from telethon import TelegramClient, events, functions
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate
import asyncio
import time
import random
import re
from datetime import datetime
import os
import json
import urllib.parse

# تنظیمات API
api_id = 35312792
api_hash = '0536b75d8bbb77161edaba324dec570c'

# ادامه بدون پروکسی در GitHub Action
proxy_info = None
client = TelegramClient('session_name', api_id, api_hash)

# تنظیمات ربات اول (آپدیت پروفایل و ارسال استیکر)
CHANNEL_USERNAME = '@proxyHagh'
STICKERS = [
    'CAACAgIAAxkBAAIBMWb6fVn_8t5QeGdN3bHc6UuO8u7-AAJhCwACRXMFSp0eAAE92rP1BTQE',
    'CAACAgIAAxkBAAIBMmb6fV8pX7q8uX7q8uX7q8uX7q8uX7q8AAJiCwACRXMFSp0eAAE92rP1BTQE',
    'CAACAgIAAxkBAAIBM2b6fV9wX7q8uX7q8uX7q8uX7q8uX7q8AAJjCwACRXMFSp0eAAE92rP1BTQE'
]

# تنظیمات ربات دوم (کامنت گذاری)
TARGET_CHANNELS = [
    '@FO_RK',
    '@NE_WG', 
    '@es_qb',
    'https://t.me/+0GG5VeCaAe5mZThk',
    '@proxyHagh'
]

# کانال‌هایی که پست‌هایشان کپی و ارسال می‌شود (به جز موارد استثنا)
ALLOWED_FOR_COPY = ['@FO_RK', '@NE_WG']

# کانال مقصد برای ارسال پست‌های کپی شده
TARGET_CHANNEL = 'https://t.me/fast_new_s'

# نام‌های کاربری که باید از متن حذف شوند
REMOVE_USERNAMES = ['@AkhbarTelFori', '@News1Fori']

FALLBACK_MESSAGES = ['ممنون', 'تشکر', 'سپاس']

# تنظیمات سرعت ایمن برای جلوگیری از FloodWait - افزایش سرعت
MAX_RETRIES = 2  # کاهش تعداد تلاش‌ها برای سرعت بیشتر
RETRY_DELAY = 1  # کاهش تاخیر بین تلاش‌ها
MONITOR_DELAY = 2  # کاهش تاخیر مانیتورینگ
COMMENT_SPEED_BOOST = True  # فعال‌سازی افزایش سرعت کامنت
ULTRA_FAST_MODE = True  # فعال‌سازی حالت فوق‌سریع
HYPER_SPEED_COMMENTS = True  # فعال‌سازی کامنت‌گذاری ابرسریع

# تنظیمات هوش مصنوعی
AI_BOT_USERNAME = '@CopilotOfficialBot'

# پوشه ذخیره تمام رسانه های نابود شونده در حافظه داخلی
SAVE_DIRECTORY = '/storage/emulated/0/Download/Telegram_Saved_Media'
os.makedirs(SAVE_DIRECTORY, exist_ok=True)

# فایل برای ذخیره اطلاعات رسانه های ذخیره شده
SAVED_MEDIA_FILE = '/storage/emulated/0/Download/Telegram_Saved_Media/saved_media.json'

# ذخیره entityهای کانال‌ها
channel_entities = {}
last_messages = {}
processed_messages = set()
copied_messages = set()
saved_self_destruct = set()
ultra_fast_cache = {}
hyper_speed_queue = asyncio.Queue()
ai_conversations = {}
ai_waiting_responses = {}
ai_group_waiting_responses = {}
processed_replies = set()  # برای جلوگیری از پردازش تکراری ریپلای‌ها
ai_processing_messages = set()  # برای جلوگیری از پردازش تکراری پیام‌های هوش مصنوعی

# ==================== توابع مدیریت ایمن برای جلوگیری از FloodWait ====================

async def safe_telegram_call(operation, *args, operation_name="", delay_before=0.3, delay_after=0.5, **kwargs):
    """تماس ایمن با تلگرام با تاخیرهای کنترل شده - سرعت افزایش یافته"""
    try:
        # تاخیر قبل از عملیات - کاهش یافته
        if delay_before > 0:
            await asyncio.sleep(delay_before)
        
        result = await operation(*args, **kwargs)
        
        # تاخیر بعد از عملیات - کاهش یافته
        if delay_after > 0:
            await asyncio.sleep(delay_after)
            
        return result
        
    except FloodWaitError as e:
        print(f"⏳ FloodWait شناسایی شد برای {operation_name}: {e.seconds} ثانیه")
        await asyncio.sleep(e.seconds + 3)  # اضافه کردن 3 ثانیه اضافی برای اطمینان
        return await safe_telegram_call(operation, *args, operation_name=operation_name, 
                                      delay_before=0, delay_after=delay_after, **kwargs)
    except Exception as e:
        print(f"❌ خطا در {operation_name}: {e}")
        return None

