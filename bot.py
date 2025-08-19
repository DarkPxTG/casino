import os
import asyncio
import logging
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ---------------- Config ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set in .env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Data Stores ----------------
USER_PAYMENTS = {}        # user_id -> total stars
PAYMENT_HISTORY = {}      # payment_token -> {user_id, amount, used}
user_tracking = {}        # user_id -> gift tracking
transfer_pending = {}     # user_id -> transfer info {to_id, amount}

# ---------------- Prizes ----------------
prizes = [
    ("🧸 تدی", 0.3),
    ("❤️ قلب", 0.3),
    ("🌹 گل ۲۵ استارزی", 0.25),
    ("🎁 موشک ۵۰ استارزی", 0.15)
]

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎰 شروع گردونه — 1 ⭐", callback_data="roll_gift")],
        [InlineKeyboardButton("💸 انتقال استارز", callback_data="transfer_star")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎰 خوش اومدی! برای شرکت در گردونه ابتدا ۱ ستارز پرداخت کنید یا استارز خود را انتقال دهید.",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "roll_gift":
        prices = [LabeledPrice("گردونه 1 ⭐", 1)]
        payload = f"roll:{query.from_user.id}:{random.randint(100000, 999999)}"
        # ذخیره توکن پرداخت
        PAYMENT_HISTORY[payload.split(":")[2]] = {"user_id": query.from_user.id, "amount": 1, "used": False}
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title="🎰 گردونه ستاره‌ای",
            description="پرداخت ۱ ستارز برای شرکت در گردونه",
            payload=payload,
            provider_token="",  # ستاره واقعی
            currency="XTR",
            prices=prices,
            start_parameter="roll_start"
        )

    elif query.data == "transfer_star":
        await query.message.reply_text(
            "💸 برای انتقال، ابتدا UserID مقصد و مقدار را وارد کنید:\n"
            "`<USER_ID> <مقدار>`\nمثال: `123456789 10`",
            parse_mode="Markdown"
        )
        context.user_data["await_transfer"] = True

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_transfer"):
        try:
            parts = update.message.text.strip().split()
            if len(parts) != 2:
                raise ValueError
            to_id = int(parts[0])
            amount = int(parts[1])
            if amount <= 0:
                await update.message.reply_text("❌ مقدار باید بیشتر از 0 باشد.")
                return
            if USER_PAYMENTS.get(update.effective_user.id, 0) < amount:
                await update.message.reply_text("❌ ستاره کافی ندارید.")
                return

            # کم کردن از فرستنده
            USER_PAYMENTS[update.effective_user.id] -= amount
            # اضافه کردن به گیرنده
            USER_PAYMENTS[to_id] = USER_PAYMENTS.get(to_id, 0) + amount

            await update.message.reply_text(f"✅ انتقال موفق! {amount} ⭐ به {to_id} اضافه شد.")
            context.user_data["await_transfer"] = False
        except Exception:
            await update.message.reply_text("❌ فرمت صحیح نیست. دوباره تلاش کنید.")

# Precheckout
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

# پرداخت موفق
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    user_id = update.effective_user.id
    token = payload.split(":")[2]  # توکن ذخیره شده

    # بررسی و ثبت پرداخت
    if token in PAYMENT_HISTORY and not PAYMENT_HISTORY[token]["used"]:
        USER_PAYMENTS[user_id] = USER_PAYMENTS.get(user_id, 0) + payment.total_amount
        PAYMENT_HISTORY[token]["used"] = True

        if payload.startswith("roll:"):
            final_gift = random.choices([p[0] for p in prizes], weights=[p[1] for p in prizes])[0]
            tracking_code = str(random.randint(1000000000, 9999999999))
            user_tracking[user_id] = {"code": tracking_code, "gift": final_gift, "status": "pending"}

            msg = await update.message.reply_text("🎰 گردونه در حال چرخش است...")
            for i in range(5):
                rolling = random.sample([p[0] for p in prizes], len(prizes))
                await msg.edit_text(" | ".join(rolling))
                await asyncio.sleep(0.7 + i*0.2)
            await msg.edit_text(f"🎉 تبریک! برنده شدید:\n\n{final_gift}\n\nکد پیگیری: {tracking_code}")

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📥 کاربر {update.message.from_user.username} برنده شد!\nجایزه: {final_gift}\nکد پیگیری: {tracking_code}"
            )

# ریفاند واقعی
async def refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفا توکن پرداخت را وارد کنید:\n/refund <PAYMENT_TOKEN>")
        return
    token = context.args[0]
    if token not in PAYMENT_HISTORY:
        await update.message.reply_text("❌ توکن نامعتبر است.")
        return
    if PAYMENT_HISTORY[token]["used"] is False:
        await update.message.reply_text("❌ این پرداخت قبلا بازپرداخت شده است.")
        return

    user_id = PAYMENT_HISTORY[token]["user_id"]
    amount = PAYMENT_HISTORY[token]["amount"]

    # ریفاند ستاره
    USER_PAYMENTS[user_id] -= amount
    PAYMENT_HISTORY[token]["used"] = False

    await update.message.reply_text(f"✅ بازپرداخت موفق بود! {amount} ⭐ از حساب شما کم شد.")

# ---------------- Main ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refund", refund_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
