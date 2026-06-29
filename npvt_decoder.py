#!/usr/bin/env python3
"""
NPVT Decoder - Standalone Python Tool
======================================
Decodes .npvt configuration files for NPV Tunnel (NapsternetV) Android app.

USAGE:
    python3 npvt_decoder.py <file.npvt> [--tables <tables.json>] [--trojan] [--out <output.json>]

If tables.json is not found locally, it will be auto-downloaded from:
    https://raw.githubusercontent.com/Nimadark/napsternetv-config-decoder/main/tables.json

EXAMPLES:
    python3 npvt_decoder.py config.npvt
    python3 npvt_decoder.py config.npvt --trojan
    python3 npvt_decoder.py config.npvt --out decoded.json
    python3 npvt_decoder.py config.npvt --tables /path/to/tables.json

ALGORITHM:
    Format:  NPVT1<b64-section-1>,<b64-section-2>,<b64-section-3>
    - Section 1: config version (encrypted JSON number, e.g. "1")
    - Section 2: servers list (encrypted JSON array of vless/vmess/trojan/ss)
    - Section 3: settings (encrypted JSON object)
    
    Encryption: White-Box AES in CTR (Counter) mode
    - Key is embedded in 5 lookup tables (970KB total)
    - Tables are extracted from the APK's memory at runtime
    - Same tables work for all .npvt files of the same app version

CREDITS:
    - Original PHP implementation by Nimadark (https://github.com/Nimadark/napsternetv-config-decoder)
    - Python port by Super Z

LEGAL:
    This tool is for security research and client migration only.
    Do NOT use it to bypass seller-imposed restrictions or resell configs.
"""

import json
import base64
import re
import sys
import os
import argparse
import urllib.request
import urllib.parse
from pathlib import Path


TABLES_URL = "https://raw.githubusercontent.com/Nimadark/napsternetv-config-decoder/main/tables.json"
TABLES_LOCAL = Path(__file__).parent / "tables.json"


# ============================================================================
# White-Box AES Tables container
# ============================================================================
class WhiteboxTables:
    """Holds the 5 lookup tables required for White-Box AES."""
    def __init__(self, nr, xor, tyboxes, tboxesLast, mbl):
        self.nr = nr                 # number of rounds - 1 (e.g. 1 for nr=2)
        self.xor = xor               # XOR lookup tables (used for MixColumns)
        self.tyboxes = tyboxes       # Type boxes (combined SubBytes + AddRoundKey + MixColumns input)
        self.tboxesLast = tboxesLast # Final round T-boxes (SubBytes + AddRoundKey, no MixColumns)
        self.mbl = mbl               # Mid-round Byte Layer (MixColumns transform)


