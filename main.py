import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import psycopg2
from psycopg2.extras import RealDictCursor
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

TOKEN = "8733585059:AAEOznbOV6FEDmP-qk_VFRSzyuthX93r0Js"
ADMIN_ID = 7753794493

# 👉 আপনার Supabase DB Connection URL যুক্ত করা হয়েছে
SUPABASE_DB_URL = "postgresql://postgres:SHAKIL6880s@db.cbzrwwhmtishjzqykehm.supabase.co:5432/postgres"

def get_db_connection():
    return psycopg2.connect(SUPABASE_DB_URL)

# STATES
WAITING_AMOUNT, WAITING_DEP_PROOF = 1, 2
ADD_PROXY_NAME, ADD_PROXY_PRICE, ADD_PROXY_ITEMS = 3, 4, 5
ADD_VPN_NAME, ADD_VPN_DAYS, ADD_VPN_PRICE = 6, 7, 8
P2P_SELL_NUMBER, P2P_SELL_PROOF = 9, 10
VPN_QTY_CUSTOM, ADMIN_VPN_DELIVER = 11, 12
SET_BKASH, SET_NAGAD, SET_BINANCE, SET_BEP20, SET_TRC20 = 13, 14, 15, 16, 17
BROADCAST_MSG = 18
EDIT_VPN_NAME_STATE, EDIT_VPN_PRICE_STATE = 19, 20
EDIT_PRX_NAME_STATE, EDIT_PRX_PRICE_STATE = 21, 22

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, balance NUMERIC DEFAULT 0.0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS proxy_products (id SERIAL PRIMARY KEY, category TEXT, price NUMERIC, ip TEXT, port TEXT, username TEXT, password TEXT, status TEXT DEFAULT 'AVAILABLE')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vpn_products (id SERIAL PRIMARY KEY, name TEXT, days INT, price NUMERIC)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales_history (id SERIAL PRIMARY KEY, item_type TEXT, name TEXT, price NUMERIC, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    defaults = {
        "BKASH": "01869425239",
        "NAGAD": "01869425239",
        "BINANCE": "7753794493",
        "BEP20": "0x1234567890abcdef1234567890abcdef12345678",
        "TRC20": "TYz1234567890abcdef1234567890abcdef"
    }
    for k, v in defaults.items():
        cursor.execute('INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING', (k, v))
        
    conn.commit()
    cursor.close()
    conn.close()

def get_setting(key):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = %s', (key,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else "NOT SET"

def set_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value', (key, value))
    conn.commit()
    cursor.close()
    conn.close()

def get_user_balance(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = %s', (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute('INSERT INTO users (user_id, balance) VALUES (%s, %s)', (user_id, 0.0))
        conn.commit()
        cursor.close()
        conn.close()
        return 0.0
    cursor.close()
    conn.close()
    return float(row[0])

def update_user_balance(user_id, amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    current_bal = get_user_balance(user_id)
    new_bal = current_bal + amount
    cursor.execute('UPDATE users SET balance = %s WHERE user_id = %s', (new_bal, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return new_bal

def get_main_keyboard(user_id):
    kb = [
        ["🛡️ BUY VPN", "🌐 BUY PROXY"],
        ["🔄 P2P (USDT BUY & SELL)"],
        ["💳 DEPOSIT", "💰 BALANCE"]
    ]
    if user_id == ADMIN_ID:
        kb.append(["👑 ADMIN PANEL"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_balance(user.id)
    
    welcome_msg = (
        f"🎉 WELCOME TO DIGITAL SERVICE BOT! 🎉\n\n"
        f"👤 NAME: {user.first_name.upper()}\n"
        f"🆔 USER ID: `{user.id}`\n"
        f"💰 YOUR BALANCE: `{get_user_balance(user.id)}` BDT\n\n"
        f"PLEASE CHOOSE AN OPTION FROM THE MENU BELOW:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_buttons(update, context)
    return ConversationHandler.END

# --- ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM proxy_products WHERE status = \'AVAILABLE\'')
    proxy_avail = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM proxy_products WHERE status = \'SOLD\'')
    proxy_sold = cursor.fetchone()[0]
    total_proxy = proxy_avail + proxy_sold
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.close()
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

# --- DEPOSIT SYSTEM ---
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💗 BKASH", callback_data="depmeth_BKASH")],
        [InlineKeyboardButton("🧡 NAGAD", callback_data="depmeth_NAGAD")],
        [InlineKeyboardButton("🟡 BINANCE", callback_data="depmeth_BINANCE")]
    ]
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("💳 SELECT PAYMENT METHOD:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("💳 SELECT PAYMENT METHOD:", reply_markup=InlineKeyboardMarkup(kb))
    return WAITING_AMOUNT

async def dep_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("_")[1]
    context.user_data['dep_method'] = method
    
    num = get_setting(method)
    await query.edit_message_text(f"✅ METHOD: {method}\n📞 SEND TO ({'ID' if method=='BINANCE' else 'NUMBER'}): `{num}`\n\n💳 ENTER DEPOSIT AMOUNT (BDT):", parse_mode="Markdown")
    return WAITING_AMOUNT

async def dep_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text in ["🛡️ BUY VPN", "🌐 BUY PROXY", "🔄 P2P (USDT BUY & SELL)", "💳 DEPOSIT", "💰 BALANCE", "👑 ADMIN PANEL"]:
        await handle_buttons(update, context)
        return ConversationHandler.END

    try:
        amount = float(text)
        method = context.user_data.get('dep_method', 'BKASH')
        context.user_data['dep_amount'] = amount
        
        warn_text = ""
        if method == "BINANCE":
            usdt_amt = amount / 125.0
            warn_text = f"\n\n⚠️ WARNING: PLEASE SEND EXACTLY `{usdt_amt:.2f}` USDT (RATE: 125 BDT = 1$)"

        num = get_setting(method)
        text_summary = f"📥 DEPOSIT SUMMARY\n\n• METHOD: {method}\n• AMOUNT: `{amount}` BDT\n• ADDRESS/NO: `{num}`{warn_text}\n\nCLICK CONFIRM PAYMENT AFTER SENDING."
        kb = [[InlineKeyboardButton("✅ CONFIRM PAYMENT", callback_data="dep_confirm")]]
        await update.message.reply_text(text_summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return WAITING_DEP_PROOF
    except ValueError:
        await update.message.reply_text("❌ PLEASE ENTER A VALID NUMBER!")
        return WAITING_AMOUNT

async def dep_confirm_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 PLEASE SEND PAYMENT SCREENSHOT AS PROOF:")
    return WAITING_DEP_PROOF

async def dep_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    method = context.user_data.get('dep_method', 'N/A')
    amount = context.user_data.get('dep_amount', 0)
    
    await update.message.reply_text("⏳ DEPOSIT REQUEST CREATED! WAIT FOR VERIFICATION.", reply_markup=get_main_keyboard(user.id))
    
    admin_kb = [[InlineKeyboardButton("✅ APPROVE", callback_data=f"depapp_app_{user.id}_{amount}"), InlineKeyboardButton("❌ REJECT", callback_data=f"depapp_rej_{user.id}_{amount}")]]
    await context.bot.send_photo(
        ADMIN_ID, 
        photo, 
        caption=f"📥 NEW DEPOSIT REQUEST\n\n👤 USER: {user.full_name.upper()} (`{user.id}`)\n💳 METHOD: {method}\n💰 AMOUNT: `{amount}` BDT", 
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

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "💳 DEPOSIT": await deposit_start(update, context)
    elif text == "💰 BALANCE": await update.message.reply_text(f"📊 YOUR BALANCE: `{get_user_balance(user_id)}` BDT", parse_mode="Markdown")
    elif text == "👑 ADMIN PANEL": await admin_panel(update, context)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    fallback_buttons = [MessageHandler(filters.Regex("^(🛡️ BUY VPN|🌐 BUY PROXY|🔄 P2P \(USDT BUY & SELL\)|💳 DEPOSIT|💰 BALANCE|👑 ADMIN PANEL)$"), cancel_conversation)]
    
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
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(dep_conv)
    app.add_handler(CallbackQueryHandler(dep_approval_handler, pattern="^depapp_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("BOT RUNNING WITH SUPABASE DATABASE...")
    app.run_polling()

if __name__ == "__main__":
    main()
