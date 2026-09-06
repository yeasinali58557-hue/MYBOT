import logging
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, ConversationHandler, filters
)

# --- DUMMY SERVER FOR CLOUD HOSTING ---
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

# CONFIGS
TOKEN = "8733585059:AAE3XL0aHVQ2gdw3BAm6RKkMSZeDXq8pe6g"
ADMIN_ID = 7753794493
DB_FILE = "bot_data.db"

BKASH_NUMBER = "01869425239"
NAGAD_NUMBER = "01869425239"
BINANCE_ID = "7753794493"
BEP20_ADDRESS = "0x1234567890abcdef1234567890abcdef12345678"
TRC20_ADDRESS = "TYz1234567890abcdef1234567890abcdef"

# CONVERSATION STATES
WAITING_AMOUNT, WAITING_TRXID = 1, 2
ADD_PROXY_NAME, ADD_PROXY_PRICE, ADD_PROXY_ITEMS = 3, 4, 5
ADD_VPN_NAME, ADD_VPN_DAYS, ADD_VPN_PRICE = 6, 7, 8
BROADCAST_MSG = 9
P2P_SELL_NUMBER, P2P_SELL_PROOF = 10, 11
VPN_QTY_CUSTOM, ADMIN_VPN_DELIVER = 12, 13

