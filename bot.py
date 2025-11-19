from telethon import TelegramClient, functions
import asyncio
import random
from datetime import datetime
import os
import sys

# تنظیمات API

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
        return True
        
    except Exception as e:
        print(f"❌ خطا در آپدیت پروفایل: {e}")
        return False

async def main():
    try:
        print("🔄 در حال اتصال به تلگرام...")
        await client.start()
        
        if not await client.is_user_authorized():
            print("❌ session نامعتبر است")
            return
        
        me = await client.get_me()
        print(f"✅ وارد شدید: {me.first_name}")
        
        # آپدیت اولیه
        success = await update_profile()
        if success:
            print("🎉 اولین آپدیت موفقیت‌آمیز بود!")
        else:
            print("⚠️ اولین آپدیت ناموفق بود")
        
        # آپدیت هر دقیقه
        counter = 0
        while True:
            await asyncio.sleep(60)
            counter += 1
            success = await update_profile()
            
            if counter % 10 == 0:  # هر 10 دقیقه یکبار وضعیت چاپ شود
                print(f"📊 وضعیت: {counter} آپدیت انجام شده")
                
    except Exception as e:
        print(f"💥 خطای اصلی: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("🚀 شروع ربات آپدیت پروفایل...")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 ربات متوقف شد")
    except Exception as e:
        print(f"💥 خطای بحرانی: {e}")