# ============================================================================
# White-Box AES in CTR Mode (the heart of the decryption)
# ============================================================================
class WBAESCTR:
    """
    White-Box AES Counter Mode decryptor.
    Each .npvt section = 16-byte nonce + N bytes ciphertext
    Counter starts at nonce and is incremented as a big-endian 16-byte integer.
    """

    def __init__(self, tables: WhiteboxTables):
        self.tables = tables

    @staticmethod
    def _urshift(a: int, b: int) -> int:
        """Unsigned 32-bit right shift (>>> in Java/Kotlin)."""
        if b <= 0:
            return a
        return (a >> b) & ~(1 << (32 - b))

    @staticmethod
    def _shift_rows(b: list) -> None:
        """AES ShiftRows step (in-place)."""
        idx = [0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11]
        copy = b[:]
        for i in range(16):
            b[i] = copy[idx[i]]

    def _encrypt_block(self, block: list) -> list:
        """
        Encrypts a 16-byte block using White-Box AES.
        NOTE: For CTR mode decryption, we ENCRYPT the counter (this is the keystream).
        """
        state = block[:]
        n_rounds_minus_1 = self.tables.nr - 1

        tyboxes    = self.tables.tyboxes
        xor_table   = self.tables.xor
        mbl        = self.tables.mbl
        tboxes_last = self.tables.tboxesLast

        # Main rounds (1 .. nr-1)
        for r in range(n_rounds_minus_1):
            self._shift_rows(state)

            for col in range(4):
                base = col * 4
                p0, p1, p2, p3 = base, base+1, base+2, base+3

                # Stage 1: T-boxes (SubBytes + round key + MixColumns prep)
                iC  = tyboxes[r][p0][state[p0] & 0xFF] & 0xFFFFFFFF
                iC2 = tyboxes[r][p1][state[p1] & 0xFF] & 0xFFFFFFFF
                iC3 = tyboxes[r][p2][state[p2] & 0xFF] & 0xFFFFFFFF
                iC4 = tyboxes[r][p3][state[p3] & 0xFF] & 0xFFFFFFFF

                # XOR cascade (4 output bytes per column)
                for k in range(4):
                    i18 = (col * 24) + (k * 6)
                    i19 = k * 8
                    hi_shift = 28 - i19
                    lo_shift = 24 - i19

                    b10 = xor_table[r][i18    ][self._urshift(iC,  hi_shift) & 0xF][self._urshift(iC2,  hi_shift) & 0xF]
                    b11 = xor_table[r][i18 + 1][self._urshift(iC3, hi_shift) & 0xF][self._urshift(iC4, hi_shift) & 0xF]
                    idx2 = xor_table[r][i18 + 2][self._urshift(iC,  lo_shift) & 0xF][self._urshift(iC2, lo_shift) & 0xF] & 0xFF
                    idx3 = xor_table[r][i18 + 3][self._urshift(iC3, lo_shift) & 0xF][self._urshift(iC4, lo_shift) & 0xF] & 0xFF
                    val5 = xor_table[r][i18 + 5][idx2][idx3]
                    val4 = xor_table[r][i18 + 4][b10 & 0xFF][b11 & 0xFF]
                    state[base + k] = (val5 | (val4 << 4)) & 0xFF

                # Stage 2: MBL (mid-byte layer) - second MixColumns transform
                iC5  = mbl[r][p0][state[p0] & 0xFF] & 0xFFFFFFFF
                iC6  = mbl[r][p1][state[p1] & 0xFF] & 0xFFFFFFFF
                iC7  = mbl[r][p2][state[p2] & 0xFF] & 0xFFFFFFFF
                iC8  = mbl[r][p3][state[p3] & 0xFF] & 0xFFFFFFFF

                for k in range(4):
                    i28 = (col * 24) + (k * 6)
                    i29 = k * 8
                    hi_shift = 28 - i29
                    lo_shift = 24 - i29

                    idx_e0 = xor_table[r][i28    ][self._urshift(iC5, hi_shift) & 0xF][self._urshift(iC6, hi_shift) & 0xF] & 0xFF
                    idx_e1 = xor_table[r][i28 + 1][self._urshift(iC7, hi_shift) & 0xF][self._urshift(iC8, hi_shift) & 0xF] & 0xFF
                    idx_e2 = xor_table[r][i28 + 2][self._urshift(iC5, lo_shift) & 0xF][self._urshift(iC6, lo_shift) & 0xF] & 0xFF
                    idx_e3 = xor_table[r][i28 + 3][self._urshift(iC7, lo_shift) & 0xF][self._urshift(iC8, lo_shift) & 0xF] & 0xFF
                    val4_part = xor_table[r][i28 + 4][idx_e0][idx_e1] & 0xFF
                    val5_part = xor_table[r][i28 + 5][idx_e2][idx_e3]
                    state[base + k] = ((val4_part << 4) | val5_part) & 0xFF

        # Final round: ShiftRows + last T-boxes (no MixColumns)
        self._shift_rows(state)
        for i in range(16):
            state[i] = tboxes_last[i][state[i] & 0xFF]

        return state

    def decrypt(self, ciphertext_with_nonce: bytes) -> bytes:
        """
        Decrypt one .npvt section.
        Layout: [16-byte nonce (counter init)][N-byte ciphertext]
        """
        data = list(ciphertext_with_nonce)
        if len(data) < 16:
            raise ValueError("Ciphertext truncated (need at least 16 bytes for nonce)")

        nonce = data[:16]              # counter initial value
        ct    = data[16:]              # actual ciphertext
        pt    = bytearray(len(ct))
        keystream_block = [0] * 16
        counter = nonce[:]

        for i, c_byte in enumerate(ct):
            if (i & 15) == 0:
                # Generate next keystream block: ENCRYPT the counter
                keystream_block = self._encrypt_block(counter)
                # Increment counter as big-endian 16-byte integer
                for j in range(15, -1, -1):
                    v = (counter[j] + 1) & 0xFF
                    counter[j] = v
                    if v != 0:
                        break

            pt[i] = keystream_block[i & 15] ^ c_byte

        return bytes(pt)


# ============================================================================
# Base64 + Config Importer
# ============================================================================
def _decode_b64(s: str) -> bytes:
    """Decode Base64, fallback to URL-safe variant."""
    s = re.sub(r'\s+', '', s)
    try:
        return base64.b64decode(s, validate=True)
    except Exception:
        # Try URL-safe
        s2 = s.replace('-', '+').replace('_', '/')
        # pad
        pad = (-len(s2)) % 4
        s2 += '=' * pad
        return base64.b64decode(s2)