# ==================== توابع مدیریت رسانه های نابود شونده ====================

def load_saved_media():
    """بارگذاری لیست رسانه های ذخیره شده از فایل"""
    try:
        if os.path.exists(SAVED_MEDIA_FILE):
            with open(SAVED_MEDIA_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
    except Exception as e:
        print(f"❌ خطا در بارگذاری رسانه های ذخیره شده: {e}")
    return set()

def save_media_list():
    """ذخیره لیست رسانه های ذخیره شده در فایل"""
    try:
        with open(SAVED_MEDIA_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(saved_self_destruct), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ خطا در ذخیره لیست رسانه ها: {e}")

def is_self_destruct_media(message):
    """بررسی اینکه آیا رسانه نابود شونده است"""
    if not message.media:
        return False
    
    if hasattr(message, 'media') and message.media:
        if hasattr(message.media, 'ttl_seconds') and message.media.ttl_seconds:
            return True
        
        if hasattr(message.media, 'ttl_seconds') and message.media.ttl_seconds > 0:
            return True
            
        if (hasattr(message, 'action') and hasattr(message.action, 'type') and 
            any(keyword in str(message.action.type).lower() for keyword in ['photo', 'video', 'secret', 'selfdestruct'])):
            return True
            
        if hasattr(message.media, 'document') and hasattr(message.media.document, 'mime_type'):
            if hasattr(message.media, 'ttl_seconds'):
                return True
    
    return False

async def save_self_destruct_media(message, source_info):
    """ذخیره تمام رسانه های نابود شونده در حافظه داخلی"""
    try:
        if not message.media:
            return False
        
        message_key = f"self_destruct_{message.chat_id}_{message.id}"
        
        if message_key in saved_self_destruct:
            return False
        
        print(f"💾 در حال ذخیره رسانه نابود شونده از {source_info}...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        clean_source = re.sub(r'[^\w\-_.]', '_', source_info)
        
        file_extension = ".unknown"
        if hasattr(message.media, 'document'):
            mime_type = message.media.document.mime_type.lower()

            if 'video' in mime_type:
                file_extension = ".mp4"
            elif 'image' in mime_type:
                file_extension = ".jpg"
            elif 'audio' in mime_type:
                file_extension = ".mp3"
            else:
                file_extension = ".bin"
        elif hasattr(message.media, 'photo'):
            file_extension = ".jpg"
        
        filename = f"{SAVE_DIRECTORY}/self_destruct_{clean_source}_{timestamp}_{message.id}{file_extension}"
        
        try:
            test_file = f"{SAVE_DIRECTORY}/test_write.txt"
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except Exception as e:
            print(f"⚠️ دسترسی به حافظه داخلی ممکن نیست: {e}")
            alt_save_dir = '/data/data/com.termux/files/home/storage/shared/Download/Telegram_Saved_Media'
            os.makedirs(alt_save_dir, exist_ok=True)
            filename = f"{alt_save_dir}/self_destruct_{clean_source}_{timestamp}_{message.id}{file_extension}"
            print(f"📁 استفاده از مسیر جایگزین: {alt_save_dir}")
        
        downloaded_path = await safe_telegram_call(
            message.download_media, 
            file=filename,
            operation_name="دانلود رسانه نابود شونده",
            delay_before=0.2,
            delay_after=0.3
        )
        
        if downloaded_path:
            print(f"✅ رسانه نابود شونده از {source_info} ذخیره شد: {os.path.basename(downloaded_path)}")
            
            saved_self_destruct.add(message_key)
            save_media_list()
            
            if "Saved Messages" not in source_info and "private" not in source_info.lower():
                await safe_telegram_call(
                    client.send_message,
                    entity='me',
                    message=f"✅ رسانه نابود شونده ذخیره شد:\n👤 از: {source_info}\n📅 زمان: {timestamp}\n📁 فایل: {os.path.basename(downloaded_path)}",
                    operation_name="ارسال تأییدیه رسانه",
                    delay_before=0.2,
                    delay_after=0.3
                )
            return True
        else:
            print(f"❌ خطا در دانلود رسانه نابود شونده از {source_info}")
            return False
            
    except Exception as e:
        print(f"❌ خطا در ذخیره رسانه نابود شونده از {source_info}: {e}")
        return False

def get_source_info(event):
    """دریافت اطلاعات منبع پیام"""
    try:
        chat = event.chat
        sender = event.sender
        
        if sender:
            if hasattr(sender, 'username') and sender.username:
                return f"@{sender.username}"
            elif hasattr(sender, 'first_name'):
                name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
                return name if name else f"user_{sender.id}"
            else:
                return f"user_{sender.id}"
        elif chat:
            if hasattr(chat, 'title'):
                return f"chat_{chat.title}"
            else:
                return f"chat_{chat.id}"
        else:
            return "unknown_source"
    except:
        return "unknown_source"

# ==================== توابع ربات اول ====================

async def update_profile_and_send_sticker():
    """به‌روزرسانی نام پروفایل و ارسال استیکر"""
    try:
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # تبدیل اعداد به سبک ترکیبی Fraktur و Double Struck
        styled_time = current_time
        fraktur_map = {
            '0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒',
            '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗'
        }
        double_struck_map = {
            '0': '𝟘', '1': '𝟙', '2': '𝟚', '3': '𝟛', '4': '𝟜',
            '5': '𝟝', '6': '𝟞', '7': '𝟟', '8': '𝟠', '9': '𝟡'
        }
        
        # استفاده ترکیبی از هر دو فونت
        for i, char in enumerate(current_time):
            if char.isdigit():
                if i % 2 == 0:  # اعداد در موقعیت زوج از Fraktur
                    styled_time = styled_time.replace(char, fraktur_map[char], 1)
                else:  # اعداد در موقعیت فرد از Double Struck
                    styled_time = styled_time.replace(char, double_struck_map[char], 1)
        
        new_first_name = f"⏰ {styled_time}"
        await safe_telegram_call(
            client,
            functions.account.UpdateProfileRequest(first_name=new_first_name),
            operation_name="آپدیت پروفایل",
            delay_before=0.5,
            delay_after=0.5
        )
        print(f"🔄 نام اکانت به‌روزرسانی شد: {new_first_name}")
        
        channel = await safe_telegram_call(
            client.get_entity,
            CHANNEL_USERNAME,
            operation_name="دریافت اطلاعات کانال",
            delay_before=0.3,
            delay_after=0.3
        )
        sticker = random.choice(STICKERS)
        await safe_telegram_call(
            client.send_file,
            channel, sticker,
            operation_name="ارسال استیکر",
            delay_before=0.3,
            delay_after=0.5
        )
        print(f"🎯 استیکر ارسال شد به: {CHANNEL_USERNAME}")
        
    except Exception as e:
        print(f"❌ خطا در به‌روزرسانی: {e}")

async def profile_updater():
    """برنامه‌ریزی به‌روزرسانی پروفایل هر دقیقه"""
    await asyncio.sleep(5)  # تاخیر اولیه کمتر
    while True:
        await update_profile_and_send_sticker()
        await asyncio.sleep(60)  # هر 1 دقیقه

# ==================== توابع ربات دوم - کامنت گذاری ایمن ====================

def extract_random_word(text):
    """استخراج یک کلمه تصادفی از متن"""
    if not text:
        return random.choice(FALLBACK_MESSAGES)
    
    words = re.findall(r'[\u0600-\u06FFa-zA-Z]{2,}', text)
    return random.choice(words) if words else random.choice(FALLBACK_MESSAGES)

def modify_text(text):
    """حذف نام‌های کاربری و جایگزینی با آدرس کانال مقصد"""
    if not text:
        return text
    
    modified_text = text
    for username in REMOVE_USERNAMES:
        modified_text = modified_text.replace(username, '')
    
    modified_text = re.sub(r'\n\s*\n', '\n\n', modified_text)
    modified_text = modified_text.strip()
    
    if modified_text:
        modified_text += f"\n\n📢 @fast_new_s"
    
    return modified_text

async def get_channel_entity(channel_identifier):
    """دریافت و ذخیره entity کانال فقط یک بار"""
    if channel_identifier in channel_entities:
        return channel_entities[channel_identifier]
    
    try:
        print(f"🔗 در حال دریافت entity برای {channel_identifier}...")
        channel = await safe_telegram_call(
            client.get_entity,
            channel_identifier,
            operation_name="دریافت entity کانال",
            delay_before=0.3,
            delay_after=0.3
        )
        channel_entities[channel_identifier] = channel
        print(f"✅ entity کانال دریافت شد: {getattr(channel, 'title', 'Unknown')}")
        return channel
    except Exception as e:
        print(f"❌ خطا در دریافت entity برای {channel_identifier}: {e}")
        return None

async def safe_send_comment(channel_entity, message):
    """ارسال ایمن کامنت با سرعت ابرسریع - تغییرات اصلی برای سرعت بالا"""
    cache_key = f"comment_{channel_entity.id}_{message.id}"
    if cache_key in ultra_fast_cache:
        return True
    
    try:
        if hasattr(channel_entity, 'username') and channel_entity.username:
            channel_id = channel_entity.username
        else:
            channel_id = str(channel_entity.id)
        
        message_key = f"{channel_id}_{message.id}"
        
        if message_key in processed_messages:
            ultra_fast_cache[cache_key] = True
            return True
            
        post_text = message.text or message.raw_text or ""
        random_word = extract_random_word(post_text)
        
        print(f"💬 ارسال کامنت ابرسریع به {channel_id}...")
        
        # ارسال کامنت با سرعت ابرسریع - بدون تاخیر
        await client.send_message(
            entity=channel_entity,
            message=random_word,
            comment_to=message.id
        )
        
        print(f"✅ کامنت ابرسریع '{random_word}' در {channel_id} ارسال شد!")
        
        processed_messages.add(message_key)
        ultra_fast_cache[cache_key] = True
        return True

    except FloodWaitError as e:
        print(f"⏳ FloodWait در کامنت ابرسریع: {e.seconds} ثانیه")
        await asyncio.sleep(e.seconds + 2)
        return await safe_send_comment(channel_entity, message)
    except Exception as e:
        print(f"❌ خطا در ارسال کامنت ابرسریع: {e}")
        return False

async def safe_copy_and_send(message, channel_entity):
    """کپی محتوا و ارسال ایمن به کانال مقصد"""
    try:
        channel_id = channel_entity.username if hasattr(channel_entity, 'username') and channel_entity.username else str(channel_entity.id)
        
        should_copy = False
        for allowed in ALLOWED_FOR_COPY:
            if allowed in channel_id or channel_id in allowed:
                should_copy = True
                break
        
        if not should_copy:
            return False
            
        message_key = f"copy_{channel_id}_{message.id}"
        
        if message_key in copied_messages:
            return False
            
        print(f"📝 کپی و ارسال محتوا از {channel_id}...")
        
        target_channel = await safe_telegram_call(
            client.get_entity,
            TARGET_CHANNEL,
            operation_name="دریافت entity کانال مقصد",
            delay_before=0.3,
            delay_after=0.3
        )
        
        if message.media:
            if message.text:
                modified_text = modify_text(message.text)
                await safe_telegram_call(
                    client.send_file,
                    target_channel,
                    message.media,
                    caption=modified_text,
                    operation_name="ارسال فایل با کپشن",
                    delay_before=0.3,
                    delay_after=0.5
                )
            else:
                await safe_telegram_call(
                    client.send_file,
                    target_channel, message.media,
                    operation_name="ارسال فایل",
                    delay_before=0.3,
                    delay_after=0.5
                )
        else:
            original_text = message.text or message.raw_text or ""
            modified_text = modify_text(original_text)
            if modified_text and modified_text.strip():
                await safe_telegram_call(
                    client.send_message,
                    target_channel, modified_text,
                    operation_name="ارسال متن کپی شده",
                    delay_before=0.3,
                    delay_after=0.5
                )
            else:
                print("⚠️ متن پس از تغییر خالی است، ارسال نشد")
                return False
        
        print(f"✅ محتوای {channel_id} به {TARGET_CHANNEL} ارسال شد!")
        copied_messages.add(message_key)
        return True
        
    except Exception as e:
        print(f"❌ خطا در کپی و ارسال محتوا: {e}")
        return False

async def initialize_channels():
    """مقداردهی اولیه کانال‌ها"""
    print("📝 در حال راه‌اندازی کانال‌ها...")
    for channel_identifier in TARGET_CHANNELS:
        try:
            channel = await get_channel_entity(channel_identifier)
            if channel:
                messages = await safe_telegram_call(
                    client.get_messages,
                    channel, limit=2,
                    operation_name="دریافت پیام‌های کانال",
                    delay_before=0.3,
                    delay_after=0.3
                )
                if messages:
                    channel_id = channel.username if hasattr(channel, 'username') and channel.username else str(channel.id)
                    last_messages[channel_id] = messages[0].id
                    print(f"📌 آخرین پست {channel_id}: ID {messages[0].id}")
        except Exception as e:
            print(f"⚠️ خطا در راه‌اندازی کانال {channel_identifier}: {e}")

# ==================== توابع هوش مصنوعی ====================

async def send_to_ai_bot(message_text, user_id):
    """ارسال پیام به هوش مصنوعی و دریافت پاسخ"""
    try:
        print(f"🤖 ارسال پیام به هوش مصنوعی برای کاربر {user_id}...")
        
        ai_bot = await safe_telegram_call(
            client.get_entity,
            AI_BOT_USERNAME,
            operation_name="دریافت entity هوش مصنوعی",
            delay_before=0.3,
            delay_after=0.3
        )
        
        sent_message = await safe_telegram_call(
            client.send_message,
            ai_bot, message_text,
            operation_name="ارسال پیام به هوش مصنوعی",
            delay_before=0.3,
            delay_after=0.5
        )
        
        conversation_key = f"{user_id}_{sent_message.id}"
        ai_conversations[conversation_key] = {
            'user_id': user_id,
            'sent_time': datetime.now(),
            'original_message': message_text,
            'sent_message_id': sent_message.id
        }
        
        ai_waiting_responses[sent_message.id] = {
            'user_id': user_id,
            'start_time': time.time(),
            'conversation_key': conversation_key
        }
        
        print(f"✅ پیام به هوش مصنوعی ارسال شد (ID: {sent_message.id})")
        return sent_message.id
        
    except Exception as e:
        print(f"❌ خطا در ارسال به هوش مصنوعی: {e}")
        return None

async def send_to_ai_bot_group(message_text, user_id, chat_id, reply_message_id):
    """ارسال پیام به هوش مصنوعی برای پاسخ گروهی"""
    try:
        print(f"🤖 ارسال پیام گروهی به هوش مصنوعی برای کاربر {user_id} در چت {chat_id}...")
        
        ai_bot = await safe_telegram_call(
            client.get_entity,
            AI_BOT_USERNAME,
            operation_name="دریافت entity هوش مصنوعی برای گروه",
            delay_before=0.3,
            delay_after=0.3
        )
        
        sent_message = await safe_telegram_call(
            client.send_message,
            ai_bot, message_text,
            operation_name="ارسال پیام گروهی به هوش مصنوعی",
            delay_before=0.3,
            delay_after=0.5
        )
        
        ai_group_waiting_responses[sent_message.id] = {
            'user_id': user_id,
            'chat_id': chat_id,
            'reply_message_id': reply_message_id,
            'start_time': time.time(),
            'original_message': message_text
        }
        
        print(f"✅ پیام گروهی به هوش مصنوعی ارسال شد (ID: {sent_message.id})")
        return sent_message.id
        
    except Exception as e:
        print(f"❌ خطا در ارسال گروهی به هوش مصنوعی: {e}")
        return None

async def handle_private_message_with_ai(event):
    """مدیریت پیام‌های خصوصی با هوش مصنوعی"""
    try:
        user_id = event.sender_id
        message_text = event.text
        
        print(f"💬 پیام خصوصی از کاربر {user_id}: {message_text[:50]}...")
        
        sent_message_id = await send_to_ai_bot(message_text, user_id)
        
        if sent_message_id:
            await safe_telegram_call(
                event.reply,
                "⏳ در حال دریافت پیام از کیومرث...",
                operation_name="ارسال پیام انتظار",
                delay_before=0.2,
                delay_after=0.3
            )
            
            await asyncio.sleep(3)  # کاهش زمان انتظار
            
        else:
            await safe_telegram_call(
                event.reply,
                "❌ خطا در ارتباط با هوش مصنوعی",
                operation_name="ارسال پیام خطا",
                delay_before=0.2,
                delay_after=0.3
            )
            
    except Exception as e:
        print(f"❌ خطا در پردازش پیام خصوصی: {e}")
        try:
            await safe_telegram_call(
                event.reply,
                "❌ خطا در پردازش پیام",
                operation_name="ارسال پیام خطای عمومی",
                delay_before=0.2,
                delay_after=0.3
            )
        except:
            pass

async def handle_any_reply_to_my_messages(event):
    """مدیریت تمام ریپلای‌ها به پیام‌های اکانت در هر چت - رفع مشکل تکراری"""
    try:
        # بررسی اینکه آیا پیام یک ریپلای است
        if not event.is_reply:
            return False
            
        # ایجاد کلید یکتا برای جلوگیری از پردازش تکراری
        reply_key = f"{event.chat_id}_{event.message.id}"
        if reply_key in processed_replies:
            return False
            
        # دریافت پیام اصلی که ریپلای شده
        replied_msg = await event.get_reply_message()
        
        # بررسی اینکه آیا ریپلای به پیام خود ربات است
        me = await client.get_me()
        if replied_msg.sender_id != me.id:
            return False
            
        user_id = event.sender_id
        chat_id = event.chat_id
        message_text = event.text
        
        if not message_text or not message_text.strip():
            return False
        
        # ایجاد کلید اضافی برای جلوگیری از پردازش تکراری توسط هوش مصنوعی
        ai_processing_key = f"ai_processing_{user_id}_{chat_id}_{message_text[:20]}"
        if ai_processing_key in ai_processing_messages:
            return False
            
        print(f"💬 ریپلای به پیام من از کاربر {user_id} در چت {chat_id}: {message_text[:50]}...")
        
        # علامت گذاری به عنوان پردازش شده برای جلوگیری از تکراری
        processed_replies.add(reply_key)
        ai_processing_messages.add(ai_processing_key)
        
        sent_message_id = await send_to_ai_bot_group(message_text, user_id, chat_id, event.message.id)
        
        if sent_message_id:
            print(f"✅ متن ریپلای به هوش مصنوعی ارسال شد (ID: {sent_message.id})")
            
            # پاک کردن کلید پردازش هوش مصنوعی بعد از 30 ثانیه برای جلوگیری از انباشته شدن
            await asyncio.sleep(30)
            ai_processing_messages.discard(ai_processing_key)
            
            return True
        else:
            print("❌ خطا در ارسال ریپلای به هوش مصنوعی")
            # اگر خطا رخ داد، کلیدها را پاک کن تا دوباره تلاش کند
            processed_replies.discard(reply_key)
            ai_processing_messages.discard(ai_processing_key)
            return False
            
    except Exception as e:
        print(f"❌ خطا در پردازش ریپلای به پیام‌های من: {e}")
        # در صورت خطا نیز کلیدها را پاک کن
        if 'reply_key' in locals():
            processed_replies.discard(reply_key)
        if 'ai_processing_key' in locals():
            ai_processing_messages.discard(ai_processing_key)
        return False

# ==================== هندلرهای پیام ====================

@client.on(events.NewMessage)
async def universal_message_handler(event):
    """هندلر جهانی برای تمام پیام‌ها"""
    try:
        # بررسی و ذخیره رسانه های نابود شونده
        if event.message.media and is_self_destruct_media(event.message):
            source_info = get_source_info(event)
            print(f"🚨 رسانه نابود شونده از {source_info} شناسایی شد!")
            await save_self_destruct_media(event.message, source_info)
        
        # مدیریت ریپلای‌ها به پیام‌های اکانت - بالاترین اولویت
        reply_handled = await handle_any_reply_to_my_messages(event)
        if reply_handled:
            return
        
        # مدیریت پیام‌های خصوصی
        if event.is_private and not event.message.out:
            me = await client.get_me()
            if event.sender_id == me.id:
                return
                
            try:
                ai_bot = await client.get_entity(AI_BOT_USERNAME)
                if event.sender_id == ai_bot.id:
                    return
            except:
                pass
            
            await handle_private_message_with_ai(event)
            return
        
        # کد اصلی برای کامنت گذاری و کپی پیام‌ها
        channel = event.chat
        
        channel_found = False
        for identifier, entity in channel_entities.items():
            if entity.id == channel.id:
                channel_found = True
                break

        if not channel_found:
            return
            
        message_id = event.message.id
        final_channel_id = channel.username if hasattr(channel, 'username') and channel.username else str(channel.id)
        message_key = f"{final_channel_id}_{message_id}"
        
        if message_key in processed_messages:
            return
            
        print(f"🎯 پست جدید در {final_channel_id} (ID: {message_id})")
        
        post_text = event.message.text or event.message.raw_text or ""
        if post_text:
            preview = post_text[:20] + "..." if len(post_text) > 20 else post_text
            print(f"📄 متن پست: '{preview}'")
        
        processed_messages.add(message_key)
        
        # استفاده از asyncio.create_task برای اجرای همزمان و سریعتر
        tasks = []
        tasks.append(asyncio.create_task(safe_send_comment(channel, event.message)))
        tasks.append(asyncio.create_task(safe_copy_and_send(event.message, channel)))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
    except Exception as e:
        print(f"❌ خطا در هندلر پیام: {e}")

@client.on(events.Album)
async def album_handler(event):
    """هندلر برای آلبوم‌های عکس (تصاویر چندتایی)"""
    try:
        for message in event.messages:
            if message.media and is_self_destruct_media(message):
                source_info = get_source_info(event)
                print(f"🚨 رسانه نابود شونده در آلبوم از {source_info} شناسایی شد!")
                await save_self_destruct_media(message, source_info)
    except Exception as e:
        print(f"❌ خطا در پردازش آلبوم: {e}")

@client.on(events.NewMessage(from_users=[AI_BOT_USERNAME]))
async def ai_bot_response_handler(event):
    """هندلر برای پاسخ‌های هوش مصنوعی"""
    try:
        if (hasattr(event.message, 'reply_to') and 
            hasattr(event.message.reply_to, 'reply_to_msg_id')):
            
            original_message_id = event.message.reply_to.reply_to_msg_id
            
            # پردازش پاسخ برای ریپلای‌های گروهی
            if original_message_id in ai_group_waiting_responses:
                conversation_data = ai_group_waiting_responses[original_message_id]
                user_id = conversation_data['user_id']
                chat_id = conversation_data['chat_id']
                reply_message_id = conversation_data['reply_message_id']
                ai_response = event.text
                
                print(f"🤖 دریافت پاسخ گروهی از هوش مصنوعی برای کاربر {user_id} در چت {chat_id}")
                
                await safe_telegram_call(
                    client.send_message,
                    chat_id, ai_response,
                    reply_to=reply_message_id,
                    operation_name="ارسال پاسخ هوش مصنوعی گروهی",
                    delay_before=0.3,
                    delay_after=0.5
                )
                
                del ai_group_waiting_responses[original_message_id]
                
                print(f"✅ پاسخ هوش مصنوعی به کاربر {user_id} در چت {chat_id} ارسال شد")
                return
            
            # پردازش پاسخ برای پیام‌های خصوصی
            if original_message_id in ai_waiting_responses:
                conversation_data = ai_waiting_responses[original_message_id]
                user_id = conversation_data['user_id']
                ai_response = event.text
                
                print(f"🤖 دریافت پاسخ از هوش مصنوعی برای کاربر {user_id}")
                
                await safe_telegram_call(
                    client.send_message,
                    user_id, f"پیام از کیومرث:\n\n{ai_response}",
                    operation_name="ارسال پاسخ هوش مصنوعی خصوصی",
                    delay_before=0.3,
                    delay_after=0.5
                )
                
                del ai_waiting_responses[original_message_id]
                
                conversation_key = conversation_data['conversation_key']
                if conversation_key in ai_conversations:
                    del ai_conversations[conversation_key]
                
                print(f"✅ پاسخ هوش مصنوعی به کاربر {user_id} ارسال شد")
                return
        
        # پردازش پاسخ‌های مستقیم (بدون ریپلای)
        current_time = time.time()
        
        # بررسی پاسخ‌های گروهی منقضی شده
        expired_group_messages = []
        for sent_id, data in ai_group_waiting_responses.items():
            if current_time - data['start_time'] > 45:  # کاهش زمان انتظار
                expired_group_messages.append(sent_id)
                continue
                
            user_id = data['user_id']
            chat_id = data['chat_id']
            reply_message_id = data['reply_message_id']
            
            if current_time - data['start_time'] < 25:  # کاهش زمان انتظار
                ai_response = event.text
                
                print(f"🤖 دریافت پاسخ مستقیم گروهی از هوش مصنوعی برای کاربر {user_id} در چت {chat_id}")
                
                await safe_telegram_call(
                    client.send_message,
                    chat_id, ai_response,
                    reply_to=reply_message_id,
                    operation_name="ارسال پاسخ مستقیم گروهی",
                    delay_before=0.3,
                    delay_after=0.5
                )
                
                del ai_group_waiting_responses[sent_id]
                
                print(f"✅ پاسخ هوش مصنوعی به کاربر {user_id} در چت {chat_id} ارسال شد")
                break
        
        # بررسی پاسخ‌های خصوصی منقضی شده
        expired_messages = []
        for sent_id, data in ai_waiting_responses.items():
            if current_time - data['start_time'] > 45:  # کاهش زمان انتظار
                expired_messages.append(sent_id)
                continue
                
            user_id = data['user_id']
            
            if current_time - data['start_time'] < 25:  # کاهش زمان انتظار
                ai_response = event.text
                
                print(f"🤖 دریافت پاسخ مستقیم از هوش مصنوعی برای کاربر {user_id}")
                
                await safe_telegram_call(
                    client.send_message,
                    user_id, f"پیام از کیومرث:\n\n{ai_response}",
                    operation_name="ارسال پاسخ مستقیم هوش مصنوعی",
                    delay_before=0.3,
                    delay_after=0.5
                )
                
                del ai_waiting_responses[sent_id]
                conversation_key = data['conversation_key']
                if conversation_key in ai_conversations:
                    del ai_conversations[conversation_key]
                
                print(f"✅ پاسخ هوش مصنوعی به کاربر {user_id} ارسال شد")
                break
        
        # پاک‌سازی پیام‌های منقضی شده
        for expired_id in expired_messages:
            if expired_id in ai_waiting_responses:
                del ai_waiting_responses[expired_id]
        
        for expired_id in expired_group_messages:
            if expired_id in ai_group_waiting_responses:
                del ai_group_waiting_responses[expired_id]
                
    except Exception as e:
        print(f"❌ خطا در پردازش پاسخ هوش مصنوعی: {e}")

async def scan_existing_self_destruct_messages():
    """اسکن پیام‌های قدیمی برای یافتن رسانه های نابود شونده"""
    try:
        print("🔍 در حال اسکن پیام‌های قدیمی برای رسانه های نابود شونده...")
        
        dialogs = await safe_telegram_call(
            client.get_dialogs,
            limit=30,
            operation_name="دریافت دیالوگ‌ها برای اسکن",
            delay_before=0.3,
            delay_after=0.3
        )
        
        for dialog in dialogs:
            try:
                messages = await safe_telegram_call(
                    client.get_messages,
                    dialog.entity, limit=5,
                    operation_name="دریافت پیام‌های قدیمی",
                    delay_before=0.3,
                    delay_after=0.3
                )
                for message in messages:
                    if message.media and is_self_destruct_media(message):
                        source_info = get_source_info(type('Event', (), {'chat': dialog.entity, 'sender': message.sender})())
                        message_key = f"self_destruct_{message.chat_id}_{message.id}"
                        
                        if message_key not in saved_self_destruct:
                            print(f"💾 یافتن رسانه نابود شونده قدیمی از {source_info}")
                            await save_self_destruct_media(message, source_info)
                            await asyncio.sleep(0.5)  # کاهش تاخیر
            except Exception as e:
                continue
                
        print("✅ اسکن پیام‌های قدیمی تکمیل شد")
    except Exception as e:
        print(f"❌ خطا در اسکن پیام‌های قدیمی: {e}")

async def safe_monitor():
    """مانیتورینگ ایمن با تاخیرهای کنترل شده"""
    await asyncio.sleep(5)  # کاهش تاخیر اولیه
    
    while True:
        try:
            for channel_identifier in TARGET_CHANNELS:
                try:
                    if channel_identifier not in channel_entities:
                        continue
                        
                    channel = channel_entities[channel_identifier]
                    
                    messages = await safe_telegram_call(
                        client.get_messages,
                        channel, limit=1,
                        operation_name="مانیتورینگ کانال",
                        delay_before=0.3,
                        delay_after=0.3
                    )
                    
                    if messages:
                        latest_message = messages[0]
                        channel_id = channel.username if hasattr(channel, 'username') and channel.username else str(channel.id)
                        message_key = f"{channel_id}_{latest_message.id}"
                        
                        if (channel_id not in last_messages or 
                            last_messages[channel_id] != latest_message.id):
                            if message_key not in processed_messages:
                                print(f"🆕 پست جدید پیدا شد در {channel_id} (ID: {latest_message.id})")
                                last_messages[channel_id] = latest_message.id
                                
                                # استفاده از create_task برای اجرای سریعتر
                                tasks = []
                                tasks.append(asyncio.create_task(safe_send_comment(channel, latest_message)))
                                tasks.append(asyncio.create_task(safe_copy_and_send(latest_message, channel)))
                                
                                await asyncio.gather(*tasks, return_exceptions=True)
                
                except Exception as e:
                    continue
            
            await asyncio.sleep(MONITOR_DELAY)
            
        except Exception as e:
            print(f"خطا در مانیتورینگ: {e}")
            await asyncio.sleep(5)  # کاهش تاخیر خطا

# ==================== تابع اصلی ====================

async def main():
    try:
        global saved_self_destruct
        saved_self_destruct = load_saved_media()
        print(f"💾 {len(saved_self_destruct)} رسانه ذخیره شده قبلی بارگذاری شد")
        
        print(f"📁 مسیر ذخیره‌سازی رسانه ها: {SAVE_DIRECTORY}")
        
        print("🔄 در حال اتصال به تلگرام...")
        # اتصال با استفاده از session موجود بدون نیاز به کد تأیید
        await client.start()
        
        if not await client.is_user_authorized():
            print("❌ session نامعتبر است. لطفاً session جدید ایجاد کنید.")
            return
        
        print("✅ ورود موفقیت‌آمیز با session موجود!")
        
        await initialize_channels()
        
        asyncio.create_task(scan_existing_self_destruct_messages())
        
        print("🤖 ربات ابرسریع فعال شد!")
        print("🚀 کامنت‌گذاری ابرسریع در کانال‌های هدف فعال شد!")
        print("⚡ حالت فوق‌سریع فعال شده است")
        print("🛡️ حالت ایمن برای جلوگیری از FloodWait فعال است")
        print("💾 ذخیره خودکار تمام رسانه های نابود شونده فعال شد")
        print("🤖 سیستم پاسخ‌دهی هوش مصنوعی فعال شد")
        print("🔒 سیستم جلوگیری از ارسال تکراری به هوش مصنوعی فعال شد")
        print("💬 سیستم پاسخ به ریپلای‌های پیام‌های اکانت در تمام چت‌ها فعال شد")
        print("🔍 اسکن پیام‌های قدیمی در حال اجرا...")
        print(f"📁 مسیر ذخیره‌سازی: Download/Telegram_Saved_Media")
        print("📊 ویژگی‌های فعال:")
        print("  🎯 آپدیت پروفایل و ارسال استیکر هر دقیقه")
        print("  💬 کامنت گذاری ابرسریع (بدون تاخیر)")
        print("  📝 کپی و ارسال محتوای کانال‌های مجاز")
        print("  🌐 ذخیره تمام رسانه های نابود شونده از همه منابع")
        print("  🤖 پاسخ‌دهی هوش مصنوعی به پیام‌های خصوصی")
        print("  💬 پاسخ‌دهی هوش مصنوعی به ریپلای‌های پیام‌های اکانت در تمام چت‌ها")
        print("  🔒 جلوگیری از ارسال تکراری به هوش مصنوعی")
        print("  ⚡ حالت فوق‌سریع برای تمام عملیات")
        print(f"  ✅ کانال‌های مجاز برای کپی: {ALLOWED_FOR_COPY}")
        print(f"  📨 کانال مقصد: {TARGET_CHANNEL}")
        print(f"  🤖 هوش مصنوعی: {AI_BOT_USERNAME}")
        print(f"  📈 تعداد کانال‌های تحت نظر: {len([ch for ch in TARGET_CHANNELS if ch in channel_entities])}")
        print(f"  🔧 تنظیمات سریع: MAX_RETRIES={MAX_RETRIES}, DELAY={RETRY_DELAY}s")
        
        await asyncio.gather(
            client.run_until_disconnected(),
            safe_monitor(),
            profile_updater()
        )
            
    except Exception as e:
        print(f"❌ خطای غیرمنتظره: {e}")
    finally:
        await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
