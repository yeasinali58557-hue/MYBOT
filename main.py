import logging
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, ConversationHandler, filters
)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BOT IS ALIVE!")

def run_dummy_server():
    try:
        server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        print(f"SERVER ERROR: {e}")

logging.basicConfig(level=logging.INFO)

TOKEN = "8736488112:AAHTHjThZMFND1pS0aITTImIKJaINzQL3Jk"
ADMIN_ID = 7753794493
DB_FILE = "bot_data.db"
REFERRAL_BONUS = 2.0  # Per referral bonus in BDT

# STATES
WAITING_AMOUNT, WAITING_DEP_PROOF = 1, 2
ADD_PROXY_NAME, ADD_PROXY_PRICE, ADD_PROXY_ITEMS = 3, 4, 5
ADD_VPN_NAME, ADD_VPN_DAYS, ADD_VPN_PRICE = 6, 7, 8
VPN_QTY_CUSTOM, ADMIN_VPN_DELIVER = 9, 10
SET_BKASH, SET_NAGAD, SET_BINANCE, SET_BEP20, SET_TRC20 = 11, 12, 13, 14, 15
BROADCAST_MSG = 16
EDIT_VPN_NAME_STATE, EDIT_VPN_PRICE_STATE = 17, 18
EDIT_PRX_NAME_STATE, EDIT_PRX_PRICE_STATE = 19, 20

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, referred_by INTEGER DEFAULT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS proxy_products (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, price REAL, ip TEXT, port TEXT, username TEXT, password TEXT, status TEXT DEFAULT 'AVAILABLE')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vpn_products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, days INTEGER, price REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales_history (id INTEGER PRIMARY KEY AUTOINCREMENT, item_type TEXT, name TEXT, price REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    defaults = {
        "BKASH": "01869425239",
        "NAGAD": "01869425239",
        "BINANCE": "7753794493",
        "BEP20": "0x1234567890abcdef1234567890abcdef12345678",
        "TRC20": "TYz1234567890abcdef1234567890abcdef"
    }
    for k, v in defaults.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))
        
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "NOT SET"

def set_setting(key, value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute('INSERT INTO users (user_id, balance) VALUES (?, ?)', (user_id, 0.0))
        conn.commit()
        conn.close()
        return 0.0
    conn.close()
    return row[0]

def update_user_balance(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_bal = get_user_balance(user_id)
    new_bal = current_bal + amount
    cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_bal, user_id))
    conn.commit()
    conn.close()
    return new_bal

def register_user(user_id, referrer_id=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    
    rewarded_referrer = None
    if row is None:
        if referrer_id and referrer_id != user_id:
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (referrer_id,))
            if cursor.fetchone():
                cursor.execute('INSERT INTO users (user_id, balance, referred_by) VALUES (?, ?, ?)', (user_id, 0.0, referrer_id))
                rewarded_referrer = referrer_id
            else:
                cursor.execute('INSERT INTO users (user_id, balance) VALUES (?, ?)', (user_id, 0.0))
        else:
            cursor.execute('INSERT INTO users (user_id, balance) VALUES (?, ?)', (user_id, 0.0))
        conn.commit()
    
    conn.close()
    
    if rewarded_referrer:
        update_user_balance(rewarded_referrer, REFERRAL_BONUS)
        return rewarded_referrer
    return None

