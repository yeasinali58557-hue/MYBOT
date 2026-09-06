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
        self.wfile.write(b"Bot is running successfully!")

def run_dummy_server():
    try:
        server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")

# Logging Setup
logging.basicConfig(level=logging.INFO)

# Configs - Token & Admin ID
TOKEN = "8733585059:AAE3XL0aHVQ2gdw3BAm6RKkMSZeDXq8pe6g"
ADMIN_ID = 7753794493
DB_FILE = "bot_data.db"

# Payment Details
BKASH_NUMBER = "01869425239"
NAGAD_NUMBER = "01869425239"
BINANCE_ID = "7753794493"
BEP20_ADDRESS = "0x1234567890abcdef1234567890abcdef12345678"
TRC20_ADDRESS = "TYz1234567890abcdef1234567890abcdef"

# Conversation States
WAITING_AMOUNT, WAITING_TRXID = 1, 2
ADD_STOCK_NAME, ADD_STOCK_PRICE, ADD_STOCK_ITEMS = 3, 4, 5
BROADCAST_MSG = 6
P2P_SELL_AMOUNT, P2P_SELL_NUMBER, P2P_SELL_PROOF = 7, 8, 9

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    # Stock table (Proxy & VPN)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            name TEXT,
            price REAL,
            item_data TEXT
        )
    ''')
    # Pending Deposits
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
        f"👋 **Hello {user.first_name}!**\n\n"
        f"🆔 **User ID:** `{user.id}`\n"
        f"💰 **Balance:** `{get_user_balance(user.id)} BDT`\n\n"
        f"Select an option from below to continue:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))

# --- ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized!")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Proxy Stock", callback_data="admin_add_PROXY"), InlineKeyboardButton("➕ Add VPN Stock", callback_data="admin_add_VPN")],
        [InlineKeyboardButton("📥 Deposit Requests", callback_data="admin_view_deposits")],
        [InlineKeyboardButton("📢 Broadcast Notice", callback_data="admin_broadcast")]
    ]
    await update.message.reply_text("👑 **ADMIN PANEL**\nChoose an action:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def addbal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
        new_bal = update_user_balance(target_id, amount)
        await update.message.reply_text(f"✅ Balance Updated! User `{target_id}` New Balance: `{new_bal} BDT`", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 **Deposit Added!**\n\n`{amount} BDT` added by Admin.\nNew Balance: `{new_bal} BDT`",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    except Exception:
        await update.message.reply_text("❌ Usage: `/addbal USER_ID AMOUNT`", parse_mode="Markdown")

# --- ADMIN STOCK ADDITION FLOW ---
async def start_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split("_")[2] # PROXY or VPN
    context.user_data['stock_cat'] = cat
    await query.edit_message_text(f"📦 Enter Product Name for **{cat}** (e.g. `9Proxy Premium`):", parse_mode="Markdown")
    return ADD_STOCK_NAME

async def stock_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['stock_name'] = update.message.text.strip()
    await update.message.reply_text("💵 Enter Price per unit (BDT) (e.g. `120`):")
    return ADD_STOCK_PRICE

async def stock_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        context.user_data['stock_price'] = price
        await update.message.reply_text(
            "📝 Send stock items **line by line** (Each line = 1 unit stock).\n\n"
            "Example:\n`user1:pass1:ip1`\n`user2:pass2:ip2`"
        )
        return ADD_STOCK_ITEMS
    except ValueError:
        await update.message.reply_text("❌ Invalid price! Enter a valid number:")
        return ADD_STOCK_PRICE

async def stock_items_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    await update.message.reply_text(f"✅ Successfully added **{len(items)}** items to **{name}** ({cat}) stock!", parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

# --- ADMIN BROADCAST FLOW ---
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 Send the message you want to broadcast to all users:")
    return BROADCAST_MSG

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    users = get_all_users()
    count = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **ANNOUNCEMENT**\n\n{msg}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Notice successfully sent to **{count}** users!", parse_mode="Markdown", reply_markup=get_main_keyboard(ADMIN_ID))
    return ConversationHandler.END

# --- DEPOSIT FLOW ---
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💗 BKASH", callback_data="method_Bkash")],
        [InlineKeyboardButton("🧡 NAGAD", callback_data="method_Nagad")],
        [InlineKeyboardButton("🟡 BINANCE", callback_data="method_Binance")]
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
    
    number = BKASH_NUMBER if method == "Bkash" else NAGAD_NUMBER if method == "Nagad" else BINANCE_ID
    label_num = "নাম্বার" if method != "Binance" else "আইডি"
    
    text = (
        f"✅ **মেথড: {method}**  🔹\n"
        f"📞 **{label_num}: `{number}`**\n\n"
        f"💳 **এবার অ্যামাউন্ট লিখুন:** ⚡"
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    return WAITING_AMOUNT

async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # Check if user clicked a menu button instead
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "🔄 P2P(USDT BUY & SELL)", "💳 DEPOSIT", "💰 BALANCE", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END
        
    try:
        amount = float(text)
        if amount <= 0:
            await update.message.reply_text("❌ Invalid amount! Please enter a valid number:")
            return WAITING_AMOUNT
            
        context.user_data['deposit_amount'] = amount
        method = context.user_data.get('deposit_method', 'Bkash')
        number = BKASH_NUMBER if method == "Bkash" else NAGAD_NUMBER if method == "Nagad" else BINANCE_ID
        
        msg = (
            f"📥 **DEPOSIT DETAILS**\n\n"
            f"• **Method:** {method}\n"
            f"• **Amount:** {amount} BDT\n"
            f"• **Send To:** `{number}`\n\n"
            f"Payment করার পর নিচে **Payment Done** বাটনে ক্লিক করুন:"
        )
        keyboard = [[InlineKeyboardButton("✅ Payment Done", callback_data="payment_done")]]
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return WAITING_TRXID
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number for amount:")
        return WAITING_AMOUNT

async def payment_done_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⚙️ **Send Payment Transaction ID (TrxID):**", parse_mode="Markdown")
    return WAITING_TRXID

async def trxid_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trx_id = update.message.text.strip()
    if trx_id in ["🛡️ BUY VPN", "🌐 BUY PROXY", "🔄 P2P(USDT BUY & SELL)", "💳 DEPOSIT", "💰 BALANCE", "👑 ADMIN PANEL"]:
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
    
    await update.message.reply_text("⏳ **Deposit Request Submitted!**\nAdmin will verify shortly.", parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    
    # Notify Admin
    admin_notify = (
        f"📥 **NEW DEPOSIT REQUEST**\n━━━━━━━━━━━━━━━━━━\n"
        f"👤 **User:** {user.full_name} (`{user.id}`)\n"
        f"💳 **Method:** {method}\n💰 **Amount:** `{amount} BDT`\n🔑 **TrxID:** `{trx_id}`\n━━━━━━━━━━━━━━━━━━"
    )
    admin_kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"dep_app_{user.id}_{amount}"), InlineKeyboardButton("❌ Reject", callback_data=f"dep_rej_{user.id}_{amount}")]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_notify, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(admin_kb))
    return ConversationHandler.END

# --- DEPOSIT APPROVAL ---
async def admin_deposit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    action, target_id, amount = data[1], int(data[2]), float(data[3])
    
    if action == "app":
        new_bal = update_user_balance(target_id, amount)
        await query.edit_message_text(f"{query.message.text}\n\n✅ **STATUS: APPROVED (+{amount} BDT)**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 **Deposit Approved!**\n\n💰 Added: `{amount} BDT`\n💳 Current Balance: `{new_bal} BDT`", parse_mode="Markdown")
        except Exception:
            pass
    elif action == "rej":
        await query.edit_message_text(f"{query.message.text}\n\n❌ **STATUS: REJECTED**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"❌ Your deposit request for `{amount} BDT` was rejected.", parse_mode="Markdown")
        except Exception:
            pass

# --- BUY STORE (PROXY & VPN) ---
async def show_store(update: Update, context: ContextTypes.DEFAULT_TYPE, category):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT name, price FROM products WHERE category = ?', (category,))
    prods = cursor.fetchall()
    conn.close()
    
    if not prods:
        await update.message.reply_text(f"❌ Currently no **{category}** stock available!", parse_mode="Markdown")
        return
        
    kb = []
    for name, price in prods:
        kb.append([InlineKeyboardButton(f"{name} - {price} BDT", callback_data=f"buy_p_{category}_{name}")])
    
    await update.message.reply_text(f"🛒 **AVAILABLE {category} STORE**\nSelect product to purchase:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

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
        await query.edit_message_text("❌ Out of stock!")
        conn.close()
        return
        
    item_id, price, item_data = row
    bal = get_user_balance(user_id)
    
    if bal < price:
        await query.edit_message_text(f"❌ **Insufficient Balance!**\nProduct Price: `{price} BDT`\nYour Balance: `{bal} BDT`\nPlease deposit first.", parse_mode="Markdown")
        conn.close()
        return
        
    # Deduct Balance & Remove Item from Stock
    update_user_balance(user_id, -price)
    cursor.execute('DELETE FROM products WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    
    delivery_text = (
        f"🎉 **PURCHASE SUCCESSFUL!**\n━━━━━━━━━━━━━━━━━━\n"
        f"📦 **Product:** {name}\n"
        f"💵 **Price:** `{price} BDT`\n"
        f"🗝️ **Details:**\n`{item_data}`\n━━━━━━━━━━━━━━━━━━\n"
        f"Thank you for buying!"
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
    await query.edit_message_text("💵 **To Buy USDT, please contact Admin directly.**\nAdmin: @AdminSupport", parse_mode="Markdown")

async def p2p_sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("💗 BKASH", callback_data="p2p_method_Bkash")],
        [InlineKeyboardButton("🧡 NAGAD", callback_data="p2p_method_Nagad")]
    ]
    await query.edit_message_text("💳 **Select BDT Payment Method to receive money:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[2]
    context.user_data['p2p_bdt_method'] = method
    await query.edit_message_text(f"📞 Enter your **{method}** account number to receive BDT:")
    return P2P_SELL_NUMBER

async def p2p_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p2p_number'] = update.message.text.strip()
    kb = [
        [InlineKeyboardButton("🟡 BINANCE Pay ID", callback_data="p2p_addr_Binance")],
        [InlineKeyboardButton("🌐 BEP-20 (BSC)", callback_data="p2p_addr_BEP20")],
        [InlineKeyboardButton("🌐 TRC-20 (TRON)", callback_data="p2p_addr_TRC20")]
    ]
    await update.message.reply_text("🌐 **Select Network Address to send USDT:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_addr_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    net = query.data.split("_")[2]
    
    addr = BINANCE_ID if net == "Binance" else BEP20_ADDRESS if net == "BEP20" else TRC20_ADDRESS
    context.user_data['p2p_network'] = net
    
    msg = (
        f"📥 **SEND USDT TO THIS ADDRESS**\n━━━━━━━━━━━━━━━━━━\n"
        f"🌐 **Network:** {net}\n"
        f"🔑 **Address / ID:** `{addr}`\n━━━━━━━━━━━━━━━━━━\n"
        f" Send USDT and click **Confirm Payment** below:"
    )
    kb = [[InlineKeyboardButton("✅ Confirm Payment", callback_data="p2p_confirm_sent")]]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def p2p_confirm_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 Please send a **Screenshot / Photo** as proof of payment:")
    return P2P_SELL_PROOF

async def p2p_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    bdt_method = context.user_data.get('p2p_bdt_method')
    bdt_number = context.user_data.get('p2p_number')
    network = context.user_data.get('p2p_network')
    
    await update.message.reply_text("⏳ **P2P Sell Request Submitted!** Admin will review and send BDT soon.", reply_markup=get_main_keyboard(user.id))
    
    admin_msg = (
        f"🚨 **NEW P2P SELL USDT REQUEST**\n━━━━━━━━━━━━━━━━━━\n"
        f"👤 **User:** {user.full_name} (`{user.id}`)\n"
        f"💳 **Receive Method:** {bdt_method}\n"
        f"📞 **Receive Number:** `{bdt_number}`\n"
        f"🌐 **Network:** {network}\n━━━━━━━━━━━━━━━━━━"
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
        await update.message.reply_text(f"📊 **ACCOUNT BALANCE**\n\n🆔 User ID: `{user_id}`\n💰 Balance: `{bal} BDT`", parse_mode="Markdown")
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
    
    # Deposit Conversation
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
        fallbacks=[]
    )
    
    # Admin Stock Conversation
    admin_stock_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_stock, pattern="^admin_add_")],
        states={
            ADD_STOCK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_name_received)],
            ADD_STOCK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_price_received)],
            ADD_STOCK_ITEMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, stock_items_received)]
        },
        fallbacks=[]
    )
    
    # Admin Broadcast Conversation
    admin_bc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_broadcast, pattern="^admin_broadcast$")],
        states={BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast)]},
        fallbacks=[]
    )
    
    # P2P Sell Conversation
    p2p_sell_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(p2p_method_selected, pattern="^p2p_method_"),
            CallbackQueryHandler(p2p_confirm_sent, pattern="^p2p_confirm_sent$")
        ],
        states={
            P2P_SELL_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, p2p_number_received)],
            P2P_SELL_PROOF: [MessageHandler(filters.PHOTO, p2p_proof_received)]
        },
        fallbacks=[]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("addbal", addbal_cmd))
    app.add_handler(deposit_conv)
    app.add_handler(admin_stock_conv)
    app.add_handler(admin_bc_conv)
    app.add_handler(p2p_sell_conv)
    
    app.add_handler(CallbackQueryHandler(admin_deposit_callback, pattern="^dep_(app|rej)_"))
    app.add_handler(CallbackQueryHandler(process_buy_product, pattern="^buy_p_"))
    app.add_handler(CallbackQueryHandler(p2p_buy_info, pattern="^p2p_buy_info$"))
    app.add_handler(CallbackQueryHandler(p2p_sell_start, pattern="^p2p_sell_start$"))
    app.add_handler(CallbackQueryHandler(p2p_addr_selected, pattern="^p2p_addr_"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
