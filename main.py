import logging
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, ConversationHandler, filters
)

# --- DUMMY WEB SERVER FOR RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BOT IS RUNNING SUCCESSFULLY!")

def run_dummy_server():
    try:
        server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        print(f"SERVER ERROR: {e}")

# LOGGING SETUP
logging.basicConfig(level=logging.INFO)

# CONFIGS - TOKEN & ADMIN ID
TOKEN = "8733585059:AAE3XL0aHVQ2gdw3BAm6RKkMSZeDXq8pe6g"
ADMIN_ID = 7753794493
DB_FILE = "bot_data.db"

# PAYMENT DETAILS
BKASH_NUMBER = "01869425239"
NAGAD_NUMBER = "01869425239"
BINANCE_ID = "7753794493"
BEP20_ADDRESS = "0x1234567890abcdef1234567890abcdef12345678"
TRC20_ADDRESS = "TYz1234567890abcdef1234567890abcdef"

# CONVERSATION STATES
WAITING_AMOUNT, WAITING_TRXID = 1, 2
ADD_STOCK_NAME, ADD_STOCK_PRICE, ADD_STOCK_ITEMS = 3, 4, 5
BROADCAST_MSG = 6
P2P_SELL_NUMBER, P2P_SELL_PROOF = 7, 8

MENU_BUTTONS = ["🛡️ BUY VPN", "🌐 BUY PROXY", "🔄 P2P(USDT BUY & SELL)", "💳 DEPOSIT", "💰 BALANCE", "👑 ADMIN PANEL"]

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            name TEXT,
            price REAL,
            item_data TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            method TEXT,
            amount REAL,
            trxid TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
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

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

