from telethon import TelegramClient, events, functions
import asyncio
import time
import random
from datetime import datetime
import os

# تنظیمات API
api_id = 35312792
api_hash = '0536b75d8bbb77161edaba324dec570c'

client = TelegramClient('session_name', api_id, api_hash)

async def update_profile():
    """به‌روزرسانی نام پروفایل"""
    try:
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # استایل کردن زمان
        styled_time = current_time
        fraktur_map = {'0':'𝟎','1':'𝟏','2':'𝟐','3':'𝟑','4':'𝟒','5':'𝟓','6':'𝟔','7':'𝟕','8':'𝟖','9':'𝟗'}
        double_struck_map = {'0':'𝟘','1':'𝟙','2':'𝟚','3':'𝟛','4':'𝟜','5':'𝟝','6':'𝟞','7':'𝟟','8':'𝟠','9':'𝟡'}
        
        for i, char in enumerate(current_time):
            if char.isdigit():
                if i % 2 == 0:
                    styled_time = styled_time.replace(char, fraktur_map[char], 1)
                else:
                    styled_time = styled_time.replace(char, double_struck_map[char], 1)
        
        new_first_name = f"⏰ {styled_time}"
        
        await client(functions.account.UpdateProfileRequest(first_name=new_first_name))
        print(f"✅ پروفایل آپدیت شد: {new_first_name}")
        
    except Exception as e:
        print(f"❌ خطا در آپدیت پروفایل: {e}")

async def main():
    await client.start()
    
    if not await client.is_user_authorized():
        print("❌ session نامعتبر است")
        return
    
    me = await client.get_me()
    print(f"✅ وارد شدید: {me.first_name}")
    
    # آپدیت اولیه
    await update_profile()
    
    # آپدیت هر دقیقه
    while True:
        await asyncio.sleep(60)
        await update_profile()

if __name__ == '__main__':
    print("🚀 شروع ربات ساده...")
    asyncio.run(main())
