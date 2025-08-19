import random
import logging
import asyncio
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# بارگذاری env
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

user_tracking = {}

# جوایز و احتمال
prizes = [
    ("🧸 تدی", 0.3),
    ("❤️ قلب", 0.3),
    ("🌹 گل ۲۵ استارزی", 0.25),
    ("🎁 موشک ۵۰ استارزی", 0.15)
]

# شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎰 خوش اومدی! برای شرکت در گردونه باید ۴۰ استارز پرداخت کنی.\n\n/roll برای شروع")

# گردونه با انیمیشن
async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    # انتخاب نهایی
    final_gift = random.choices([p[0] for p in prizes], weights=[p[1] for p in prizes])[0]

    # ساخت کد پیگیری
    tracking_code = str(random.randint(1000000000, 9999999999))
    user_tracking[user_id] = {"code": tracking_code, "gift": final_gift, "status": "pending"}

    # پیام اولیه
    msg = await update.message.reply_text("🎰 گردونه در حال چرخش است...")

    # شبیه‌سازی چرخش (۵ بار تغییر متن)
    for i in range(5):
        rolling = random.sample([p[0] for p in prizes], len(prizes))  # ردیف تصادفی
        await msg.edit_text(" | ".join(rolling))
        await asyncio.sleep(0.7 + i*0.2)  # هر بار کندتر بشه

    # توقف روی جایزه اصلی
    await msg.edit_text(f"🎉 تبریک! شما برنده شدید:\n\n{final_gift}\n\nکد پیگیری شما: {tracking_code}", parse_mode="Markdown")

    # پیام به ادمین
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📥 کاربر {update.message.from_user.username} برنده شد!\n\nجایزه: {final_gift}\nکد پیگیری: {tracking_code}"
    )

# بررسی کدها (فقط ادمین)
async def baresy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    
    if not user_tracking:
        await update.message.reply_text("❌ هنوز کدی ثبت نشده.")
        return
    
    buttons = []
    for uid, data in user_tracking.items():
        status = "✅" if data["status"] == "done" else "⏳"
        buttons.append([
            InlineKeyboardButton(
                f"{data['code']} - {data['gift']} {status}",
                callback_data=f"confirm_{uid}"
            )
        ])
    
    await update.message.reply_text(
        "📋 لیست کدهای پیگیری:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# تایید هدیه توسط ادمین
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    uid = int(query.data.split("_")[1])
    if uid in user_tracking:
        user_tracking[uid]["status"] = "done"
        
        # پیام به کاربر
        await context.bot.send_message(
            chat_id=uid,
            text="🎁 گیفت شما ارسال شد ✅"
        )
        
        # آپدیت پیام ادمین
        await query.edit_message_text("✅ گیفت تأیید و ارسال شد.")

# ران اصلی
def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(API_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("baresy", baresy))
    app.add_handler(CallbackQueryHandler(confirm, pattern="confirm_"))
    
    app.run_polling()

if __name__ == "__main__":
    main()