class ConfigImporter:
    """
    Parses a full .npvt file.
    Format:
        NPVT1<b64-1>,<b64-2>,<b64-3>
    Where:
        part 1 = encrypted config version (e.g. "1")
        part 2 = encrypted JSON: list of servers (vless/vmess/trojan/ss)
        part 3 = encrypted JSON: settings object
    """

    def __init__(self, wbaes: WBAESCTR):
        self.wbaes = wbaes

    def import_config(self, import_string: str) -> dict:
        try:
            import_string = import_string.strip()
            if not import_string.startswith("NPVT1"):
                raise ValueError("invalid config header (must start with NPVT1)")

            payload = import_string[5:].strip()
            parts = [p.strip() for p in payload.split(',')]

            if len(parts) != 3:
                raise ValueError(f"invalid config: expected 3 parts, got {len(parts)}")

            decrypted_parts = []
            for part in parts:
                binary = _decode_b64(part)
                plain  = self.wbaes.decrypt(binary)
                decrypted_parts.append(plain.rstrip(b'\x00 \t\r\n').decode('utf-8', errors='replace'))

            version = int(decrypted_parts[0])
            if version > 1:
                raise ValueError(f"unsupported config version {version} (need v1)")

            servers = json.loads(decrypted_parts[1])
            settings = json.loads(decrypted_parts[2])

            return {
                'status':  'success',
                'version': version,
                'servers': servers,
                'setting': settings,
                '_decrypted_parts': decrypted_parts,  # for debugging
            }
        except Exception as e:
            return {'status': 'failed', 'message': str(e)}


# ============================================================================
# Tables loader (auto-download if missing)
# ============================================================================
def load_tables(tables_path: str = None) -> WhiteboxTables:
    """Load white-box AES lookup tables from JSON. Auto-download if missing."""
    if tables_path:
        path = Path(tables_path)
    else:
        path = TABLES_LOCAL
    
    if not path.exists():
        print(f"[*] Tables not found at {path}", file=sys.stderr)
        print(f"[*] Auto-downloading from {TABLES_URL} ...", file=sys.stderr)
        try:
            urllib.request.urlretrieve(TABLES_URL, path)
            print(f"[+] Downloaded tables ({path.stat().st_size} bytes)", file=sys.stderr)
        except Exception as e:
            raise RuntimeError(f"Failed to download tables: {e}\n"
                             f"Please manually download tables.json from:\n  {TABLES_URL}")
    
    with open(path, 'r') as f:
        data = json.load(f)
    return WhiteboxTables(
        nr         = data['nr'],
        xor        = data['xor'],
        tyboxes    = data['tyboxes'],
        tboxesLast = data['tboxesLast'],
        mbl        = data['mbl'],
    )


# ============================================================================
# Helpers: convert decoded server to standard URL schemes
# ============================================================================
def server_to_trojan_url(srv: dict) -> str:
    """Convert a decoded V2RAY/Trojan server to a trojan:// URL."""
    v2p = srv.get('v2rayProfile', {})
    password = v2p.get('password', '')
    server   = v2p.get('server', '')
    port     = v2p.get('serverPort', '443')
    
    # Try to extract from v2rayJson if direct fields are missing
    if not password and v2p.get('v2rayJson'):
        try:
            v2j = json.loads(v2p['v2rayJson'])
            for ob in v2j.get('outbounds', []):
                if ob.get('tag') == 'proxy' and ob.get('protocol') == 'trojan':
                    s = ob['settings']['servers'][0]
                    password = s.get('password', '')
                    server = s.get('address', server)
                    port = s.get('port', port)
                    ss = ob.get('streamSettings', {})
                    v2p['network']  = ss.get('network', v2p.get('network', 'ws'))
                    v2p['security'] = ss.get('security', v2p.get('security', 'tls'))
                    v2p['host']     = ss.get('wsSettings', {}).get('host', v2p.get('host', ''))
                    v2p['path']     = ss.get('wsSettings', {}).get('path', v2p.get('path', '/'))
                    v2p['sni']      = ss.get('tlsSettings', {}).get('serverName', v2p.get('sni', ''))
                    break
        except Exception:
            pass
    
    network  = v2p.get('network', 'ws')
    security = v2p.get('security', 'tls')
    host     = v2p.get('host', '')
    path     = v2p.get('path', '/')
    sni      = v2p.get('sni', '')
    fp       = v2p.get('fingerPrint', 'chrome')
    alpn     = v2p.get('alpn', 'http/1.1')
    name     = srv.get('name', 'server')
    
    params = urllib.parse.urlencode({
        'security': security,
        'type': network,
        'host': host,
        'path': path,
        'sni': sni,
        'fp': fp,
        'alpn': alpn,
    }, quote_via=urllib.parse.quote)
    
    return f"trojan://{password}@{server}:{port}?{params}#{urllib.parse.quote(name)}"