# --- KEYBOARDS ---
def get_main_keyboard(user_id):
    kb = [
        ["🛡️ BUY VPN", "🌐 BUY PROXY"],
        ["🔄 P2P(USDT BUY & SELL)"],
        ["💳 DEPOSIT", "💰 BALANCE"]
    ]
    if user_id == ADMIN_ID:
        kb.append(["👑 ADMIN PANEL"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# --- START & MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_balance(user.id)
    
    welcome_msg = (
        f"👋 **HELLO {user.first_name.upper()}!**\n\n"
        f"🆔 **USER ID:** `{user.id}`\n"
        f"💰 **BALANCE:** `{get_user_balance(user.id)} BDT`\n\n"
        f"SELECT AN OPTION FROM BELOW TO CONTINUE:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    return ConversationHandler.END

# --- ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ YOU ARE NOT AUTHORIZED!")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("➕ ADD PROXY STOCK", callback_data="admin_add_PROXY"), InlineKeyboardButton("➕ ADD VPN STOCK", callback_data="admin_add_VPN")],
        [InlineKeyboardButton("📥 DEPOSIT REQUESTS", callback_data="admin_view_deposits")],
        [InlineKeyboardButton("📢 BROADCAST NOTICE", callback_data="admin_broadcast")]
    ]
    await update.message.reply_text("👑 **ADMIN PANEL**\nCHOOSE AN ACTION:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def addbal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
        new_bal = update_user_balance(target_id, amount)
        await update.message.reply_text(f"✅ BALANCE UPDATED! USER `{target_id}` NEW BALANCE: `{new_bal} BDT`", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 **DEPOSIT ADDED!**\n\n`{amount} BDT` ADDED BY ADMIN.\nNEW BALANCE: `{new_bal} BDT`",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    except Exception:
        await update.message.reply_text("❌ USAGE: `/addbal USER_ID AMOUNT`", parse_mode="Markdown")

# --- ADMIN APPROVAL HANDLERS ---
async def handle_deposit_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    action = data[1] # app or rej
    target_user_id = int(data[2])
    amount = float(data[3])
    
    if action == "app":
        new_bal = update_user_balance(target_user_id, amount)
        await query.edit_message_caption(caption=f"{query.message.caption or query.message.text}\n\n✅ **APPROVED BY ADMIN**", parse_mode="Markdown") if query.message.photo else await query.edit_message_text(f"{query.message.text}\n\n✅ **APPROVED BY ADMIN**", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 **DEPOSIT APPROVED!**\n\nYOUR DEPOSIT OF `{amount} BDT` HAS BEEN APPROVED.\nCURRENT BALANCE: `{new_bal} BDT`",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    elif action == "rej":
        await query.edit_message_text(f"{query.message.text}\n\n❌ **REJECTED BY ADMIN**", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"❌ **DEPOSIT REJECTED!**\n\nYOUR DEPOSIT OF `{amount} BDT` WAS REJECTED BY ADMIN.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

# --- ADMIN STOCK ADDITION FLOW ---
async def start_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split("_")[2]
    context.user_data['stock_cat'] = cat
    await query.edit_message_text(f"📦 ENTER PRODUCT NAME FOR **{cat}** (E.G. `9PROXY PREMIUM`):", parse_mode="Markdown")
    return ADD_STOCK_NAME

async def stock_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS:
        await handle_buttons(update, context)
        return ConversationHandler.END
    context.user_data['stock_name'] = update.message.text.strip().upper()
    await update.message.reply_text("💵 ENTER PRICE PER UNIT (BDT) (E.G. `120`):")
    return ADD_STOCK_PRICE

async def stock_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS:
        await handle_buttons(update, context)
        return ConversationHandler.END
    try:
        price = float(update.message.text.strip())
        context.user_data['stock_price'] = price
        await update.message.reply_text(
            "📝 SEND STOCK ITEMS **LINE BY LINE** (EACH LINE = 1 UNIT STOCK).\n\n"
            "EXAMPLE:\n`USER1:PASS1:IP1`\n`USER2:PASS2:IP2`"
        )
        return ADD_STOCK_ITEMS
    except ValueError:
        await update.message.reply_text("❌ INVALID PRICE! ENTER A VALID NUMBER:")
        return ADD_STOCK_PRICE

async def stock_items_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS:
        await handle_buttons(update, context)
        return ConversationHandler.END
    items = [line.strip() for line in update.message.text.strip().split('\n') if line.strip()]
    cat = context.user_data.get('stock_cat')
    name = context.user_data.get('stock_name')
    price = context.user_data.get('stock_price')
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for item in items:
        cursor.execute('INSERT INTO products (category, name, price, item_data) VALUES (?, ?, ?, ?)', (cat, name, price, item))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ SUCCESSFULLY ADDED **{len(items)}** ITEMS TO **{name}** ({cat}) STOCK!", parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

# --- ADMIN BROADCAST FLOW ---
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 SEND THE MESSAGE YOU WANT TO BROADCAST TO ALL USERS:")
    return BROADCAST_MSG

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS:
        await handle_buttons(update, context)
        return ConversationHandler.END
    msg = update.message.text.upper()
    users = get_all_users()
    count = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **ANNOUNCEMENT**\n\n{msg}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ NOTICE SUCCESSFULLY SENT TO **{count}** USERS!", parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

# --- DEPOSIT FLOW ---
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💗 BKASH", callback_data="method_BKASH")],
        [InlineKeyboardButton("🧡 NAGAD", callback_data="method_NAGAD")],
        [InlineKeyboardButton("🟡 BINANCE", callback_data="method_BINANCE")]
    ]
    await update.message.reply_text(
        "⚡ **SELECT PAYMENT METHOD** ⚡", 
        parse_mode="Markdown", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[1]
    context.user_data['deposit_method'] = method
    
    number = BKASH_NUMBER if method == "BKASH" else NAGAD_NUMBER if method == "NAGAD" else BINANCE_ID
    label_num = "NUMBER" if method != "BINANCE" else "ID"
    
    text = (
        f"✅ **METHOD: {method}**\n"
        f"📞 **{label_num}: `{number}`**\n\n"
        f"💳 **ENTER DEPOSIT AMOUNT (BDT):**"
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    return WAITING_AMOUNT

async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in MENU_BUTTONS:
        await handle_buttons(update, context)
        return ConversationHandler.END
        
    try:
        amount = float(text)
        if amount <= 0:
            await update.message.reply_text("❌ INVALID AMOUNT! PLEASE ENTER A VALID NUMBER:")
            return WAITING_AMOUNT
            
        context.user_data['deposit_amount'] = amount
        method = context.user_data.get('deposit_method', 'BKASH')
        number = BKASH_NUMBER if method == "BKASH" else NAGAD_NUMBER if method == "NAGAD" else BINANCE_ID
        
        msg = (
            f"📥 **DEPOSIT DETAILS**\n\n"
            f"• **METHOD:** {method}\n"
            f"• **AMOUNT:** {amount} BDT\n"
            f"• **SEND TO:** `{number}`\n\n"
            f"AFTER PAYMENT, CLICK **PAYMENT DONE** BELOW:"
        )
        keyboard = [[InlineKeyboardButton("✅ PAYMENT DONE", callback_data="payment_done")]]
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return WAITING_TRXID
    except ValueError:
        await update.message.reply_text("❌ PLEASE ENTER A VALID NUMBER FOR AMOUNT:")
        return WAITING_AMOUNT

async def payment_done_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⚙️ **SEND PAYMENT TRANSACTION ID (TRXID):**", parse_mode="Markdown")
    return WAITING_TRXID

async def trxid_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trx_id = update.message.text.strip()
    if trx_id in MENU_BUTTONS:
        await handle_buttons(update, context)
        return ConversationHandler.END
        
    user = update.effective_user
    method = context.user_data.get('deposit_method', 'N/A')
    amount = context.user_data.get('deposit_amount', 0.0)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO deposits (user_id, method, amount, trxid) VALUES (?, ?, ?, ?)', (user.id, method, amount, trx_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("⏳ **DEPOSIT REQUEST SUBMITTED!**\nADMIN WILL VERIFY SHORTLY.", parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    
    admin_notify = (
        f"📥 **NEW DEPOSIT REQUEST**\n━━━━━━━━━━━━━━━━━━\n"
        f"👤 **USER:** {user.full_name.upper()} (`{user.id}`)\n"
        f"💳 **METHOD:** {method}\n💰 **AMOUNT:** `{amount} BDT`\n🔑 **TRXID:** `{trx_id}`\n━━━━━━━━━━━━━━━━━━"
    )
    admin_kb = [[InlineKeyboardButton("✅ APPROVE", callback_data=f"dep_app_{user.id}_{amount}"), InlineKeyboardButton("❌ REJECT", callback_data=f"dep_rej_{user.id}_{amount}")]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_notify, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(admin_kb))
    return ConversationHandler.END

# --- BUY STORE (PROXY & VPN) ---
async def show_store(update: Update, context: ContextTypes.DEFAULT_TYPE, category):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT name, price FROM products WHERE category = ?', (category,))
    prods = cursor.fetchall()
    conn.close()
    
    if not prods:
        await update.message.reply_text(f"❌ CURRENTLY NO **{category}** STOCK AVAILABLE!", parse_mode="Markdown")
        return
        
    kb = []
    for name, price in prods:
        kb.append([InlineKeyboardButton(f"{name} - {price} BDT", callback_data=f"buy_p_{category}_{name}")])
    
    await update.message.reply_text(f"🛒 **AVAILABLE {category} STORE**\nSELECT PRODUCT TO PURCHASE:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def process_buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, cat, name = query.data.split("_", 3)
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, price, item_data FROM products WHERE category = ? AND name = ? LIMIT 1', (cat, name))
    row = cursor.fetchone()
    
    if not row:
        await query.edit_message_text("❌ OUT OF STOCK!")
        conn.close()
        return
        
    item_id, price, item_data = row
    bal = get_user_balance(user_id)
    
    if bal < price:
        await query.edit_message_text(f"❌ **INSUFFICIENT BALANCE!**\nPRODUCT PRICE: `{price} BDT`\nYOUR BALANCE: `{bal} BDT`\nPLEASE DEPOSIT FIRST.", parse_mode="Markdown")
        conn.close()
        return
        
    update_user_balance(user_id, -price)
    cursor.execute('DELETE FROM products WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    
    delivery_text = (
        f"🎉 **PURCHASE SUCCESSFUL!**\n━━━━━━━━━━━━━━━━━━\n"
        f"📦 **PRODUCT:** {name}\n"
        f"💵 **PRICE:** `{price} BDT`\n"
        f"🗝️ **DETAILS:**\n`{item_data}`\n━━━━━━━━━━━━━━━━━━\n"
        f"THANK YOU FOR BUYING!"
    )
    await query.edit_message_text(delivery_text, parse_mode="Markdown")

# --- P2P SECTION ---
async def show_p2p_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔄 **P2P USDT TRADING ZONE**\n━━━━━━━━━━━━━━━━━━\n"
        "📢 **BUY USDT**\n1 $ = 130 ৳\n\n"
        "📢 **SELL USDT**\n1 $ = 122 ৳\n━━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [InlineKeyboardButton("💵 BUY USDT (130৳)", callback_data="p2p_buy_info")],
        [InlineKeyboardButton("🔴 SELL USDT (122৳)", callback_data="p2p_sell_start")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_buy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💵 **TO BUY USDT, PLEASE CONTACT ADMIN DIRECTLY.**\nADMIN: @ADMINSUPPORT", parse_mode="Markdown")

async def p2p_sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("💗 BKASH", callback_data="p2p_method_BKASH")],
        [InlineKeyboardButton("🧡 NAGAD", callback_data="p2p_method_NAGAD")]
    ]
    await query.edit_message_text("💳 **SELECT BDT PAYMENT METHOD TO RECEIVE MONEY:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[2]
    context.user_data['p2p_bdt_method'] = method
    await query.edit_message_text(f"📞 ENTER YOUR **{method}** ACCOUNT NUMBER TO RECEIVE BDT:")
    return P2P_SELL_NUMBER

async def p2p_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS:
        await handle_buttons(update, context)
        return ConversationHandler.END
    context.user_data['p2p_number'] = update.message.text.strip()
    kb = [
        [InlineKeyboardButton("🟡 BINANCE PAY ID", callback_data="p2p_addr_BINANCE")],
        [InlineKeyboardButton("🌐 BEP-20 (BSC)", callback_data="p2p_addr_BEP20")],
        [InlineKeyboardButton("🌐 TRC-20 (TRON)", callback_data="p2p_addr_TRC20")]
    ]
    await update.message.reply_text("🌐 **SELECT NETWORK ADDRESS TO SEND USDT:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_addr_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    net = query.data.split("_")[2]
    
    addr = BINANCE_ID if net == "BINANCE" else BEP20_ADDRESS if net == "BEP20" else TRC20_ADDRESS
    context.user_data['p2p_network'] = net
    
    msg = (
        f"📥 **SEND USDT TO THIS ADDRESS**\n━━━━━━━━━━━━━━━━━━\n"
        f"🌐 **NETWORK:** {net}\n"
        f"🔑 **ADDRESS / ID:** `{addr}`\n━━━━━━━━━━━━━━━━━━\n"
        f"SEND USDT AND CLICK **CONFIRM PAYMENT** BELOW:"
    )
    kb = [[InlineKeyboardButton("✅ CONFIRM PAYMENT", callback_data="p2p_confirm_sent")]]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_confirm_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 **PLEASE SEND A SCREENSHOT / PHOTO AS PROOF OF PAYMENT:**", parse_mode="Markdown")
    return P2P_SELL_PROOF

async def p2p_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    bdt_method = context.user_data.get('p2p_bdt_method', 'N/A')
    bdt_number = context.user_data.get('p2p_number', 'N/A')
    network = context.user_data.get('p2p_network', 'N/A')
    
    await update.message.reply_text("⏳ **P2P SELL REQUEST SUBMITTED!** ADMIN WILL REVIEW AND SEND BDT SOON.", reply_markup=get_main_keyboard(user.id))
    
    admin_msg = (
        f"🚨 **NEW P2P SELL USDT REQUEST**\n━━━━━━━━━━━━━━━━━━\n"
        f"👤 **USER:** {user.full_name.upper()} (`{user.id}`)\n"
        f"💳 **RECEIVE METHOD:** {bdt_method}\n"
        f"📞 **RECEIVE NUMBER:** `{bdt_number}`\n"
        f"🌐 **NETWORK:** {network}\n━━━━━━━━━━━━━━━━━━"
    )
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo, caption=admin_msg, parse_mode="Markdown")
    return ConversationHandler.END

# --- GENERAL BUTTON HANDLERS ---
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "💳 DEPOSIT":
        await deposit_start(update, context)
    elif text == "💰 BALANCE":
        bal = get_user_balance(user_id)
        await update.message.reply_text(f"📊 **ACCOUNT BALANCE**\n\n🆔 USER ID: `{user_id}`\n💰 BALANCE: `{bal} BDT`", parse_mode="Markdown")
    elif text == "🛡️ BUY VPN":
        await show_store(update, context, "VPN")
    elif text == "🌐 BUY PROXY":
        await show_store(update, context, "PROXY")
    elif text == "🔄 P2P(USDT BUY & SELL)":
        await show_p2p_menu(update, context)
    elif text == "👑 ADMIN PANEL":
        await admin_panel(update, context)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    # DEPOSIT CONVERSATION
    deposit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(method_selected, pattern="^method_"),
            MessageHandler(filters.Regex("^(💳 DEPOSIT)$"), deposit_start)
        ],
        states={
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
            WAITING_TRXID: [
                CallbackQueryHandler(payment_done_clicked, pattern="^payment_done$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, trxid_received)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    # ADMIN STOCK CONVERSATION
    admin_stock_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_stock, pattern="^admin_add_")],
        states={
            ADD_STOCK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_name_received)],
            ADD_STOCK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_price_received)],
            ADD_STOCK_ITEMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_items_received)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    # ADMIN BROADCAST CONVERSATION
    admin_bc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_broadcast, pattern="^admin_broadcast$")],
        states={BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast)]},
        fallbacks=[CommandHandler("start", start)]
    )
    
    # P2P SELL CONVERSATION
    p2p_sell_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(p2p_method_selected, pattern="^p2p_method_"),
            CallbackQueryHandler(p2p_confirm_sent, pattern="^p2p_confirm_sent$")
        ],
        states={
            P2P_SELL_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, p2p_number_received)],
            P2P_SELL_PROOF: [MessageHandler(filters.PHOTO, p2p_proof_received)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    # COMMANDS
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("addbal", addbal_cmd))
    
    # CONVERSATIONS
    app.add_handler(deposit_conv)
    app.add_handler(admin_stock_conv)
    app.add_handler(admin_bc_conv)
    app.add_handler(p2p_sell_conv)
    
    # CALLBACK HANDLERS
    app.add_handler(CallbackQueryHandler(handle_deposit_approval, pattern="^dep_"))
    app.add_handler(CallbackQueryHandler(process_buy_product, pattern="^buy_p_"))
    app.add_handler(CallbackQueryHandler(p2p_buy_info, pattern="^p2p_buy_info$"))
    app.add_handler(CallbackQueryHandler(p2p_sell_start, pattern="^p2p_sell_start$"))
    app.add_handler(CallbackQueryHandler(p2p_addr_selected, pattern="^p2p_addr_"))
    
    # GENERAL MESSAGE HANDLER
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("BOT IS RUNNING...")
    app.run_polling()

if __name__ == "__main__":
    main()
