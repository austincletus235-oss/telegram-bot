import os
from flask import Flask
server = Flask(__name__)

@server.route('/')
def health_check():
    return "Bot is alive!"
    
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

# ================= WALLET (FIXED FOR RENDER) =================
def get_wallet(coin):
    # 1. Check database first
    cursor.execute("SELECT address FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    if row:
        return row[0]
    
    # 2. Hardcoded defaults so it is NEVER "NOT SET" on Render
    defaults = {
        "USDT": "UQBO80Ku-tQvQMd2nXltilpR8hZrBgn7B_0_JlGjujn4hWOr",
        "BTC": "NOT SET",
        "ETH": "NOT SET"
    }
    return defaults.get(coin.upper(), "NOT SET")

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

    # ================= GUIDE =================
    if data.startswith("guide_"):
        coin = data.split("_")[1]
        guide_text = f"📘 Crypto Payment Guide ({coin})\n\n1️⃣ Open wallet\n2️⃣ Select {coin}\n3️⃣ Paste address\n4️⃣ Send exact amount."
        await query.message.reply_text(guide_text)
        return

    # ================= ADMIN PANEL =================
    if data == "admin_panel":
        if not is_admin(user_id):
            await query.edit_message_text("❌ Unauthorized")
            return
        await query.edit_message_text("🛠 Admin Panel Active")
        return

    # ================= BOOKING LOGIC =================
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
        await query.edit_message_text(f"Selected: {meeting_type}\n\nSend your reason for the meeting:")

    # ================= PAYMENT SELECTION =================
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
            f"🧾 Invoice\n\nType: {meeting_type}\nAmount: ${price}\nCoin: {coin}\n\n📥 Wallet:\n{wallet}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ================= CONFIRMATION =================
    elif data == "confirm_payment":
        meeting_type = context.user_data.get("meeting_type", "Meet & Greet")
        price = 15000 if meeting_type == "Meet & Greet" else 20000

        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🧾 Payment Pending\nUser: {user_id}\nType: {meeting_type}\nAmount: ${price}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")],
                    [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]
                ])
            )
        await query.edit_message_text("⏳ Awaiting admin approval...")

    # ================= APPROVAL =================
    elif data.startswith("approve_"):
        if not is_admin(user_id): return
        target_user = int(data.split("_")[1])
        meeting_date = datetime.now() + timedelta(days=5)
        await context.bot.send_message(
            chat_id=target_user,
            text=f"🎉 Payment Confirmed!\nMeeting Date: {meeting_date.strftime('%Y-%m-%d %H:%M')}\n\nYour VIP Fan Card will be shipped in 2 days."
        )
        await query.edit_message_text("✅ Approved")

    elif data.startswith("reject_"):
        if not is_admin(user_id): return
        target_user = int(data.split("_")[1])
        await context.bot.send_message(target_user, "❌ Payment rejected.")
        await query.edit_message_text("❌ Rejected")

# ================= TEXT HANDLER =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") == "reason":
        meeting_type = context.user_data.get("meeting_type")
        price = 15000 if meeting_type == "Meet & Greet" else 20000
        
        cursor.execute("INSERT INTO bookings (user_id, meeting_type, reason, price, status) VALUES (?, ?, ?, ?, ?)",
                       (update.effective_user.id, meeting_type, update.message.text, price, "pending"))
        conn.commit()
        context.user_data["step"] = None

        keyboard = [
            [InlineKeyboardButton("BTC", callback_data="pay_BTC")],
            [InlineKeyboardButton("ETH", callback_data="pay_ETH")],
            [InlineKeyboardButton("USDT", callback_data="pay_USDT")]
        ]
        await update.message.reply_text(f"Amount: ${price}\nChoose payment method:", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

print("Bot running...")
if __name__ == "__main__":
# 1. Start the bot (non-blocking)
app.run_polling(drop_pending_updates=True, close_loop=False)
    
# 2. Start the Flask server Render is scanning for
port = int(os.environ.get("PORT", 8000))
server.run(host='0.0.0.0', port=port)
        
    
