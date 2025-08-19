import random
import logging
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, MessageHandler, ContextTypes, filters, ConversationHandler
)

# -------------------- Config --------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not BOT_TOKEN or not ADMIN_ID:
    raise SystemExit("BOT_TOKEN or ADMIN_ID not set in .env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------- Data Stores --------------------
user_tracking = {}        # user_id -> current spin
USER_PAYMENTS = {}        # user_id -> total stars
TRANSFER_PENDING = {}     # user_id -> {"to": target_id, "amount": x}

# -------------------- Prizes --------------------
prizes = [
    ("🧸 تدی", 0.3),
    ("❤️ قلب", 0.3),
    ("🌹 گل ۲۵ استارزی", 0.25),
    ("🎁 موشک ۵۰ استارزی", 0.15)
]

# -------------------- States for ConversationHandler --------------------
ENTER_TARGET_ID, ENTER_AMOUNT = range(2)

# -------------------- Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎰 شروع گردونه (۱ ⭐)", callback_data="buy_spin")],
        [InlineKeyboardButton("💸 انتقال استارز", callback_data="transfer_start")]
    ]
    await update.message.reply_text(
        "سلام! ربات آماده است. انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# -------------------- Spin Handlers --------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy_spin":
        prices = [LabeledPrice("گردونه 1 ستاره", 1)]
        await context.bot.send_invoice(
            chat_id=user_id,
            title="پرداخت ۱ ستاره برای گردونه",
            description="برای شروع گردونه ۱ ستاره پرداخت کنید",
            payload=f"spin:{user_id}",
            provider_token="",  # ستاره‌ها
            currency="XTR",
            prices=prices,
            start_parameter="spin_start"
        )

    elif query.data == "transfer_start":
        await query.message.reply_text("📥 لطفا ابتدا **User ID مقصد** را وارد کنید:")
        return ENTER_TARGET_ID


# -------------------- Transfer Conversation --------------------
async def enter_target_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = update.message.text
    if not target_id.isdigit():
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")
        return ENTER_TARGET_ID
    context.user_data["transfer_target"] = int(target_id)
    await update.message.reply_text("💰 حالا مقدار استارز برای انتقال را وارد کنید:")
    return ENTER_AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount_text = update.message.text
    if not amount_text.isdigit():
        await update.message.reply_text("❌ لطفاً عدد معتبر وارد کنید.")
        return ENTER_AMOUNT

    amount = int(amount_text)
    target_id = context.user_data["transfer_target"]
    sender_id = update.effective_user.id

    # ثبت تراکنش موقت
    TRANSFER_PENDING[sender_id] = {"to": target_id, "amount": amount}

    prices = [LabeledPrice(f"انتقال {amount} ستاره (کارمزد ۳ ⭐)", amount)]
    await context.bot.send_invoice(
        chat_id=sender_id,
        title=f"انتقال {amount} ستاره",
        description=f"{amount} ستاره به {target_id} (۳ ستاره کارمزد)",
        payload=f"transfer:{sender_id}",
        provider_token="",  # ستاره‌ها
        currency="XTR",
        prices=prices,
        start_parameter="transfer_start"
    )

    return ConversationHandler.END


# -------------------- Payment Callbacks --------------------
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload.startswith(("spin:", "transfer:")):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="پرداخت نامعتبر")


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    payload = payment.invoice_payload

    if payload.startswith("spin:"):
        # ثبت پرداخت کاربر
        USER_PAYMENTS[user_id] = USER_PAYMENTS.get(user_id, 0) + payment.total_amount
        await update.message.reply_text("✅ پرداخت موفق بود! گردونه شروع می‌شود...")
        await run_spin(update, context, user_id)

    elif payload.startswith("transfer:"):
        sender_id = int(payload.split(":")[1])
        trans = TRANSFER_PENDING.get(sender_id)
        if not trans:
            await update.message.reply_text("❌ تراکنش پیدا نشد.")
            return

        target_id = trans["to"]
        amount = trans["amount"]
        fee = 3
        transferred_amount = amount - fee

        # ثبت موجودی مقصد
        USER_PAYMENTS[target_id] = USER_PAYMENTS.get(target_id, 0) + transferred_amount
        USER_PAYMENTS[sender_id] = USER_PAYMENTS.get(sender_id, 0) + 0  # فقط ثبت جهت ریفاند

        await update.message.reply_text(
            f"✅ انتقال موفق بود!\nکارمزد: {fee} ستاره\n"
            f"{transferred_amount} ستاره به {target_id} اضافه شد."
        )
        if target_id not in USER_PAYMENTS:
            USER_PAYMENTS[target_id] = transferred_amount
        else:
            USER_PAYMENTS[target_id] += transferred_amount

        del TRANSFER_PENDING[sender_id]


# -------------------- Spin Logic --------------------
async def run_spin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    final_gift = random.choices([p[0] for p in prizes], weights=[p[1] for p in prizes])[0]
    tracking_code = str(random.randint(1000000000, 9999999999))
    user_tracking[user_id] = {"code": tracking_code, "gift": final_gift, "status": "pending"}

    msg = await context.bot.send_message(chat_id=user_id, text="🎰 گردونه در حال چرخش است...")

    for i in range(5):
        rolling = random.sample([p[0] for p in prizes], len(prizes))
        await msg.edit_text(" | ".join(rolling))
        await asyncio.sleep(0.7 + i*0.2)

    await msg.edit_text(f"🎉 تبریک! شما برنده شدید:\n\n{final_gift}\n\nکد پیگیری شما: {tracking_code}")

    # اطلاع ادمین
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📥 کاربر {update.effective_user.username} برنده شد!\nجایزه: {final_gift}\nکد پیگیری: {tracking_code}"
    )


# -------------------- Refund --------------------
async def refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفاً توکن پرداخت را وارد کنید:\n/refund <PAYMENT_TOKEN>")
        return
    charge_id = context.args[0]
    user_id = update.effective_user.id

    try:
        success = await context.bot.refund_star_payment(user_id=user_id, telegram_payment_charge_id=charge_id)
        if success:
            await update.message.reply_text("✅ بازپرداخت موفق بود!")
        else:
            await update.message.reply_text("❌ بازپرداخت موفق نبود.")
    except Exception as e:
        await update.message.reply_text(f"خطا در ریفاند: {e}")


# -------------------- Main --------------------
def main():
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="transfer_start")],
        states={
            ENTER_TARGET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_target_id)],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
        },
        fallbacks=[]
    )

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refund", refund_command))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="buy_spin"))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
