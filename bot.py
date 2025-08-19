import os
import asyncio
import logging
from datetime import datetime, timedelta
import random

from dotenv import load_dotenv
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters
)

# -------------------- Config --------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set in .env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------- Data Stores --------------------
USER_PAYMENTS = {}       # user_id -> total stars
PAYMENT_HISTORY = {}     # telegram_payment_charge_id -> {user_id, amount, refunded(bool)}
transfer_pending = {}    # user_id -> {"to_id": ..., "amount": ...}

# -------------------- گردونه / جوایز --------------------
prizes = [
    ("🧸 تدی", 0.3),
    ("❤️ قلب", 0.3),
    ("🌹 گل ۲۵ استارزی", 0.25),
    ("🎁 موشک ۵۰ استارزی", 0.15)
]

# -------------------- Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎰 خوش اومدی! برای شرکت در گردونه ۱ ستاره پرداخت کنید.")

async def roll_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = [LabeledPrice("گردونه 1 ⭐", 1)]
    await context.bot.send_invoice(
        chat_id=update.effective_user.id,
        title="گردونه ستاره‌ای",
        description="پرداخت ۱ ستاره برای شرکت در گردونه",
        payload=f"roll:{update.effective_user.id}",
        provider_token="",  # ستاره واقعی
        currency="XTR",
        prices=prices,
        start_parameter="roll_start"
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    token = payment.telegram_payment_charge_id

    # ثبت پرداخت واقعی
    PAYMENT_HISTORY[token] = {"user_id": user_id, "amount": payment.total_amount, "refunded": False}
    USER_PAYMENTS[user_id] = USER_PAYMENTS.get(user_id, 0) + payment.total_amount

    # گردونه
    payload = payment.invoice_payload
    if payload.startswith("roll:"):
        final_gift = random.choices([p[0] for p in prizes], weights=[p[1] for p in prizes])[0]
        tracking_code = str(random.randint(1000000000, 9999999999))
        msg = await update.message.reply_text("🎰 گردونه در حال چرخش است...")
        for i in range(5):
            rolling = random.sample([p[0] for p in prizes], len(prizes))
            await msg.edit_text(" | ".join(rolling))
            await asyncio.sleep(0.7 + i*0.2)
        await msg.edit_text(f"🎉 برنده شدید:\n{final_gift}\nکد پیگیری: {tracking_code}")

        await update.message.reply_text(f"✅ برای ریفاند: /refund {token}")

# -------------------- ریفاند --------------------
async def refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفا توکن پرداخت را وارد کنید:\n/refund <PAYMENT_TOKEN>")
        return

    token = context.args[0]
    if token not in PAYMENT_HISTORY:
        await update.message.reply_text("❌ توکن نامعتبر است.")
        return
    if PAYMENT_HISTORY[token]["refunded"]:
        await update.message.reply_text("❌ این پرداخت قبلا بازپرداخت شده.")
        return

    user_id = PAYMENT_HISTORY[token]["user_id"]
    amount = PAYMENT_HISTORY[token]["amount"]

    # برگرداندن ستاره به کاربر
    if user_id in USER_PAYMENTS:
        USER_PAYMENTS[user_id] -= amount
        PAYMENT_HISTORY[token]["refunded"] = True
        await update.message.reply_text(f"✅ بازپرداخت موفق! {amount} ⭐ از حساب شما کسر شد.")
    else:
        await update.message.reply_text("❌ خطا در بازپرداخت.")

# -------------------- انتقال ستارز --------------------
async def transfer_star(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💸 برای انتقال، فرمت را وارد کنید:\n<USER_ID> <مقدار>")
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
            from_id = update.effective_user.id
            if USER_PAYMENTS.get(from_id, 0) < amount:
                await update.message.reply_text("❌ ستاره کافی ندارید.")
                return

            # کم کردن از فرستنده و اضافه کردن به گیرنده
            USER_PAYMENTS[from_id] -= amount
            USER_PAYMENTS[to_id] = USER_PAYMENTS.get(to_id, 0) + amount

            await update.message.reply_text(f"✅ انتقال موفق! {amount} ⭐ به {to_id} اضافه شد.")
            context.user_data["await_transfer"] = False
        except Exception:
            await update.message.reply_text("❌ فرمت اشتباه است. دوباره تلاش کنید.")

# -------------------- Main --------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("roll", roll_gift))
    app.add_handler(CommandHandler("refund", refund_command))
    app.add_handler(CommandHandler("transfer", transfer_star))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