def server_to_vless_url(srv: dict) -> str:
    """Convert a decoded V2RAY/VLESS server to a vless:// URL (if applicable)."""
    v2p = srv.get('v2rayProfile', {})
    if not v2p.get('v2rayJson'):
        return ""
    try:
        v2j = json.loads(v2p['v2rayJson'])
        for ob in v2j.get('outbounds', []):
            if ob.get('protocol') == 'vless':
                s = ob['settings']['vnext'][0]
                user = s['users'][0]
                uuid = user['id']
                server = s['address']
                port = s['port']
                ss = ob.get('streamSettings', {})
                params = urllib.parse.urlencode({
                    'type': ss.get('network', 'ws'),
                    'security': ss.get('security', 'tls'),
                    'host': ss.get('wsSettings', {}).get('host', ''),
                    'path': ss.get('wsSettings', {}).get('path', '/'),
                    'sni': ss.get('tlsSettings', {}).get('serverName', ''),
                }, quote_via=urllib.parse.quote)
                return f"vless://{uuid}@{server}:{port}?{params}#{urllib.parse.quote(srv.get('name',''))}"
    except Exception:
        pass
    return ""


def server_to_vmess_url(srv: dict) -> str:
    """Convert a decoded VMess server to a vmess:// URL (if applicable)."""
    v2p = srv.get('v2rayProfile', {})
    if not v2p.get('v2rayJson'):
        return ""
    try:
        v2j = json.loads(v2p['v2rayJson'])
        for ob in v2j.get('outbounds', []):
            if ob.get('protocol') == 'vmess':
                s = ob['settings']['vnext'][0]
                user = s['users'][0]
                cfg = {
                    "v": "2",
                    "ps": srv.get('name', ''),
                    "add": s['address'],
                    "port": str(s['port']),
                    "id": user['id'],
                    "aid": str(user.get('alterId', 0)),
                    "net": ob.get('streamSettings', {}).get('network', 'ws'),
                    "type": "none",
                    "host": ob.get('streamSettings', {}).get('wsSettings', {}).get('host', ''),
                    "path": ob.get('streamSettings', {}).get('wsSettings', {}).get('path', '/'),
                    "tls": ob.get('streamSettings', {}).get('security', ''),
                    "sni": ob.get('streamSettings', {}).get('tlsSettings', {}).get('serverName', ''),
                }
                return "vmess://" + base64.b64encode(
                    json.dumps(cfg, separators=(',', ':')).encode()
                ).decode()
    except Exception:
        pass
    return ""


