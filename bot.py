from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import sqlite3
from datetime import datetime, timedelta
import os
import threading
from flask import Flask

# ================= RENDER HEARTBEAT =================
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
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS bookings (user_id INTEGER, meeting_type TEXT, reason TEXT, price INTEGER, status TEXT, meeting_date TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS wallets (coin TEXT PRIMARY KEY, address TEXT, memo TEXT)")
conn.commit()

def get_wallet(coin):
    cursor.execute("SELECT address, memo FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    return row if row else ("NOT SET", None)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    keyboard = [[InlineKeyboardButton("🎯 Book Meeting", callback_data="book")]]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])
    await update.message.reply_text("Welcome 👋", reply_markup=InlineKeyboardMarkup(keyboard))

# ================= CALLBACKS =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # COPY FEATURE
    if data.startswith("copy_"):
        val = data.replace("copy_", "")
        await query.message.reply_text(f"`{val}`", parse_mode="MarkdownV2")
        await query.answer(text="Copied! ✅")
        return

    # ADMIN PANEL MAIN
    if data == "admin_panel" and is_admin(user_id):
        kb = [[InlineKeyboardButton("Edit BTC", callback_data="manage_BTC")],
              [InlineKeyboardButton("Edit ETH", callback_data="manage_ETH")],
              [InlineKeyboardButton("Edit USDT", callback_data="manage_USDT")],
              [InlineKeyboardButton("📢 Broadcast Message", callback_data="broadcast")]]
        await query.edit_message_text("🛠 **Admin Control Center**", reply_markup=InlineKeyboardMarkup(kb))

    # MANAGE COIN (SIMPLE UI)
    elif data.startswith("manage_") and is_admin(user_id):
        coin = data.split("_")[1]
        addr, memo = get_wallet(coin)
        kb = [[InlineKeyboardButton("📝 Set Address", callback_data=f"setaddr_{coin}")],
              [InlineKeyboardButton("📝 Set Memo", callback_data=f"setmemo_{coin}")],
              [InlineKeyboardButton("❌ Clear Memo", callback_data=f"clear_memo_{coin}")],
              [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]]
        await query.edit_message_text(f"💎 **{coin} Settings**\n\nAddr: `{addr}`\nMemo: `{memo if memo else 'None'}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("setaddr_") and is_admin(user_id):
        context.user_data["edit_target"] = (data.split("_")[1], "address")
        await query.edit_message_text(f"📥 Send the new **{data.split('_')[1]} Address**:")

    elif data.startswith("setmemo_") and is_admin(user_id):
        context.user_data["edit_target"] = (data.split("_")[1], "memo")
        await query.edit_message_text(f"📥 Send the new **{data.split('_')[1]} Memo**:")

    elif data.startswith("clear_memo_") and is_admin(user_id):
        coin = data.split("_")[2]
        cursor.execute("UPDATE wallets SET memo = NULL WHERE coin = ?", (coin,))
        conn.commit()
        await query.edit_message_text(f"✅ Memo for {coin} cleared.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"manage_{coin}")]]))

    # BROADCAST
    elif data == "broadcast" and is_admin(user_id):
        context.user_data["step"] = "broadcasting"
        await query.edit_message_text("📢 Send the message for ALL users:")

    # ORIGINAL GUIDE (RESTORED EXACTLY)
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
• Add Memo/Tag if required

After payment, return and confirm.
"""
        await query.message.reply_text(guide_text)
        return

    # USER BOOKING
    if data == "book":
        kb = [[InlineKeyboardButton("Meet & Greet", callback_data="type_meet")], [InlineKeyboardButton("Business", callback_data="type_business")]]
        await query.edit_message_text("Choose meeting type:", reply_markup=InlineKeyboardMarkup(kb))

    elif data in ["type_meet", "type_business"]:
        context.user_data["meeting_type"] = "Meet & Greet" if data == "type_meet" else "Business"
        context.user_data["step"] = "reason"
        await query.edit_message_text("Send your reason for the meeting:")

    elif data.startswith("pay_"):
        coin = data.split("_")[1]
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        price = 15000 if m_type == "Meet & Greet" else 20000
        addr, memo = get_wallet(coin)
        kb = [[InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_{addr}")]]
        if memo: kb.append([InlineKeyboardButton("📋 Copy Memo", callback_data=f"copy_{memo}")])
        kb.append([InlineKeyboardButton("📘 Payment Guide", callback_data=f"guide_{coin}")])
        kb.append([InlineKeyboardButton("✅ Confirm Payment", callback_data="confirm_payment")])
        m_txt = f"\n📝 **Memo:** `{memo}`" if memo else ""
        await query.message.reply_text(f"🧾 **Invoice**\nType: {m_type}\nAmount: ${price}\nCoin: {coin}\n\n📍 **Address:**\n`{addr}`{m_txt}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "confirm_payment":
        for admin in ADMIN_IDS:
            await context.bot.send_message(chat_id=admin, text=f"🧾 **New Payment Alert**\nUser: {user_id}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")]]))
        await query.edit_message_text("⏳ Awaiting admin approval...")

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
            "🎫 A VIP Fan Recognition Card will be issued.\n"
            "Status: CONFIRMED ✅"
        ))
        await query.edit_message_text("✅ Approved")

# ================= HANDLERS =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if is_admin(user_id) and context.user_data.get("edit_target"):
        coin, field = context.user_data.pop("edit_target")
        if field == "address":
            cursor.execute("INSERT INTO wallets (coin, address) VALUES (?, ?) ON CONFLICT(coin) DO UPDATE SET address=excluded.address", (coin, text))
        else:
            cursor.execute("UPDATE wallets SET memo = ? WHERE coin = ?", (text, coin))
        conn.commit()
        await update.message.reply_text(f"✅ {coin} {field} saved!")

    elif is_admin(user_id) and context.user_data.get("step") == "broadcasting":
        context.user_data["step"] = None
        cursor.execute("SELECT user_id FROM users")
        for (u,) in cursor.fetchall():
            try: await context.bot.send_message(chat_id=u, text=text)
            except: pass
        await update.message.reply_text("📢 Broadcast sent!")

    elif context.user_data.get("step") == "reason":
        context.user_data["step"] = None
        kb = [[InlineKeyboardButton("BTC", callback_data="pay_BTC")], [InlineKeyboardButton("ETH", callback_data="pay_ETH")], [InlineKeyboardButton("USDT", callback_data="pay_USDT")]]
        await update.message.reply_text("Choose payment method:", reply_markup=InlineKeyboardMarkup(kb))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    def run_f(): server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
    threading.Thread(target=run_f, daemon=True).start()
    app.run_polling(drop_pending_updates=True)
