import asyncio, requests, random, os, psutil
from datetime import datetime
from pyrogram import Client, filters
from dotenv import load_dotenv

# ---------------- Config ----------------
load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
session = os.getenv("SESSION_NAME", "selfbot")

# اختیاری‌ها
tg = os.getenv("TARGET_GROUP")
target_group = int(tg) if tg else None

ff = os.getenv("FORWARD_FROM")
forward_from = int(ff) if ff else None

ft = os.getenv("FORWARD_TO")
forward_to = int(ft) if ft else None

media_save_path = os.getenv("MEDIA_SAVE_PATH", "downloads")

app = Client(session, api_id=api_id, api_hash=api_hash)

# ========== آپدیت ساعت کنار اسم ==========
async def update_name():
    while True:
        now = datetime.now().strftime("%H:%M")
        try:
            await app.update_profile(first_name=f"⌚ {now} | Kia")
        except Exception as e:
            print("خطا در تغییر اسم:", e)
        await asyncio.sleep(60)

# ========== دستورات پایه ==========
@app.on_message(filters.me & filters.command("ping", prefixes="/"))
async def ping(_, msg):
    await msg.edit("✅ Online!")

@app.on_message(filters.me & filters.command("setbio", prefixes="/"))
async def set_bio(_, msg):
    text = " ".join(msg.command[1:])
    await app.update_profile(bio=text)
    await msg.edit("🔄 بیو آپدیت شد!")

@app.on_message(filters.me & filters.command("setname", prefixes="/"))
async def set_name(_, msg):
    text = " ".join(msg.command[1:])
    await app.update_profile(first_name=text)
    await msg.edit("🔄 اسم آپدیت شد!")

@app.on_message(filters.me & filters.command("price", prefixes="/"))
async def price(_, msg):
    if len(msg.command) < 2:
        return await msg.edit("❌ استفاده: `/price bitcoin`")
    coin = msg.command[1].lower()
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"
    r = requests.get(url).json()
    if coin in r:
        await msg.edit(f"💰 {coin.upper()} = {r[coin]['usd']}$")
    else:
        await msg.edit("❌ ارز پیدا نشد!")

@app.on_message(filters.me & filters.command("status", prefixes="/"))
async def status(_, msg):
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    await msg.edit(f"📊 وضعیت سیستم:\n🖥 CPU: {cpu}%\n💾 RAM: {ram}%\n⏰ زمان: {now}")

# ========== اتو ریپلای ==========
@app.on_message(filters.private & ~filters.me)
async def auto_reply(_, msg):
    text = msg.text.lower()
    if "سلام" in text:
        await msg.reply("سلام ✌️")
    elif "خوبی" in text:
        await msg.reply("مرسی تو خوبی؟")
    elif "btc" in text:
        await msg.reply("برای قیمت بیت‌کوین دستور `/price bitcoin` رو بزن.")

# ========== کازینو فان ==========
@app.on_message(filters.me & filters.command("casino", prefixes="/"))
async def casino(_, msg):
    emojis = ["🎰777🎰", "🎲", "🍒", "💎", "🍀", "🔥"]
    await msg.edit(random.choice(emojis))

# ========== اسپم دستی ==========
@app.on_message(filters.me & filters.command("spam", prefixes="/"))
async def spam(_, msg):
    try:
        count = int(msg.command[1])
        text = " ".join(msg.command[2:])
    except:
        return await msg.edit("❌ `/spam تعداد متن`")
    await msg.delete()
    for _ in range(count):
        await app.send_message(msg.chat.id, text)
        await asyncio.sleep(0.3)

# ========== اسپم خودکار ==========
auto_spam_on = False

@app.on_message(filters.me & filters.command("autospam", prefixes="/"))
async def start_autospam(_, msg):
    global auto_spam_on
    if not target_group:
        return await msg.edit("❌ TARGET_GROUP تو .env تنظیم نشده!")
    auto_spam_on = True
    await msg.edit("♻️ اسپم خودکار فعال شد.")

    while auto_spam_on:
        text = "🎰777🎰"
        for _ in range(3):
            await app.send_message(target_group, text)
            await asyncio.sleep(0.5)
        await asyncio.sleep(3)

@app.on_message(filters.me & filters.command("stopspam", prefixes="/"))
async def stop_autospam(_, msg):
    global auto_spam_on
    auto_spam_on = False
    await msg.edit("⛔ اسپم خودکار متوقف شد.")

# ========== سیو خودکار مدیا ==========
@app.on_message(filters.media & ~filters.me)
async def save_media(_, msg):
    if not os.path.exists(media_save_path):
        os.makedirs(media_save_path)
    await msg.download(file_name=media_save_path)
    print(f"📥 مدیا ذخیره شد: {msg.media}")

# ========== فوروارد خودکار ==========
@app.on_message(filters.chat(forward_from))
async def forward_auto(_, msg):
    if not forward_to:
        return
    await msg.copy(forward_to)

# ========== زمان‌بندی پیام ==========
@app.on_message(filters.me & filters.command("schedule", prefixes="/"))
async def schedule(_, msg):
    try:
        time_str = msg.command[1]  # فرمت HH:MM
        text = " ".join(msg.command[2:])
        await msg.edit(f"⏰ پیام زمان‌بندی شد برای {time_str}")
        while True:
            now = datetime.now().strftime("%H:%M")
            if now == time_str:
                await app.send_message(msg.chat.id, text)
                break
            await asyncio.sleep(20)
    except:
        await msg.edit("❌ `/schedule HH:MM متن`")

# ========== ضد اسپم PV ==========
@app.on_message(filters.private & ~filters.me)
async def anti_spam(_, msg):
    bad_words = ["تبلیغ", "کانال", "رایگان", "کلیک"]
    if any(w in msg.text.lower() for w in bad_words):
        await msg.delete()
        await msg.chat.block()

# ========== ران سلف ==========
async def main():
    await app.start()
    asyncio.create_task(update_name())
    print("🤖 SelfBot Full Option Running...")
    await asyncio.get_event_loop().create_future()

app.run(main())