# ============================================================================
# Pretty printer
# ============================================================================
def print_summary(result: dict, show_trojan: bool = False) -> None:
    """Print a human-readable summary of the decoded config."""
    print("=" * 70)
    print(f"  Status:   {result.get('status')}")
    if result.get('status') != 'success':
        print(f"  Error:    {result.get('message')}")
        print("=" * 70)
        return

    print(f"  Version:  {result.get('version')}")
    print(f"  Servers:  {len(result.get('servers', []))} server(s)")
    print("=" * 70)

    for i, srv in enumerate(result.get('servers', [])):
        print(f"\n--- Server {i+1}: {srv.get('name','')} ---")
        print(f"  Address: {srv.get('address','')}")
        print(f"  Type:    {srv.get('type','')}")

        v2p = srv.get('v2rayProfile', {})

        # If v2rayJson is empty, fields are at top level
        if v2p.get('v2rayJson'):
            try:
                v2j = json.loads(v2p['v2rayJson'])
                for ob in v2j.get('outbounds', []):
                    if ob.get('tag') == 'proxy':
                        print(f"  Protocol: {ob.get('protocol','')}")
                        if 'servers' in ob.get('settings', {}):
                            s = ob['settings']['servers'][0]
                            print(f"  Server IP:    {s.get('address','')}")
                            print(f"  Server Port:  {s.get('port','')}")
                            if 'password' in s:
                                print(f"  Password:     {s.get('password','')}")
                        elif 'vnext' in ob.get('settings', {}):
                            s = ob['settings']['vnext'][0]
                            u = s['users'][0]
                            print(f"  Server IP:    {s.get('address','')}")
                            print(f"  Server Port:  {s.get('port','')}")
                            print(f"  UUID:         {u.get('id','')}")
                            print(f"  AlterId:      {u.get('alterId',0)}")
                        ss = ob.get('streamSettings', {})
                        print(f"  Network:      {ss.get('network','')}")
                        print(f"  Security:     {ss.get('security','')}")
                        if 'wsSettings' in ss:
                            print(f"  WS Host:      {ss['wsSettings'].get('host','')}")
                            print(f"  WS Path:      {ss['wsSettings'].get('path','')}")
                        if 'tlsSettings' in ss:
                            print(f"  SNI:          {ss['tlsSettings'].get('serverName','')}")
                            print(f"  Fingerprint:  {ss['tlsSettings'].get('fingerprint','')}")
            except Exception as e:
                print(f"  (parse error: {e})")
        else:
            # Fields at top level of v2rayProfile
            print(f"  Protocol:     trojan (inferred)")
            print(f"  Server IP:    {v2p.get('server','')}")
            print(f"  Server Port:  {v2p.get('serverPort','')}")
            print(f"  Password:     {v2p.get('password','')}")
            print(f"  Network:      {v2p.get('network','')}")
            print(f"  Security:     {v2p.get('security','')}")
            print(f"  Host:         {v2p.get('host','')}")
            print(f"  Path:         {v2p.get('path','')}")
            print(f"  SNI:          {v2p.get('sni','')}")
            print(f"  Fingerprint:  {v2p.get('fingerPrint','')}")
            print(f"  ALPN:         {v2p.get('alpn','')}")

        # Lock config
        lc = srv.get('lockConfig', {})
        if lc:
            print(f"\n  Lock Config:")
            print(f"    Is Locked:               {lc.get('isLocked', False)}")
            print(f"    Block Rooted/Jailbroken: {lc.get('blockRootedAndJailbroken', False)}")
            print(f"    Expiry Date:             {lc.get('expiryDate', '') or '(none)'}")
            print(f"    Device IDs:              {lc.get('deviceIds', '') or '(none)'}")
            if lc.get('message'):
                print(f"    Message:")
                for line in lc['message'].split('\n'):
                    print(f"      {line}")

        # Trojan URL
        if show_trojan:
            url = server_to_trojan_url(srv)
            if url:
                print(f"\n  Trojan URL:")
                print(f"    {url}")

    # Settings
    setting = result.get('setting', {})
    if setting:
        print(f"\n--- Global Settings ---")
        for k, v in setting.items():
            if k == 'message':
                print(f"  {k}:")
                for line in str(v).split('\n'):
                    print(f"    {line}")
            else:
                print(f"  {k}: {v}")


# ============================================================================
# Main CLI
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description='Decode .npvt files from NPV Tunnel (NapsternetV) Android app',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  python3 npvt_decoder.py config.npvt
  python3 npvt_decoder.py config.npvt --trojan
  python3 npvt_decoder.py config.npvt --out decoded.json
  python3 npvt_decoder.py config.npvt --tables /path/to/tables.json
        """,
    )
    parser.add_argument('npvt_file', help='Path to the .npvt file to decode')
    parser.add_argument('--tables', default=None,
                       help=f'Path to tables.json (default: {TABLES_LOCAL}, auto-download if missing)')
    parser.add_argument('--out', '-o', default=None,
                       help='Save full decoded JSON to this file')
    parser.add_argument('--trojan', '-t', action='store_true',
                       help='Also generate trojan:// URLs for each server')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Only output JSON, no progress messages')
    args = parser.parse_args()

    if not args.quiet:
        print(f"[*] Loading white-box tables...", file=sys.stderr)
    tables = load_tables(args.tables)
    wbaes  = WBAESCTR(tables)
    importer = ConfigImporter(wbaes)

    if not args.quiet:
        print(f"[*] Decoding {args.npvt_file}...", file=sys.stderr)

    with open(args.npvt_file, 'r', encoding='utf-8') as f:
        content = f.read()

    result = importer.import_config(content)

    if not args.quiet:
        print_summary(result, show_trojan=args.trojan)
        print()
        print("=" * 70)
        print("Full decoded JSON:")
        print("=" * 70)

    # Output JSON to stdout (so it can be piped/redirected)
    output_json = {k: v for k, v in result.items() if k != '_decrypted_parts'}
    print(json.dumps(output_json, indent=2, ensure_ascii=False))

    # Save to file if requested
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(output_json, f, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(f"\n[+] Saved to {args.out}", file=sys.stderr)

    return 0 if result.get('status') == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