def get_referral_count(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_main_keyboard(user_id):
    kb = [
        ["🛡️ BUY VPN", "🌐 BUY PROXY"],
        ["💳 DEPOSIT", "💰 BALANCE"],
        ["🔗 REFERRAL"]
    ]
    if user_id == ADMIN_ID:
        kb.append(["👑 ADMIN PANEL"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    referrer_id = None
    if context.args and len(context.args) > 0:
        try:
            referrer_id = int(context.args[0])
        except ValueError:
            referrer_id = None
            
    rewarded_referrer = register_user(user.id, referrer_id)
    
    if rewarded_referrer:
        try:
            new_ref_bal = get_user_balance(rewarded_referrer)
            await context.bot.send_message(
                rewarded_referrer, 
                f"🎉 **NEW REFERRAL JOINED!**\n\nSomeone joined using your referral link!\n💰 Added Bonus: `{REFERRAL_BONUS}` BDT\n📊 Total Balance: `{new_ref_bal}` BDT",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    user_bal = get_user_balance(user.id)

    welcome_msg = (
        f"🎉 WELCOME TO — ͟͞͞💗𝗡𝗘𝗫𝗢𝗥𝗔 𝗦𝗧𝗢𝗥𝗘 🎉\n\n"
        f"👤 NAME: {user.first_name.upper()}\n"
        f"🆔 USER ID: `{user.id}`\n"
        f"💰 YOUR BALANCE: `{user_bal}` BDT\n\n"
        f"PLEASE CHOOSE AN OPTION FROM THE MENU BELOW:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_buttons(update, context)
    return ConversationHandler.END

async def show_referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    ref_count = get_referral_count(user_id)
    total_earned = ref_count * REFERRAL_BONUS
    
    text = (
        f"🔗 **YOUR REFERRAL DASHBOARD**\n\n"
        f"🎁 **REWARD:** `{REFERRAL_BONUS}` BDT per valid referral\n"
        f"👥 **TOTAL REFERRED:** `{ref_count}` Users\n"
        f"💰 **TOTAL EARNED:** `{total_earned}` BDT\n\n"
        f"📌 **YOUR UNIQUE REFERRAL LINK:**\n"
        f"`{ref_link}`\n\n"
        f"💡 Share this link with your friends to earn automatic balance!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# --- ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM proxy_products WHERE status = "AVAILABLE"')
    proxy_avail = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM proxy_products WHERE status = "SOLD"')
    proxy_sold = cursor.fetchone()[0]
    total_proxy = proxy_avail + proxy_sold
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    conn.close()

    kb = [
        [InlineKeyboardButton("📢 BROADCAST MESSAGE", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🛡️ MANAGE VPN STOCK", callback_data="admin_manage_vpn"), InlineKeyboardButton("🌐 MANAGE PROXY STOCK", callback_data="admin_manage_proxy")],
        [InlineKeyboardButton("⚙️ SETTINGS (ADDRESS & NUMBERS)", callback_data="admin_settings")]
    ]
    
    admin_text = (
        f"👑 **ADMIN DASHBOARD**\n\n"
        f"👥 TOTAL USERS: `{total_users}`\n\n"
        f"📊 **PROXY STATS:**\n"
        f"📦 TOTAL UPLOADED: `{total_proxy}` PCS\n"
        f"✅ AVAILABLE: `{proxy_avail}` PCS\n"
        f"🛒 SOLD OUT: `{proxy_sold}` PCS"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(admin_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(admin_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# --- PROXY STOCK MANAGEMENT ---
async def manage_proxy_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT category, price FROM proxy_products GROUP BY category')
    categories = cursor.fetchall()

    kb = []
    text_info = "⚙️ **PROXY STOCK MANAGEMENT PANEL**\n\n"
    
    if categories:
        text_info += "📋 **CATEGORY STATS:**\n"
        for (cat_name, price) in categories:
            cursor.execute('SELECT COUNT(*) FROM proxy_products WHERE category = ? AND status = "AVAILABLE"', (cat_name,))
            avail = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM proxy_products WHERE category = ? AND status = "SOLD"', (cat_name,))
            sold = cursor.fetchone()[0]
            total = avail + sold
            
            text_info += f"• **{cat_name.upper()}**: Total `{total}` | Available `{avail}` | Sold `{sold}`\n"
            kb.append([
                InlineKeyboardButton(f"🌐 {cat_name.upper()} ({avail} Avail)", callback_data=f"infoprx_{cat_name}"),
                InlineKeyboardButton("✏️ EDIT", callback_data=f"editprx_menu_{cat_name}")
            ])
    else:
        text_info += "❌ No proxy categories found."

    conn.close()
    kb.append([InlineKeyboardButton("➕ ADD BULK PROXY STOCK", callback_data="admin_add_proxy")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel_back")])
    
    await query.edit_message_text(text_info, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def start_add_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🌐 ENTER PROXY CATEGORY NAME (e.g. USA SOCKS5, RESIDENTIAL, 9PROXY):")
    return ADD_PROXY_NAME

async def add_proxy_name_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END
        
    context.user_data['stk_prx_name'] = text.upper()
    await update.message.reply_text("💵 ENTER PRICE PER PROXY (BDT):")
    return ADD_PROXY_PRICE

async def add_proxy_price_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    try:
        context.user_data['stk_prx_price'] = float(text)
        msg = (
            "🚀 **PASTE BULK PROXIES NOW!**\n\n"
            "একসাথে যত খুশি প্রক্সি পেস্ট করে পাঠিয়ে দিন।\n\n"
            "📌 **SUPPORTED FORMATS:**\n"
            "`IP:PORT:USERNAME:PASSWORD`\n"
            "`IP:PORT`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return ADD_PROXY_ITEMS
    except ValueError:
        await update.message.reply_text("❌ INVALID PRICE! Please enter a number (e.g. 15 or 20):")
        return ADD_PROXY_PRICE

async def add_proxy_items_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    lines = text.split('\n')
    name = context.user_data.get('stk_prx_name')
    price = context.user_data.get('stk_prx_price')
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    added_count = 0
    skipped_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        parts = line.split(':')
        ip, port, uname, pwd = "", "", "", ""
        
        if len(parts) == 4:
            ip, port, uname, pwd = parts[0], parts[1], parts[2], parts[3]
        elif len(parts) == 2:
            ip, port = parts[0], parts[1]
        else:
            continue

        cursor.execute('SELECT id FROM proxy_products WHERE ip = ? AND port = ?', (ip, port))
        if cursor.fetchone():
            skipped_count += 1
            continue

        cursor.execute(
            'INSERT INTO proxy_products (category, price, ip, port, username, password, status) VALUES (?, ?, ?, ?, ?, ?, "AVAILABLE")',
            (name, price, ip, port, uname, pwd)
        )
        added_count += 1

    conn.commit()
    conn.close()
    
    result_text = (
        f"✅ **BULK PROXY IMPORTED SUCCESSFULLY!**\n\n"
        f"📦 CATEGORY: `{name}`\n"
        f"💵 PRICE: `{price}` BDT\n"
        f"➕ ADDED: `{added_count}` PCS\n"
        f"⚠️ DUPLICATE/SKIPPED: `{skipped_count}` PCS"
    )
    await update.message.reply_text(result_text, parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

# --- BUY PROXY STORE ---
async def show_proxy_store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT category, price FROM proxy_products WHERE status = "AVAILABLE" GROUP BY category')
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        text = "❌ NO PROXY STOCK AVAILABLE RIGHT NOW!"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return
        
    kb = []
    for cat, price in items:
        kb.append([InlineKeyboardButton(f"🌐 {cat.upper()} - {price} BDT", callback_data=f"buyprx_{cat}")])
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("🌐 SELECT PROXY PACKAGE:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("🌐 SELECT PROXY PACKAGE:", reply_markup=InlineKeyboardMarkup(kb))

async def buy_proxy_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split("_")[1]
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, price, ip, port, username, password FROM proxy_products WHERE category = ? AND status = "AVAILABLE" LIMIT 1', (cat,))
    row = cursor.fetchone()
    
    if not row:
        await query.edit_message_text("❌ OUT OF STOCK!")
        conn.close()
        return
        
    pid, price, ip, port, uname, pwd = row
    bal = get_user_balance(user_id)
    if bal < price:
        await query.edit_message_text(f"❌ INSUFFICIENT BALANCE!\nPRICE: `{price}` BDT\nYOUR BALANCE: `{bal}` BDT", parse_mode="Markdown")
        conn.close()
        return
        
    update_user_balance(user_id, -price)
    
    cursor.execute('UPDATE proxy_products SET status = "SOLD" WHERE id = ?', (pid,))
    cursor.execute('INSERT INTO sales_history (item_type, name, price) VALUES ("PROXY", ?, ?)', (cat, price))
    conn.commit()
    conn.close()
    
    user_pass_str = f"⭐ USER: `{uname}`\n🔑 PASS: `{pwd}`\n" if uname else ""
    
    deliv = (
        f"✅ **ORDER COMPLETED** ✨\n\n"
        f"📦 PACKAGE: `{cat.upper()}`\n\n"
        f"🌐 **YOUR PROXY DETAILS:**\n"
        f"🌐 IP: `{ip}`\n"
        f"⬆️ PORT: `{port}`\n"
        f"{user_pass_str}\n"
        f"THANK YOU FOR YOUR PURCHASE!"
    )
    await query.edit_message_text(deliv, parse_mode="Markdown")

# --- BROADCAST ---
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 WRITE THE MESSAGE YOU WANT TO SEND TO ALL USERS:")
    return BROADCAST_MSG

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text
    if msg_text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()

    success, fail = 0, 0
    await update.message.reply_text("⏳ SENDING BROADCAST MESSAGE...")

    for (uid,) in users:
        try:
            await context.bot.send_message(uid, f"📢 ANNOUNCEMENT FROM ADMIN:\n\n{msg_text}")
            success += 1
        except Exception:
            fail += 1

    await update.message.reply_text(f"✅ BROADCAST COMPLETED!\n\nSUCCESS: {success}\nFAILED: {fail}", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

# --- VPN MANAGEMENTS ---
async def manage_vpn_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT name FROM vpn_products')
    vpn_items = cursor.fetchall()
    conn.close()

    kb = []
    for (vpn_name,) in vpn_items:
        kb.append([
            InlineKeyboardButton(f"🛡️ {vpn_name.upper()}", callback_data=f"infovpn_{vpn_name}"),
            InlineKeyboardButton("✏️ EDIT", callback_data=f"editvpn_menu_{vpn_name}")
        ])
        
    kb.append([InlineKeyboardButton("➕ ADD NEW VPN PACK", callback_data="admin_add_vpn")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel_back")])
    
    await query.edit_message_text("⚙️ VPN STOCK MANAGEMENT PANEL:", reply_markup=InlineKeyboardMarkup(kb))

async def vpn_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vpn_name = query.data.split("_")[2]
    
    kb = [
        [InlineKeyboardButton("✏️ CHANGE NAME", callback_data=f"vpn_cname_{vpn_name}")],
        [InlineKeyboardButton("💵 CHANGE PRICE", callback_data=f"vpn_cprice_{vpn_name}")],
        [InlineKeyboardButton("❌ DELETE PRODUCT", callback_data=f"vpn_del_{vpn_name}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_manage_vpn")]
    ]
    await query.edit_message_text(f"✏️ EDITING VPN: {vpn_name.upper()}\nSELECT AN OPTION:", reply_markup=InlineKeyboardMarkup(kb))

async def edit_vpn_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vpn_name = query.data.split("_")[2]
    context.user_data['old_vpn_name'] = vpn_name
    await query.edit_message_text(f"✏️ ENTER NEW NAME FOR `{vpn_name}`:", parse_mode="Markdown")
    return EDIT_VPN_NAME_STATE

async def edit_vpn_name_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip().upper()
    if new_name in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    old_name = context.user_data.get('old_vpn_name')
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE vpn_products SET name = ? WHERE name = ?', (new_name, old_name))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ VPN NAME CHANGED FROM `{old_name}` TO `{new_name}`!", parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

async def edit_vpn_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vpn_name = query.data.split("_")[2]
    context.user_data['edit_vpn_price_target'] = vpn_name
    await query.edit_message_text(f"💵 ENTER NEW PRICE FOR `{vpn_name}` (BDT):", parse_mode="Markdown")
    return EDIT_VPN_PRICE_STATE

async def edit_vpn_price_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    try:
        new_price = float(text)
        vpn_name = context.user_data.get('edit_vpn_price_target')
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE vpn_products SET price = ? WHERE name = ?', (new_price, vpn_name))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ VPN `{vpn_name}` PRICE UPDATED TO `{new_price}` BDT!", parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ INVALID PRICE!")
        return EDIT_VPN_PRICE_STATE

async def delete_vpn_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vpn_name = query.data.split("_")[2]
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM vpn_products WHERE name = ?', (vpn_name,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text(f"🗑️ VPN `{vpn_name}` DELETED SUCCESSFULLY!", parse_mode="Markdown")

# --- PROXY EDIT MANAGEMENT ---
async def prx_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prx_name = query.data.split("_")[2]
    
    kb = [
        [InlineKeyboardButton("✏️ CHANGE NAME", callback_data=f"prx_cname_{prx_name}")],
        [InlineKeyboardButton("💵 CHANGE PRICE", callback_data=f"prx_cprice_{prx_name}")],
        [InlineKeyboardButton("❌ DELETE ALL STOCK", callback_data=f"prx_del_{prx_name}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_manage_proxy")]
    ]
    await query.edit_message_text(f"✏️ EDITING PROXY: {prx_name.upper()}\nSELECT AN OPTION:", reply_markup=InlineKeyboardMarkup(kb))

async def edit_prx_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prx_name = query.data.split("_")[2]
    context.user_data['old_prx_name'] = prx_name
    await query.edit_message_text(f"✏️ ENTER NEW NAME FOR `{prx_name}`:", parse_mode="Markdown")
    return EDIT_PRX_NAME_STATE

async def edit_prx_name_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip().upper()
    if new_name in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    old_name = context.user_data.get('old_prx_name')
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE proxy_products SET category = ? WHERE category = ?', (new_name, old_name))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ PROXY NAME CHANGED FROM `{old_name}` TO `{new_name}`!", parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

async def edit_prx_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prx_name = query.data.split("_")[2]
    context.user_data['edit_prx_price_target'] = prx_name
    await query.edit_message_text(f"💵 ENTER NEW PRICE FOR `{prx_name}` (BDT):", parse_mode="Markdown")
    return EDIT_PRX_PRICE_STATE

async def edit_prx_price_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    try:
        new_price = float(text)
        prx_name = context.user_data.get('edit_prx_price_target')
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE proxy_products SET price = ? WHERE category = ?', (new_price, prx_name))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ PROXY `{prx_name}` PRICE UPDATED TO `{new_price}` BDT!", parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ INVALID PRICE!")
        return EDIT_PRX_PRICE_STATE

async def delete_prx_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prx_name = query.data.split("_")[2]
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM proxy_products WHERE category = ?', (prx_name,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text(f"🗑️ PROXY `{prx_name}` DELETED SUCCESSFULLY!", parse_mode="Markdown")

# --- SETTINGS MENU ---
async def admin_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        f"⚙️ BOT SETTINGS & ADDRESSES:\n\n"
        f"💗 BKASH: `{get_setting('BKASH')}`\n"
        f"🧡 NAGAD: `{get_setting('NAGAD')}`\n"
        f"🟡 BINANCE ID: `{get_setting('BINANCE')}`\n"
        f"🌐 BEP20: `{get_setting('BEP20')}`\n"
        f"🌐 TRC20: `{get_setting('TRC20')}`"
    )
    
    kb = [
        [InlineKeyboardButton("EDIT BKASH", callback_data="set_bkash"), InlineKeyboardButton("EDIT NAGAD", callback_data="set_nagad")],
        [InlineKeyboardButton("EDIT BINANCE ID", callback_data="set_binance")],
        [InlineKeyboardButton("EDIT BEP20 ADDRESS", callback_data="set_bep20"), InlineKeyboardButton("EDIT TRC20 ADDRESS", callback_data="set_trc20")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_panel_back")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def set_bkash_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📞 ENTER NEW BKASH NUMBER:")
    return SET_BKASH

async def set_bkash_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    set_setting("BKASH", text)
    await update.message.reply_text("✅ BKASH NUMBER UPDATED!", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

async def set_nagad_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📞 ENTER NEW NAGAD NUMBER:")
    return SET_NAGAD

async def set_nagad_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    set_setting("NAGAD", text)
    await update.message.reply_text("✅ NAGAD NUMBER UPDATED!", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

async def set_binance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🟡 ENTER NEW BINANCE PAY ID:")
    return SET_BINANCE

async def set_binance_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    set_setting("BINANCE", text)
    await update.message.reply_text("✅ BINANCE PAY ID UPDATED!", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

async def set_bep20_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🌐 ENTER NEW BEP20 ADDRESS:")
    return SET_BEP20

async def set_bep20_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    set_setting("BEP20", text)
    await update.message.reply_text("✅ BEP20 ADDRESS UPDATED!", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

async def set_trc20_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🌐 ENTER NEW TRC20 ADDRESS:")
    return SET_TRC20

async def set_trc20_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    set_setting("TRC20", text)
    await update.message.reply_text("✅ TRC20 ADDRESS UPDATED!", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

# --- DEPOSIT SYSTEM ---
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("✅ BKASH", callback_data="depmeth_BKASH")],
        [InlineKeyboardButton("✅ NAGAD", callback_data="depmeth_NAGAD")],
        [InlineKeyboardButton("🟡 BINANCE", callback_data="depmeth_BINANCE")]
    ]
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("💳 **SELECT DEPOSIT METHOD:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update.message.reply_text("💳 **SELECT DEPOSIT METHOD:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return WAITING_AMOUNT

async def dep_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[1]
    context.user_data['dep_method'] = method
    
    num = get_setting(method)
    text = (
        f"✅ **METHOD:** {method}\n"
        f"📞 **SEND TO ({'ID' if method=='BINANCE' else 'NUMBER'}):** `{num}`\n\n"
        f"💳 **ENTER DEPOSIT AMOUNT (BDT):**"
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    return WAITING_AMOUNT

async def dep_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    try:
        amount = float(text)
        method = context.user_data.get('dep_method', 'BKASH')
        context.user_data['dep_amount'] = amount
        num = get_setting(method)
        
        warn_text = ""
        if method == "BINANCE":
            usdt_amt = amount / 125.0
            warn_text = f"\n⚠️ **WARNING:** PLEASE SEND EXACTLY `{usdt_amt:.2f}` USDT"

        text_summary = (
            f"📩 **DEPOSIT SUMMARY**\n\n"
            f"🔹 **METHOD:** {method}\n"
            f"💵 **AMOUNT:** {amount} BDT\n"
            f"📱 **ADDRESS/NO:** {num}{warn_text}\n\n"
            f"👇 **CLICK CONFIRM PAYMENT AFTER SENDING.**"
        )
        
        kb = [[InlineKeyboardButton("✅ CONFIRM PAYMENT", callback_data="dep_confirm")]]
        await update.message.reply_text(text_summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return WAITING_DEP_PROOF
    except ValueError:
        await update.message.reply_text("❌ PLEASE ENTER A VALID NUMBER!")
        return WAITING_AMOUNT

async def dep_confirm_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 **PLEASE SEND THE PAYMENT SCREENSHOT NOW:**", parse_mode="Markdown")
    return WAITING_DEP_PROOF

async def dep_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    method = context.user_data.get('dep_method', 'N/A')
    amount = context.user_data.get('dep_amount', 0)
    
    final_text = (
        f"DEPOSIT REQUEST CREATE ✅\n\n"
        f"🔹 **METHOD:** {method}\n"
        f"💵 **AMOUNT:** {amount} BDT\n\n"
        f"⚡ **WAIT FOR 2-5 MINUTE ADMIN VERIFY** ⚡"
    )
    
    await update.message.reply_text(final_text, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    
    admin_kb = [[InlineKeyboardButton("✅ APPROVE", callback_data=f"depapp_app_{user.id}_{amount}"), InlineKeyboardButton("❌ REJECT", callback_data=f"depapp_rej_{user.id}_{amount}")]]
    await context.bot.send_photo(
        ADMIN_ID, 
        photo, 
        caption=f"📥 **NEW DEPOSIT REQUEST**\n\n👤 USER: {user.full_name.upper()} (`{user.id}`)\n💳 METHOD: {method}\n💰 AMOUNT: `{amount}` BDT", 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(admin_kb)
    )
    return ConversationHandler.END

async def dep_approval_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, act, uid, amt = query.data.split("_")
    uid, amt = int(uid), float(amt)
    if act == "app":
        new_bal = update_user_balance(uid, amt)
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n✅ APPROVED")
        await context.bot.send_message(uid, f"🎉 DEPOSIT APPROVED!\nADDED: `{amt}` BDT\nBALANCE: `{new_bal}` BDT", parse_mode="Markdown")
    else:
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n❌ REJECTED")
        await context.bot.send_message(uid, "❌ DEPOSIT REJECTED!")

# --- VPN STORE & DELIVERY ---
async def start_vpn_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📅 3 DAYS", callback_data="vpndays_3"), InlineKeyboardButton("📅 7 DAYS", callback_data="vpndays_7")],
        [InlineKeyboardButton("📅 14 DAYS", callback_data="vpndays_14"), InlineKeyboardButton("📅 30 DAYS", callback_data="vpndays_30")]
    ]
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("💥 VPN PACKAGES 💥\n\nSELECT DURATION: 🛡️", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("💥 VPN PACKAGES 💥\n\nSELECT DURATION: 🛡️", reply_markup=InlineKeyboardMarkup(kb))

async def vpn_days_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    days = int(query.data.split("_")[1])
    context.user_data['buy_vpn_days'] = days
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT name, price FROM vpn_products WHERE days = ?', (days,))
    prods = cursor.fetchall()
    conn.close()
    
    kb = []
    if not prods:
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="vpn_main_back")])
        await query.edit_message_text(f"❌ NO VPN PACKS AVAILABLE FOR {days} DAYS!", reply_markup=InlineKeyboardMarkup(kb))
        return
        
    for name, price in prods:
        kb.append([InlineKeyboardButton(f"{name.upper()} [{days} DAYS] - {price} BDT", callback_data=f"vpnpack_{name}_{price}")])
    
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="vpn_main_back")])
    
    await query.edit_message_text(f"💥 VPN ({days} DAYS) 💥\n\nSELECT VPN SERVICE: 🛡️", reply_markup=InlineKeyboardMarkup(kb))

async def vpn_pack_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name, price = query.data.split("_")
    context.user_data['buy_vpn_name'] = name
    context.user_data['buy_vpn_price'] = float(price)
    days = context.user_data.get('buy_vpn_days')
    
    kb = [
        [InlineKeyboardButton("1 PCS", callback_data="vpnqty_1"), InlineKeyboardButton("3 PCS", callback_data="vpnqty_3")],
        [InlineKeyboardButton("5 PCS", callback_data="vpnqty_5"), InlineKeyboardButton("10 PCS", callback_data="vpnqty_10")],
        [InlineKeyboardButton("📝 ENTER QUANTITY", callback_data="vpnqty_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"vpndays_{days}")]
    ]
    await query.edit_message_text(f"💥 VPN 💥 {name.upper()} [{days} DAYS]\n\nHOW MANY PIECES DO YOU WANT TO BUY? 🛡️", reply_markup=InlineKeyboardMarkup(kb))

async def vpn_qty_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")[1]
    
    if data == "custom":
        await query.edit_message_text("📝 ENTER QUANTITY (NUMBER):")
        return VPN_QTY_CUSTOM
    else:
        qty = int(data)
        return await finalize_vpn_order(update, context, qty, query)

async def vpn_custom_qty_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    try:
        qty = int(text)
        return await finalize_vpn_order(update, context, qty)
    except ValueError:
        await update.message.reply_text("❌ INVALID NUMBER!")
        return VPN_QTY_CUSTOM

async def finalize_vpn_order(update, context, qty, query=None):
    user = update.effective_user
    days = context.user_data.get('buy_vpn_days')
    name = context.user_data.get('buy_vpn_name')
    price_per = context.user_data.get('buy_vpn_price')
    total_cost = price_per * qty
    
    bal = get_user_balance(user.id)
    if bal < total_cost:
        msg = f"❌ INSUFFICIENT BALANCE!\nTOTAL: `{total_cost}` BDT\nBALANCE: `{bal}` BDT"
        if query: await query.edit_message_text(msg, parse_mode="Markdown")
        else: await update.message.reply_text(msg, parse_mode="Markdown")
        return ConversationHandler.END
        
    update_user_balance(user.id, -total_cost)
    
    user_msg = f"🎉 ORDER SUBMITTED!\n\nYOUR VPN ORDER WILL BE DELIVERED WITHIN 20-50 MINUTES AFTER APPROVAL"
    if query: await query.edit_message_text(user_msg)
    else: await update.message.reply_text(user_msg, reply_markup=get_main_keyboard(user.id))
    
    admin_req = f"🔔 NEW VPN ORDER\n\n👤 USER: {user.full_name.upper()} (`{user.id}`)\n📦 VPN: {name.upper()}\n📅 DAYS: {days}\n🔢 QTY: {qty}\n💰 TOTAL COST: `{total_cost}` BDT"
    kb = [[InlineKeyboardButton("🚀 DELIVER PRODUCT", callback_data=f"delivvpn_{user.id}")]]
    await context.bot.send_message(ADMIN_ID, admin_req, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

async def start_admin_deliver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_uid = query.data.split("_")[1]
    context.user_data['deliver_target_uid'] = target_uid
    await query.edit_message_text(f"🚀 SEND PRODUCT DETAILS FOR USER `{target_uid}`:", parse_mode="Markdown")
    return ADMIN_VPN_DELIVER

async def admin_deliver_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    target_uid = context.user_data.get('deliver_target_uid')
    details = text
    
    try:
        await context.bot.send_message(target_uid, f"🎁 YOUR VPN ORDER DELIVERED!\n\n{details}")
        await update.message.reply_text("✅ PRODUCT SENT TO USER SUCCESSFULLY!")
    except Exception as e:
        await update.message.reply_text(f"❌ ERROR SENDING MESSAGE: {e}")
    return ConversationHandler.END

async def start_add_vpn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🛡️ ENTER VPN NAME:")
    return ADD_VPN_NAME

async def add_vpn_name_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    context.user_data['stk_vpn_name'] = text.upper()
    await update.message.reply_text("📅 ENTER DAYS (E.G. 3, 7, 14, 30):")
    return ADD_VPN_DAYS

async def add_vpn_days_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    try:
        context.user_data['stk_vpn_days'] = int(text)
        await update.message.reply_text("💵 ENTER PRICE (BDT):")
        return ADD_VPN_PRICE
    except ValueError:
        await update.message.reply_text("❌ INVALID NUMBER!")
        return ADD_VPN_DAYS

async def add_vpn_price_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "💳 DEPOSIT", "💰 BALANCE", "🔗 REFERRAL", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    try:
        price = float(text)
        name = context.user_data.get('stk_vpn_name')
        days = context.user_data.get('stk_vpn_days')
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO vpn_products (name, days, price) VALUES (?, ?, ?)', (name, days, price))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ ADDED {name} [{days} DAYS] FOR {price} BDT!", reply_markup=get_main_keyboard(ADMIN_ID))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ INVALID PRICE!")
        return ADD_VPN_PRICE

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "💳 DEPOSIT": await deposit_start(update, context)
    elif text == "💰 BALANCE": await update.message.reply_text(f"📊 YOUR BALANCE: `{get_user_balance(user_id)}` BDT", parse_mode="Markdown")
    elif text == "🔗 REFERRAL": await show_referral_info(update, context)
    elif text == "🛡️ BUY VPN": await start_vpn_flow(update, context)
    elif text == "🌐 BUY PROXY": await show_proxy_store(update, context)
    elif text == "👑 ADMIN PANEL": await admin_panel(update, context)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    fallback_buttons = [
        MessageHandler(filters.Regex("^(🛡️ BUY VPN|🌐 BUY PROXY|💳 DEPOSIT|💰 BALANCE|🔗 REFERRAL|👑 ADMIN PANEL)$"), cancel_conversation),
        CommandHandler("cancel", cancel_conversation)
    ]
    
    # CONVERSATIONS
    dep_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(💳 DEPOSIT)$"), deposit_start)],
        states={
            WAITING_AMOUNT: [
                CallbackQueryHandler(dep_method_selected, pattern="^depmeth_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, dep_amount_received)
            ],
            WAITING_DEP_PROOF: [
                CallbackQueryHandler(dep_confirm_clicked, pattern="^dep_confirm$"),
                MessageHandler(filters.PHOTO, dep_proof_received)
            ]
        },
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )
    
    add_prx_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_proxy, pattern="^admin_add_proxy$")],
        states={
            ADD_PROXY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_proxy_name_rec)],
            ADD_PROXY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_proxy_price_rec)],
            ADD_PROXY_ITEMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_proxy_items_rec)]
        },
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )

    vpn_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(vpn_qty_process, pattern="^vpnqty_")],
        states={VPN_QTY_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, vpn_custom_qty_received)]},
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )
    
    admin_deliver_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_admin_deliver, pattern="^delivvpn_")],
        states={ADMIN_VPN_DELIVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_deliver_received)]},
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )

    add_vpn_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_vpn, pattern="^admin_add_vpn$")],
        states={
            ADD_VPN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_name_rec)],
            ADD_VPN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_days_rec)],
            ADD_VPN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_price_rec)]
        },
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^admin_broadcast$")],
        states={BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)]},
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )

    settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_bkash_start, pattern="^set_bkash$"),
            CallbackQueryHandler(set_nagad_start, pattern="^set_nagad$"),
            CallbackQueryHandler(set_binance_start, pattern="^set_binance$"),
            CallbackQueryHandler(set_bep20_start, pattern="^set_bep20$"),
            CallbackQueryHandler(set_trc20_start, pattern="^set_trc20$")
        ],
        states={
            SET_BKASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_bkash_rec)],
            SET_NAGAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_nagad_rec)],
            SET_BINANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_binance_rec)],
            SET_BEP20: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_bep20_rec)],
            SET_TRC20: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_trc20_rec)]
        },
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )

    edit_vpn_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_vpn_name_start, pattern="^vpn_cname_"),
            CallbackQueryHandler(edit_vpn_price_start, pattern="^vpn_cprice_")
        ],
        states={
            EDIT_VPN_NAME_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_vpn_name_rec)],
            EDIT_VPN_PRICE_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_vpn_price_rec)]
        },
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )

    edit_prx_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_prx_name_start, pattern="^prx_cname_"),
            CallbackQueryHandler(edit_prx_price_start, pattern="^prx_cprice_")
        ],
        states={
            EDIT_PRX_NAME_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_prx_name_rec)],
            EDIT_PRX_PRICE_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_prx_price_rec)]
        },
        fallbacks=fallback_buttons + [CommandHandler("start", start)],
        per_message=False,
        allow_reentry=True
    )

    # HANDLERS REGISTER
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    
    app.add_handler(dep_conv)
    app.add_handler(add_prx_conv)
    app.add_handler(vpn_conv)
    app.add_handler(admin_deliver_conv)
    app.add_handler(add_vpn_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(settings_conv)
    app.add_handler(edit_vpn_conv)
    app.add_handler(edit_prx_conv)
    
    # CALLBACKS
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel_back$"))
    app.add_handler(CallbackQueryHandler(start_vpn_flow, pattern="^vpn_main_back$"))
    app.add_handler(CallbackQueryHandler(admin_settings_menu, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(manage_vpn_stock, pattern="^admin_manage_vpn$"))
    app.add_handler(CallbackQueryHandler(manage_proxy_stock, pattern="^admin_manage_proxy$"))
    app.add_handler(CallbackQueryHandler(vpn_edit_menu, pattern="^editvpn_menu_"))
    app.add_handler(CallbackQueryHandler(prx_edit_menu, pattern="^editprx_menu_"))
    app.add_handler(CallbackQueryHandler(delete_vpn_product, pattern="^vpn_del_"))
    app.add_handler(CallbackQueryHandler(delete_prx_product, pattern="^prx_del_"))
    
    app.add_handler(CallbackQueryHandler(dep_approval_handler, pattern="^depapp_"))
    app.add_handler(CallbackQueryHandler(show_proxy_store, pattern="^buy_proxy$"))
    app.add_handler(CallbackQueryHandler(buy_proxy_process, pattern="^buyprx_"))
    app.add_handler(CallbackQueryHandler(vpn_days_selected, pattern="^vpndays_"))
    app.add_handler(CallbackQueryHandler(vpn_pack_selected, pattern="^vpnpack_"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("BOT IS RUNNING PERFECTLY...")
    app.run_polling()

if __name__ == "__main__":
    main()
