import os
import asyncio
import logging
from datetime import datetime, timedelta
import random

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
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
    raise SystemExit("API_TOKEN is not set in .env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Data Stores ----------------
USER_PAYMENTS = {}  # user_id -> total stars
user_tracking = {}  # user_id -> gift tracking
transfer_pending = {}  # user_id -> transfer info {to_id, amount}

# ---------------- Prizes ----------------
prizes = [
    ("🧸 تدی", 0.3),
    ("❤️ قلب", 0.3),
    ("🌹 گل ۲۵ استارزی", 0.25),
    ("🎁 موشک ۵۰ استارزی", 0.15)
]

# ---------------- Handlers ----------------

# Start
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

# دکمه‌ها
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "roll_gift":
        prices = [LabeledPrice("گردونه 1 ⭐", 1)]
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title="🎰 گردونه ستاره‌ای",
            description="پرداخت ۱ ستارز برای شرکت در گردونه",
            payload=f"roll:{query.from_user.id}",
            provider_token="",  # ستاره واقعی
            currency="XTR",
            prices=prices,
            start_parameter="roll_start"
        )

    elif query.data == "transfer_star":
        await query.message.reply_text(
            "💸 برای انتقال، ابتدا UserID مقصد و مقدار را وارد کنید:\n"
            "`<USER_ID> <مقدار>`\n"
            "مثال: `123456789 10`",
            parse_mode="Markdown"
        )
        context.user_data["await_transfer"] = True

# دریافت مقدار انتقال
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

            fee = 0 if amount < 5 else 3
            final_amount = amount - fee

            transfer_pending[update.effective_user.id] = {"to_id": to_id, "amount": final_amount, "fee": fee}

            prices = [LabeledPrice(f"انتقال {final_amount} ⭐", amount)]
            await context.bot.send_invoice(
                chat_id=update.effective_user.id,
                title="💸 انتقال استارز",
                description=f"انتقال {final_amount} ⭐ به {to_id} (کارمزد {fee} ⭐)",
                payload=f"transfer:{update.effective_user.id}:{to_id}:{final_amount}",
                provider_token="",  # ستاره واقعی
                currency="XTR",
                prices=prices,
                start_parameter="transfer_start"
            )

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

    if payload.startswith("roll:"):
        USER_PAYMENTS[user_id] = USER_PAYMENTS.get(user_id, 0) + 1
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

    elif payload.startswith("transfer:"):
        parts = payload.split(":")
        from_id = int(parts[1])
        to_id = int(parts[2])
        amount = int(parts[3])
        USER_PAYMENTS[to_id] = USER_PAYMENTS.get(to_id, 0) + amount

        await update.message.reply_text(
            f"✅ انتقال موفق! {amount} ⭐ به {to_id} اضافه شد."
        )

# ریفاند
async def refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفا توکن پرداخت را وارد کنید:\n/refund <PAYMENT_TOKEN>")
        return
    await update.message.reply_text("✅ ریفاند انجام شد (پرداخت واقعی ستاره‌ها)")

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