MENU_BUTTONS = ["🛡️ BUY VPN", "🌐 BUY PROXY", "🔄 P2P (USDT BUY & SELL)", "💳 DEPOSIT", "💰 BALANCE", "👑 ADMIN PANEL"]

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS proxy_products (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, price REAL, ip TEXT, port TEXT, username TEXT, password TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vpn_products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, days INTEGER, price REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales_history (id INTEGER PRIMARY KEY AUTOINCREMENT, item_type TEXT, name TEXT, price REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, method TEXT, amount REAL, trxid TEXT, status TEXT DEFAULT 'PENDING')''')
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

# --- MAIN KEYBOARD (ALL UPPERCASE) ---
def get_main_keyboard(user_id):
    kb = [
        ["🛡️ BUY VPN", "🌐 BUY PROXY"],
        ["🔄 P2P (USDT BUY & SELL)"],
        ["💳 DEPOSIT", "💰 BALANCE"]
    ]
    if user_id == ADMIN_ID:
        kb.append(["👑 ADMIN PANEL"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_balance(user.id)
    
    welcome_msg = (
        f"🎉 **WELCOME TO DIGITAL SERVICE BOT!** 🎉\n\n"
        f"👤 **NAME:** {user.first_name.upper()}\n"
        f"🆔 **USER ID:** `{user.id}`\n"
        f"💰 **YOUR BALANCE:** `{get_user_balance(user.id)} BDT`\n\n"
        f"PLEASE CHOOSE AN OPTION FROM THE MENU BELOW:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    return ConversationHandler.END

# --- ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM proxy_products')
    proxy_stock = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM sales_history WHERE item_type = "PROXY"')
    proxy_sold = cursor.fetchone()[0]
    conn.close()

    kb = [
        [InlineKeyboardButton("📥 DEPOSIT REQUESTS", callback_data="admin_deposit_req")],
        [InlineKeyboardButton("➕ MANAGE VPN STOCK", callback_data="admin_manage_vpn"), InlineKeyboardButton("➕ MANAGE PROXY STOCK", callback_data="admin_manage_proxy")],
        [InlineKeyboardButton("📢 BROADCAST", callback_data="admin_broadcast")]
    ]
    admin_text = f"👑 **ADMIN DASHBOARD**\n\n🌐 **PROXY STOCK:** {proxy_stock} PCS\n🛒 **PROXY SOLD:** {proxy_sold} PCS"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(admin_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(admin_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# --- STOCK MANAGEMENT ---
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
        v_upper = vpn_name.upper()
        kb.append([
            InlineKeyboardButton(f"🛡️ {v_upper}", callback_data=f"info_vpn_{vpn_name}"),
            InlineKeyboardButton("✏️ EDIT", callback_data=f"edit_vpn_{vpn_name}"),
            InlineKeyboardButton("📅 DAYS", callback_data=f"days_vpn_{vpn_name}")
        ])
        
    kb.append([InlineKeyboardButton("➕ ADD NEW VPN PACK", callback_data="admin_add_vpn")])
    kb.append([InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel_back")])
    
    await query.edit_message_text("⚙️ **VPN STOCK MANAGEMENT PANEL:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def manage_proxy_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT category FROM proxy_products')
    proxy_items = cursor.fetchall()
    conn.close()

    kb = []
    for (prx_name,) in proxy_items:
        p_upper = prx_name.upper()
        kb.append([
            InlineKeyboardButton(f"🌐 {p_upper}", callback_data=f"info_prx_{prx_name}"),
            InlineKeyboardButton("✏️ EDIT", callback_data=f"edit_prx_{prx_name}"),
            InlineKeyboardButton("📅 DAYS", callback_data=f"days_prx_{prx_name}")
        ])
        
    kb.append([InlineKeyboardButton("➕ ADD NEW PROXY STOCK", callback_data="admin_add_proxy")])
    kb.append([InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel_back")])
    
    await query.edit_message_text("⚙️ **PROXY STOCK MANAGEMENT PANEL:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def handle_stock_days_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_name = query.data.split("_")[-1].upper()
    
    kb = [
        [InlineKeyboardButton("📅 3 DAYS", callback_data=f"setday_3_{item_name}"), InlineKeyboardButton("📅 7 DAYS", callback_data=f"setday_7_{item_name}")],
        [InlineKeyboardButton("📅 14 DAYS", callback_data=f"setday_14_{item_name}"), InlineKeyboardButton("📅 30 DAYS", callback_data=f"setday_30_{item_name}")],
        [InlineKeyboardButton("🔙 BACK", callback_data="admin_manage_vpn")]
    ]
    await query.edit_message_text(f"📅 **SELECT DURATION FOR {item_name}:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_deposit_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📥 **DEPOSIT REQUESTS:**\n\nNO PENDING REQUESTS FOUND.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK TO ADMIN", callback_data="admin_panel_back")]]))

# --- DEPOSIT SYSTEM ---
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💗 BKASH", callback_data="dep_BKASH")],
        [InlineKeyboardButton("🧡 NAGAD", callback_data="dep_NAGAD")],
        [InlineKeyboardButton("🟡 BINANCE", callback_data="dep_BINANCE")]
    ]
    await update.message.reply_text("💳 **SELECT PAYMENT METHOD:**", reply_markup=InlineKeyboardMarkup(kb))

async def dep_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[1]
    context.user_data['dep_method'] = method
    
    num = BKASH_NUMBER if method == "BKASH" else NAGAD_NUMBER if method == "NAGAD" else BINANCE_ID
    await query.edit_message_text(f"✅ **METHOD: {method}**\n📞 **SEND TO ({'ID' if method=='BINANCE' else 'NUMBER'}):** `{num}`\n\n💳 **ENTER DEPOSIT AMOUNT (BDT):**", parse_mode="Markdown")
    return WAITING_AMOUNT

async def dep_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    try:
        amount = float(update.message.text.strip())
        method = context.user_data.get('dep_method')
        context.user_data['dep_amount'] = amount
        
        warn_text = ""
        if method == "BINANCE":
            usdt_amt = amount / 125.0
            warn_text = f"\n\n⚠️ **WARNING:** PLEASE SEND EXACTLY **{usdt_amt:.2f} USDT** (RATE: 125 BDT = 1$)"

        num = BKASH_NUMBER if method == "BKASH" else NAGAD_NUMBER if method == "NAGAD" else BINANCE_ID
        text = f"📥 **DEPOSIT SUMMARY**\n\n• **METHOD:** {method}\n• **AMOUNT:** {amount} BDT\n• **ADDRESS/NO:** `{num}`{warn_text}\n\nCLICK **PAYMENT DONE** AFTER SENDING."
        kb = [[InlineKeyboardButton("✅ PAYMENT DONE", callback_data="dep_done")]]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return WAITING_TRXID
    except ValueError:
        await update.message.reply_text("❌ PLEASE ENTER A VALID NUMBER!")
        return WAITING_AMOUNT

async def dep_done_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⚙️ **SEND PAYMENT TRANSACTION ID (TRXID):**", parse_mode="Markdown")
    return WAITING_TRXID

async def dep_trx_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    trx_id = update.message.text.strip()
    user = update.effective_user
    method = context.user_data.get('dep_method')
    amount = context.user_data.get('dep_amount')
    
    await update.message.reply_text("⏳ **DEPOSIT SUBMITTED FOR APPROVAL!**", reply_markup=get_main_keyboard(user.id))
    admin_kb = [[InlineKeyboardButton("✅ APPROVE", callback_data=f"depapp_app_{user.id}_{amount}"), InlineKeyboardButton("❌ REJECT", callback_data=f"depapp_rej_{user.id}_{amount}")]]
    await context.bot.send_message(ADMIN_ID, f"📥 **NEW DEPOSIT**\nUSER: {user.full_name.upper()} (`{user.id}`)\nMETHOD: {method}\nAMOUNT: {amount} BDT\nTRXID: `{trx_id}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(admin_kb))
    return ConversationHandler.END

async def dep_approval_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, act, uid, amt = query.data.split("_")
    uid, amt = int(uid), float(amt)
    if act == "app":
        new_bal = update_user_balance(uid, amt)
        await query.edit_message_text(f"{query.message.text}\n\n✅ **APPROVED**")
        await context.bot.send_message(uid, f"🎉 **DEPOSIT APPROVED!**\nADDED: `{amt} BDT`\nBALANCE: `{new_bal} BDT`", parse_mode="Markdown")
    else:
        await query.edit_message_text(f"{query.message.text}\n\n❌ **REJECTED**")
        await context.bot.send_message(uid, "❌ **DEPOSIT REJECTED!**")

# --- PROXY STORE & DELIVERY ---
async def show_proxy_store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT category, price, COUNT(*) FROM proxy_products GROUP BY category')
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        await update.message.reply_text("❌ NO PROXY STOCK AVAILABLE!")
        return
        
    kb = []
    for cat, price, count in items:
        kb.append([InlineKeyboardButton(f"{cat.upper()} - {price} BDT ({count} PCS)", callback_data=f"buyprx_{cat}")])
    await update.message.reply_text("🌐 **SELECT PROXY PACKAGE:**", reply_markup=InlineKeyboardMarkup(kb))

async def buy_proxy_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split("_")[1]
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, price, ip, port, username, password FROM proxy_products WHERE category = ? LIMIT 1', (cat,))
    row = cursor.fetchone()
    
    if not row:
        await query.edit_message_text("❌ OUT OF STOCK!")
        conn.close()
        return
        
    pid, price, ip, port, uname, pwd = row
    bal = get_user_balance(user_id)
    if bal < price:
        await query.edit_message_text(f"❌ **INSUFFICIENT BALANCE!**\nPRICE: `{price} BDT`\nYOUR BALANCE: `{bal} BDT`", parse_mode="Markdown")
        conn.close()
        return
        
    update_user_balance(user_id, -price)
    cursor.execute('DELETE FROM proxy_products WHERE id = ?', (pid,))
    cursor.execute('INSERT INTO sales_history (item_type, name, price) VALUES ("PROXY", ?, ?)', (cat, price))
    conn.commit()
    conn.close()
    
    deliv = (
        f"✅ **ORDER COMPLETED** ✨\n\n"
        f"📦 **PACKAGE:** PROXY ~ IP ➜ {cat.upper()}\n\n"
        f"🌐 **YOUR PRODUCT DETAILS:** ✨\n\n"
        f"🌐 **IP:** `{ip}`\n"
        f"⬆️ **PORT:** `{port}`\n"
        f"⭐ **USER:** `{uname}`\n"
        f"🔑 **PASS:** `{pwd}`\n\n"
        f"THANK YOU FOR YOUR PURCHASE!"
    )
    await query.edit_message_text(deliv, parse_mode="Markdown")

# --- VPN STORE & DELIVERY ---
async def start_vpn_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📅 3 DAYS", callback_data="vpndays_3"), InlineKeyboardButton("📅 7 DAYS", callback_data="vpndays_7")],
        [InlineKeyboardButton("📅 14 DAYS", callback_data="vpndays_14"), InlineKeyboardButton("📅 30 DAYS", callback_data="vpndays_30")]
    ]
    await update.message.reply_text("💥 **VPN PACKAGES** 💥\n\nSELECT DURATION: 🛡️", reply_markup=InlineKeyboardMarkup(kb))

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
    
    if not prods:
        await query.edit_message_text(f"❌ NO VPN PACKS AVAILABLE FOR {days} DAYS!")
        return
        
    kb = []
    for name, price in prods:
        kb.append([InlineKeyboardButton(f"{name.upper()} [{days} DAYS] - {price} BDT", callback_data=f"vpnpack_{name}_{price}")])
    await query.edit_message_text(f"💥 **VPN ({days} DAYS)** 💥\n\nSELECT VPN SERVICE: 🛡️", reply_markup=InlineKeyboardMarkup(kb))

async def vpn_pack_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, name, price = query.data.split("_")
    context.user_data['buy_vpn_name'] = name
    context.user_data['buy_vpn_price'] = float(price)
    
    kb = [
        [InlineKeyboardButton("1 PCS", callback_data="vpnqty_1"), InlineKeyboardButton("3 PCS", callback_data="vpnqty_3")],
        [InlineKeyboardButton("5 PCS", callback_data="vpnqty_5"), InlineKeyboardButton("10 PCS", callback_data="vpnqty_10")],
        [InlineKeyboardButton("📝 ENTER QUANTITY", callback_data="vpnqty_custom")]
    ]
    await query.edit_message_text(f"💥 **VPN** 💥 {name.upper()} [{context.user_data['buy_vpn_days']} DAYS]\n\nHOW MANY PIECES DO YOU WANT TO BUY? 🛡️", reply_markup=InlineKeyboardMarkup(kb))

async def vpn_qty_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")[1]
    
    if data == "custom":
        await query.edit_message_text("📝 **ENTER QUANTITY (NUMBER):**")
        return VPN_QTY_CUSTOM
    else:
        qty = int(data)
        return await finalize_vpn_order(update, context, qty, query)

async def vpn_custom_qty_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    try:
        qty = int(update.message.text.strip())
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
        msg = f"❌ **INSUFFICIENT BALANCE!**\nTOTAL: `{total_cost} BDT`\nBALANCE: `{bal} BDT`"
        if query: await query.edit_message_text(msg, parse_mode="Markdown")
        else: await update.message.reply_text(msg, parse_mode="Markdown")
        return ConversationHandler.END
        
    update_user_balance(user.id, -total_cost)
    
    user_msg = f"🎉 **ORDER SUBMITTED!**\n\n`YOUR VPN ORDER WILL BE DELIVERED WITHIN 20-50 MINUTES AFTER APPROVAL`"
    if query: await query.edit_message_text(user_msg, parse_mode="Markdown")
    else: await update.message.reply_text(user_msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    
    admin_req = f"🔔 **NEW VPN ORDER**\n\n👤 **USER:** {user.full_name.upper()} (`{user.id}`)\n📦 **VPN:** {name.upper()}\n📅 **DAYS:** {days}\n🔢 **QTY:** {qty}\n💰 **TOTAL COST:** {total_cost} BDT"
    kb = [[InlineKeyboardButton("🚀 DELIVER PRODUCT", callback_data=f"delivvpn_{user.id}")]]
    await context.bot.send_message(ADMIN_ID, admin_req, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# --- ADMIN MANUAL DELIVER ---
async def start_admin_deliver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_uid = query.data.split("_")[1]
    context.user_data['deliver_target_uid'] = target_uid
    await query.edit_message_text(f"🚀 **SEND PRODUCT DETAILS FOR USER `{target_uid}`:**", parse_mode="Markdown")
    return ADMIN_VPN_DELIVER

async def admin_deliver_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    target_uid = context.user_data.get('deliver_target_uid')
    details = update.message.text
    
    try:
        await context.bot.send_message(target_uid, f"🎁 **YOUR VPN ORDER DELIVERED!**\n\n{details}", parse_mode="Markdown")
        await update.message.reply_text("✅ PRODUCT SENT TO USER SUCCESSFULLY!")
    except Exception as e:
        await update.message.reply_text(f"❌ ERROR SENDING MESSAGE: {e}")
    return ConversationHandler.END

# --- ADD STOCK ---
async def start_add_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🌐 ENTER PROXY NAME:")
    return ADD_PROXY_NAME

async def add_proxy_name_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    context.user_data['stk_prx_name'] = update.message.text.strip().upper()
    await update.message.reply_text("💵 ENTER PRICE PER PROXY (BDT):")
    return ADD_PROXY_PRICE

async def add_proxy_price_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    try:
        context.user_data['stk_prx_price'] = float(update.message.text.strip())
        await update.message.reply_text("📝 SEND PROXIES LINE BY LINE:\nFORMAT: `IP:PORT:USERNAME:PASSWORD`")
        return ADD_PROXY_ITEMS
    except ValueError:
        await update.message.reply_text("❌ INVALID PRICE!")
        return ADD_PROXY_PRICE

async def add_proxy_items_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    lines = update.message.text.strip().split('\n')
    name = context.user_data.get('stk_prx_name')
    price = context.user_data.get('stk_prx_price')
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    added = 0
    for line in lines:
        parts = line.strip().split(':')
        if len(parts) == 4:
            cursor.execute('INSERT INTO proxy_products (category, price, ip, port, username, password) VALUES (?, ?, ?, ?, ?, ?)', (name, price, parts[0], parts[1], parts[2], parts[3]))
            added += 1
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ ADDED {added} PROXIES TO STOCK!", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

async def start_add_vpn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🛡️ ENTER VPN NAME:")
    return ADD_VPN_NAME

async def add_vpn_name_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    context.user_data['stk_vpn_name'] = update.message.text.strip().upper()
    await update.message.reply_text("📅 ENTER DAYS (E.G. 3, 7, 14, 30):")
    return ADD_VPN_DAYS

async def add_vpn_days_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    try:
        context.user_data['stk_vpn_days'] = int(update.message.text.strip())
        await update.message.reply_text("💵 ENTER PRICE (BDT):")
        return ADD_VPN_PRICE
    except ValueError:
        await update.message.reply_text("❌ INVALID NUMBER!")
        return ADD_VPN_DAYS

async def add_vpn_price_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    try:
        price = float(update.message.text.strip())
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

# --- P2P HANDLERS ---
async def show_p2p_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🔄 **P2P USDT TRADING ZONE**\n\n📢 **BUY USDT:** 1 $ = 130 ৳\n📢 **SELL USDT:** 1 $ = 122 ৳"
    kb = [[InlineKeyboardButton("💵 BUY USDT", callback_data="p2p_buy")], [InlineKeyboardButton("🔴 SELL USDT", callback_data="p2p_sell")]]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_buy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💵 CONTACT ADMIN TO BUY USDT: @ADMINSUPPORT")

async def p2p_sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [[InlineKeyboardButton("💗 BKASH", callback_data="p2psell_BKASH")], [InlineKeyboardButton("🧡 NAGAD", callback_data="p2psell_NAGAD")]]
    await query.edit_message_text("💳 SELECT PAYMENT METHOD TO RECEIVE BDT:", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_sell_method_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[1]
    context.user_data['p2p_method'] = method
    await query.edit_message_text(f"📞 ENTER YOUR {method} NUMBER:")
    return P2P_SELL_NUMBER

async def p2p_number_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return ConversationHandler.END
    context.user_data['p2p_number'] = update.message.text.strip()
    kb = [
        [InlineKeyboardButton("🟡 BINANCE PAY ID", callback_data="p2pnet_BINANCE")],
        [InlineKeyboardButton("🌐 BEP-20", callback_data="p2pnet_BEP20")],
        [InlineKeyboardButton("🌐 TRC-20", callback_data="p2pnet_TRC20")]
    ]
    await update.message.reply_text("🌐 SELECT NETWORK ADDRESS:", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_net_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    net = query.data.split("_")[1]
    addr = BINANCE_ID if net == "BINANCE" else BEP20_ADDRESS if net == "BEP20" else TRC20_ADDRESS
    context.user_data['p2p_net'] = net
    
    msg = f"📥 **SEND USDT TO THIS ADDRESS**\n\n🌐 **NETWORK:** {net}\n🔑 **ADDRESS:** `{addr}`\n\nCLICK **CONFIRM PAYMENT** AFTER SENDING."
    kb = [[InlineKeyboardButton("✅ CONFIRM PAYMENT", callback_data="p2p_confirm")]]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_confirm_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 **SEND SCREENSHOT / PROOF OF PAYMENT:**")
    return P2P_SELL_PROOF

async def p2p_proof_rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    method = context.user_data.get('p2p_method')
    number = context.user_data.get('p2p_number')
    net = context.user_data.get('p2p_net')
    
    await update.message.reply_text("⏳ **P2P REQUEST SUBMITTED!**", reply_markup=get_main_keyboard(user.id))
    admin_msg = f"🚨 **P2P SELL REQUEST**\nUSER: {user.full_name.upper()} (`{user.id}`)\nMETHOD: {method}\nNUMBER: `{number}`\nNETWORK: {net}"
    await context.bot.send_photo(ADMIN_ID, photo, caption=admin_msg, parse_mode="Markdown")
    return ConversationHandler.END

# --- GENERAL BUTTON HANDLER ---
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "💳 DEPOSIT": await deposit_start(update, context)
    elif text == "💰 BALANCE": await update.message.reply_text(f"📊 **YOUR BALANCE:** `{get_user_balance(user_id)} BDT`", parse_mode="Markdown")
    elif text == "🛡️ BUY VPN": await start_vpn_flow(update, context)
    elif text == "🌐 BUY PROXY": await show_proxy_store(update, context)
    elif text == "🔄 P2P (USDT BUY & SELL)": await show_p2p_menu(update, context)
    elif text == "👑 ADMIN PANEL": await admin_panel(update, context)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    # CONVERSATIONS
    dep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dep_method_selected, pattern="^dep_"), MessageHandler(filters.Regex("^(💳 DEPOSIT)$"), deposit_start)],
        states={
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dep_amount_received)],
            WAITING_TRXID: [CallbackQueryHandler(dep_done_clicked, pattern="^dep_done$"), MessageHandler(filters.TEXT & ~filters.COMMAND, dep_trx_received)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    vpn_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(vpn_qty_process, pattern="^vpnqty_")],
        states={VPN_QTY_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, vpn_custom_qty_received)]},
        fallbacks=[CommandHandler("start", start)]
    )
    
    admin_deliver_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_admin_deliver, pattern="^delivvpn_")],
        states={ADMIN_VPN_DELIVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_deliver_received)]},
        fallbacks=[CommandHandler("start", start)]
    )
    
    add_prx_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_proxy, pattern="^admin_add_proxy$")],
        states={
            ADD_PROXY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_proxy_name_rec)],
            ADD_PROXY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_proxy_price_rec)],
            ADD_PROXY_ITEMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_proxy_items_rec)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    add_vpn_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_vpn, pattern="^admin_add_vpn$")],
        states={
            ADD_VPN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_name_rec)],
            ADD_VPN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_days_rec)],
            ADD_VPN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vpn_price_rec)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    p2p_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(p2p_sell_method_rec, pattern="^p2psell_"), CallbackQueryHandler(p2p_confirm_clicked, pattern="^p2p_confirm$")],
        states={
            P2P_SELL_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, p2p_number_rec)],
            P2P_SELL_PROOF: [MessageHandler(filters.PHOTO, p2p_proof_rec)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    # HANDLERS REGISTER
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    
    app.add_handler(dep_conv)
    app.add_handler(vpn_conv)
    app.add_handler(admin_deliver_conv)
    app.add_handler(add_prx_conv)
    app.add_handler(add_vpn_conv)
    app.add_handler(p2p_conv)
    
    # CALLBACKS
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel_back$"))
    app.add_handler(CallbackQueryHandler(admin_deposit_requests, pattern="^admin_deposit_req$"))
    app.add_handler(CallbackQueryHandler(manage_vpn_stock, pattern="^admin_manage_vpn$"))
    app.add_handler(CallbackQueryHandler(manage_proxy_stock, pattern="^admin_manage_proxy$"))
    app.add_handler(CallbackQueryHandler(handle_stock_days_select, pattern="^days_"))
    
    app.add_handler(CallbackQueryHandler(dep_approval_handler, pattern="^depapp_"))
    app.add_handler(CallbackQueryHandler(show_proxy_store, pattern="^buy_proxy$"))
    app.add_handler(CallbackQueryHandler(buy_proxy_process, pattern="^buyprx_"))
    app.add_handler(CallbackQueryHandler(vpn_days_selected, pattern="^vpndays_"))
    app.add_handler(CallbackQueryHandler(vpn_pack_selected, pattern="^vpnpack_"))
    app.add_handler(CallbackQueryHandler(p2p_buy_info, pattern="^p2p_buy$"))
    app.add_handler(CallbackQueryHandler(p2p_sell_start, pattern="^p2p_sell$"))
    app.add_handler(CallbackQueryHandler(p2p_net_rec, pattern="^p2pnet_"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("BOT IS RUNNING PERFECTLY...")
    app.run_polling()

if __name__ == "__main__":
    main()
