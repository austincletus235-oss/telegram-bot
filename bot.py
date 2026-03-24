from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import sqlite3
from datetime import datetime, timedelta
import os
import threading
import urllib.request
import json
from flask import Flask

# ================= RENDER HEARTBEAT =================
server = Flask(__name__)
@server.route('/')
def health_check(): return "Alive", 200

# ================= SETTINGS =================
TOKEN = "8681446523:AAHs42JckBFG_n-OYsASEbv-6Q4eFUlE5tw"
ADMIN_IDS = [7936558915]

def is_admin(user_id): return user_id in ADMIN_IDS

# ================= BTC PRICE CONVERTER =================
def get_btc_amount(usd_amount):
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        data = json.loads(response.read())
        btc_price = float(data['price'])
        return f"{round(usd_amount / btc_price, 6)} BTC"
    except Exception:
        return f"${usd_amount} (BTC equivalent)"

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS wallets (coin TEXT PRIMARY KEY, address TEXT, memo TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, rej_msg TEXT, price_meet INTEGER, price_biz INTEGER)")
cursor.execute("INSERT OR IGNORE INTO settings (id, price_meet, price_biz) VALUES (1, 15000, 20000)")
conn.commit()

def get_wallet(coin):
    cursor.execute("SELECT address, memo FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    return row if row else ("NOT SET", None)

def get_prices():
    cursor.execute("SELECT price_meet, price_biz FROM settings WHERE id=1")
    res = cursor.fetchone()
    return res if res else (15000, 20000)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

    user = update.effective_user
    username = f"@{user.username}" if user.username else "No Username"
    if not is_admin(user_id):
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin,
                    text=f"🔔 **New User Alert!**\n👤 **Name:** {user.first_name}\n🔗 **Username:** {username}\n🆔 **ID:** `{user_id}`",
                    parse_mode="Markdown"
                )
            except: pass

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

    if data.startswith("copy_"):
        val = data.replace("copy_", "")
        await query.message.reply_text(f"`{val}`", parse_mode="MarkdownV2")
        return

    # ADMIN PANEL
    if data == "admin_panel" and is_admin(user_id):
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        kb = [[InlineKeyboardButton("💰 Edit Prices", callback_data="edit_prices")],
              [InlineKeyboardButton("💳 Edit Wallets/Bank", callback_data="wallet_menu")],
              [InlineKeyboardButton("💬 DM a User", callback_data="dm_user")],
              [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
              [InlineKeyboardButton("📝 Edit Rejection Msg", callback_data="set_rej_msg")]]
        await query.edit_message_text(f"📊 **Admin Panel**\nTotal Active Users: `{count}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "wallet_menu" and is_admin(user_id):
        kb = [[InlineKeyboardButton("BTC", callback_data="manage_BTC"), InlineKeyboardButton("ETH", callback_data="manage_ETH")],
              [InlineKeyboardButton("USDT", callback_data="manage_USDT"), InlineKeyboardButton("Bank", callback_data="manage_Bank")],
              [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]]
        await query.edit_message_text("Select asset to edit:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "edit_prices" and is_admin(user_id):
        p_meet, p_biz = get_prices()
        kb = [[InlineKeyboardButton(f"Meet & Greet (${p_meet})", callback_data="setp_meet")],
              [InlineKeyboardButton(f"Business (${p_biz})", callback_data="setp_biz")],
              [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]]
        await query.edit_message_text("Select price to update:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("setp_") and is_admin(user_id):
        context.user_data["step"] = data
        await query.edit_message_text("🔢 Send the new price (Numbers only):")

    elif data == "dm_user" and is_admin(user_id):
        context.user_data["step"] = "dm_id"
        await query.edit_message_text("🆔 Send the **User ID** you want to message:")

    # NEW: Quick Reply Button handler
    elif data.startswith("reply_") and is_admin(user_id):
        target = data.split("_")[1]
        context.user_data["target_dm"] = target
        context.user_data["step"] = "dm_msg"
        await query.message.reply_text(f"📝 Now send your reply to user `{target}`:")

    elif data.startswith("manage_") and is_admin(user_id):
        coin = data.split("_")[1]
        addr, memo = get_wallet(coin)
        kb = [[InlineKeyboardButton("📝 Set Address/Acct", callback_data=f"setaddr_{coin}")],
              [InlineKeyboardButton("📝 Set Memo/BankName", callback_data=f"setmemo_{coin}")],
              [InlineKeyboardButton("⬅️ Back", callback_data="wallet_menu")]]
        await query.edit_message_text(f"💎 **{coin} Settings**\nAddr: `{addr}`\nMemo: `{memo}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("setaddr_") and is_admin(user_id):
        context.user_data["edit_target"] = (data.split("_")[1], "address")
        await query.edit_message_text(f"📥 Send new address for {data.split('_')[1]}:")

    elif data.startswith("setmemo_") and is_admin(user_id):
        context.user_data["edit_target"] = (data.split("_")[1], "memo")
        await query.edit_message_text(f"📥 Send new memo for {data.split('_')[1]}:")

    elif data == "set_rej_msg" and is_admin(user_id):
        context.user_data["step"] = "setting_rej_msg"
        await query.edit_message_text("📥 Send the new Rejection Message:")

    elif data == "broadcast" and is_admin(user_id):
        context.user_data["step"] = "broadcasting"
        await query.edit_message_text("📢 Send the message for ALL users:")

    elif data.startswith("guide_"):
        coin = data.split("_")[1]
        guide_text = (
            f"📘 **How to Pay with {coin}**\n\n"
            "1️⃣ Open your crypto exchange or wallet app.\n"
            f"2️⃣ Tap **Send** or **Withdraw** and choose **{coin}**.\n"
            "3️⃣ Select the correct **Network** (Critical!).\n"
            "4️⃣ Paste the exact Wallet Address from your invoice.\n"
            "5️⃣ Add the **Memo/Tag** (ONLY if your invoice shows one).\n"
            "6️⃣ Enter the exact amount, cover any network fees, and send.\n\n"
            "⚠️ **IMPORTANT:** Always double-check the network and address before confirming."
        )
        await query.message.reply_text(guide_text, parse_mode="Markdown")

    # USER UI
    elif data == "book":
        p_meet, p_biz = get_prices()
        kb = [[InlineKeyboardButton(f"Meet & Greet (${p_meet})", callback_data="type_meet")], 
              [InlineKeyboardButton(f"Business (${p_biz})", callback_data="type_business")]]
        await query.edit_message_text("Choose meeting type:", reply_markup=InlineKeyboardMarkup(kb))

    elif data in ["type_meet", "type_business"]:
        context.user_data["meeting_type"] = "Meet & Greet" if data == "type_meet" else "Business"
        context.user_data["step"] = "reason"
        await query.edit_message_text("Send your reason for the meeting:")

    elif data.startswith("pay_"):
        coin = data.split("_")[1]
        user = query.from_user
        if not is_admin(user_id):
            for admin in ADMIN_IDS:
                try: await context.bot.send_message(chat_id=admin, text=f"💳 **Payment Activity!**\nUser: {user.first_name}\nAction: Viewing **{coin}**.")
                except: pass

        p_meet, p_biz = get_prices()
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        price = p_meet if m_type == "Meet & Greet" else p_biz
        addr, memo = get_wallet(coin)

        if coin == "Bank" and addr == "NOT SET":
            await query.message.reply_text("Unavailable due to network issues.")
            return

        display_coin = {"USDT": "USDT (TRON TRC20)", "ETH": "ETH (Ethereum ERC20)", "Bank": "Bank Transfer", "BTC": "BTC"}.get(coin, coin)
        display_price = get_btc_amount(price) if coin == "BTC" else f"${price}"

        kb = [[InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_{addr}")]]
        if memo: kb.append([InlineKeyboardButton("📋 Copy Memo", callback_data=f"copy_{memo}")])
        if coin != "Bank": kb.append([InlineKeyboardButton("📘 Payment Guide", callback_data=f"guide_{coin}")])
        kb.append([InlineKeyboardButton("✅ Confirm Payment", callback_data="confirm_payment")])
        m_txt = f"\n📝 **Memo:** `{memo}`" if memo else ""
        await query.message.reply_text(f"🧾 **Invoice**\nType: {m_type}\nAmount: {display_price}\nCoin: {display_coin}\n\n📍 **Address:**\n`{addr}`{m_txt}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "confirm_payment":
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")],
                  [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]]
            await context.bot.send_message(chat_id=admin, text=f"🧾 **Payment Alert**\nUser: {user_id}", reply_markup=InlineKeyboardMarkup(kb))
        await query.edit_message_text("⏳ Awaiting admin approval...")

    elif data.startswith("approve_") and is_admin(user_id):
        target = int(data.split("_")[1])
        meeting_date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d %H:%M')
        vip_message = "🎉 **Payment Confirmed Successfully**\n\n━━━━━━━━━━━━━━━━━━\n👑 **VIP CONFIRMATION NOTICE**\n━━━━━━━━━━━━━━━━━━\n\nDear User,\n\nYour payment has been successfully verified. Your exclusive meeting with **Morgan Wallen** is now officially scheduled.\n\n📅 **Scheduled Date:** {0}\n\n🎫 **VIP Recognition Card:**\nA VIP Fan Card will be issued as your official form of recognition and identification for the meeting. This card will be prepared and shipped to you within the next **2 days**.\n\n📦 **Shipping & Delivery:**\nPersonal details such as your **Full Name, Shipping Address, and Phone Number** must be provided by you once the card is ready for dispatch to ensure a secure delivery.\n\nThank you for your trust. We look forward to delivering a premium experience.\n\n━━━━━━━━━━━━━━━━━━\nStatus: **CONFIRMED ✅**".format(meeting_date)
        await context.bot.send_message(chat_id=target, text=vip_message, parse_mode="Markdown")
        await query.edit_message_text(f"✅ Approved for {target}")

    elif data.startswith("reject_") and is_admin(user_id):
        target = int(data.split("_")[1])
        cursor.execute("SELECT rej_msg FROM settings WHERE id=1")
        row = cursor.fetchone()
        rej_txt = row[0] if row and row[0] else "❌ **Payment Not Received**\n\nWe were unable to verify your transaction. Please check your details and try again."
        await context.bot.send_message(chat_id=target, text=rej_txt, parse_mode="Markdown")
        await query.edit_message_text(f"❌ Rejected for {target}")

# ================= HANDLERS =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    step = context.user_data.get("step")

    if is_admin(user_id):
        if context.user_data.get("edit_target"):
            coin, field = context.user_data.pop("edit_target")
            if field == "address": cursor.execute("INSERT INTO wallets (coin, address) VALUES (?, ?) ON CONFLICT(coin) DO UPDATE SET address=excluded.address", (coin, text))
            else: cursor.execute("UPDATE wallets SET memo = ? WHERE coin = ?", (text, coin))
            conn.commit()
            await update.message.reply_text(f"✅ {coin} {field} saved!")
        
        elif step == "setp_meet":
            cursor.execute("UPDATE settings SET price_meet = ? WHERE id = 1", (int(text),))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text(f"✅ Meet & Greet price set to ${text}")

        elif step == "setp_biz":
            cursor.execute("UPDATE settings SET price_biz = ? WHERE id = 1", (int(text),))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text(f"✅ Business price set to ${text}")

        elif step == "dm_id":
            context.user_data["target_dm"] = text
            context.user_data["step"] = "dm_msg"
            await update.message.reply_text(f"📝 Now send the message for user `{text}`:")

        elif step == "dm_msg":
            target = context.user_data.pop("target_dm")
            context.user_data["step"] = None
            try:
                await context.bot.send_message(chat_id=target, text=text, parse_mode="Markdown")
                await update.message.reply_text("✅ Message sent!")
            except: await update.message.reply_text("❌ User blocked bot or ID wrong.")

        elif step == "setting_rej_msg":
            cursor.execute("UPDATE settings SET rej_msg = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ Rejection Message saved!")

        elif step == "broadcasting":
            cursor.execute("SELECT user_id FROM users")
            for (u,) in cursor.fetchall():
                try: await context.bot.send_message(chat_id=u, text=text)
                except: pass
            context.user_data["step"] = None
            await update.message.reply_text("📢 Broadcast sent!")

    elif step == "reason":
        context.user_data["step"] = None
        kb = [[InlineKeyboardButton("BTC", callback_data="pay_BTC")], 
              [InlineKeyboardButton("ETH (Ethereum ERC20)", callback_data="pay_ETH")], 
              [InlineKeyboardButton("USDT (TRON TRC20)", callback_data="pay_USDT")],
              [InlineKeyboardButton("Bank Transfer", callback_data="pay_Bank")]]
        await update.message.reply_text("Choose payment method:", reply_markup=InlineKeyboardMarkup(kb))
    
    # NEW: Forward any regular text from users directly to Admin
    elif not is_admin(user_id):
        user = update.effective_user
        username = f"@{user.username}" if user.username else "No Username"
        for admin in ADMIN_IDS:
            try:
                kb = [[InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{user_id}")]]
                await context.bot.send_message(
                    chat_id=admin, 
                    text=f"📩 **New Message**\n👤 {user.first_name} ({username})\n🆔 `{user_id}`\n\n💬 {text}",
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode="Markdown"
                )
            except: pass

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    threading.Thread(target=lambda: server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    app.run_polling(drop_pending_updates=True)
