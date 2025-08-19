import os
import asyncio
import logging
import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
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

# ---------------- Data ----------------
USER_PAYMENTS = {}       # user_id -> total stars
USER_SUBSCRIPTIONS = {}  # user_id -> subscription expiration datetime
transfer_pending = {}    # user_id -> {"to_id": .., "amount": .., "fee": ..}

# ---------------- Gifts ----------------
prizes = [
    ("🧸 تدی", 0.3),
    ("❤️ قلب", 0.3),
    ("🌹 گل ۲۵ استارزی", 0.25),
    ("🎁 موشک ۵۰ استارزی", 0.15)
]

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎰 گردونه 1 ⭐", callback_data="roll_gift")],
        [InlineKeyboardButton("💸 انتقال استارز", callback_data="transfer_star")],
        [InlineKeyboardButton("📦 خرید اشتراک 1 ماهه — 1 ⭐", callback_data="buy_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎰 خوش آمدی! می‌تونی گردونه بزنی، استارز منتقل کنی یا اشتراک بخری.",
        reply_markup=reply_markup
    )

# ---------------- دکمه‌ها ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "roll_gift":
        prices = [LabeledPrice("گردونه 1 ⭐", 1)]
        await context.bot.send_invoice(
            chat_id=user_id,
            title="🎰 گردونه ستاره‌ای",
            description="پرداخت ۱ ستارز برای شرکت در گردونه",
            payload=f"roll:{user_id}",
            provider_token="",  # ستاره واقعی
            currency="XTR",
            prices=prices,
            start_parameter="roll_start"
        )

    elif query.data == "transfer_star":
        await query.message.reply_text(
            "💸 برای انتقال، UserID مقصد و مقدار را وارد کنید:\n`<USER_ID> <مقدار>`\nمثال: `123456789 10`",
            parse_mode="Markdown"
        )
        context.user_data["await_transfer"] = True

    elif query.data == "buy_subscription":
        prices = [LabeledPrice("اشتراک 1 ماهه سیگنال", 1)]
        await context.bot.send_invoice(
            chat_id=user_id,
            title="اشتراک سیگنال ارز دیجیتال",
            description="اشتراک ۱ ماهه ربات سیگنال ارز دیجیتال",
            payload=f"subscription:{user_id}",
            provider_token="",  # ستاره واقعی
            currency="XTR",
            prices=prices,
            start_parameter="subscription_start"
        )

# ---------------- دریافت مقدار انتقال ----------------
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

# ---------------- Precheckout ----------------
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

# ---------------- پرداخت موفق ----------------
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    user_id = update.effective_user.id

    # گردونه
    if payload.startswith("roll:"):
        USER_PAYMENTS[user_id] = USER_PAYMENTS.get(user_id, 0) + 1
        final_gift = random.choices([p[0] for p in prizes], weights=[p[1] for p in prizes])[0]
        tracking_code = str(random.randint(1000000000, 9999999999))
        await update.message.reply_text(f"🎉 برنده شدید: {final_gift}\nکد پیگیری: {tracking_code}")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📥 کاربر {update.message.from_user.username} برنده شد!\nجایزه: {final_gift}\nکد پیگیری: {tracking_code}"
        )

    # انتقال
    elif payload.startswith("transfer:"):
        parts = payload.split(":")
        from_id = int(parts[1])
        to_id = int(parts[2])
        amount = int(parts[3])
        USER_PAYMENTS[to_id] = USER_PAYMENTS.get(to_id, 0) + amount

        await update.message.reply_text(f"✅ انتقال موفق! {amount} ⭐ به {to_id} اضافه شد.")
        await context.bot.send_message(
            chat_id=to_id,
            text=f"🎉 شما {amount} ⭐ از طرف {update.message.from_user.username} دریافت کردید!"
        )

    # اشتراک
    elif payload.startswith("subscription:"):
        USER_SUBSCRIPTIONS[user_id] = datetime.now() + timedelta(days=30)
        USER_PAYMENTS[user_id] = USER_PAYMENTS.get(user_id, 0) + payment.total_amount
        await update.message.reply_text(
            f"✅ اشتراک یک ماهه فعال شد!\n"
            f"برای ریفاند: /refund {payment.telegram_payment_charge_id}\n"
            f"تاریخ انقضا: {USER_SUBSCRIPTIONS[user_id]}"
        )

# ---------------- ریفاند ----------------
async def refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفا توکن پرداخت را وارد کنید:\n/refund <PAYMENT_TOKEN>")
        return

    try:
        charge_id = context.args[0]
        user_id = update.effective_user.id

        success = await context.bot.refund_star_payment(
            user_id=user_id,
            telegram_payment_charge_id=charge_id
        )

        if success:
            await update.message.reply_text("✅ بازپرداخت موفق بود!")
            if user_id in USER_SUBSCRIPTIONS:
                del USER_SUBSCRIPTIONS[user_id]
        else:
            await update.message.reply_text("❌ بازپرداخت موفق نبود. توکن صحیح باشد یا قبلاً بازپرداخت انجام شده.")
    except Exception as e:
        await update.message.reply_text(f"خطا در ریفاند: {e}")

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
