import logging
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, ConversationHandler, filters
)

# --- DUMMY WEB SERVER FOR RENDER PORT BINDING ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
    server.serve_forever()

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

# Conversation States
WAITING_AMOUNT = 1
WAITING_TRXID = 2

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

# --- KEYBOARDS ---
MAIN_KEYBOARD = [
    ["🛡️ BUY VPN", "🌐 BUY PROXY"],
    ["🔄 P2P(USDT BUY & SELL)"],
    ["💳 DEPOSIT", "💰 BALANCE"]
]
reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

# --- START & MENU HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_balance(user.id)
    
    welcome_msg = (
        f"👋 **Hello {user.first_name}!**\n\n"
        f"🆔 **User ID:** `{user.id}`\n"
        f"💰 **Balance:** `{get_user_balance(user.id)} BDT`\n\n"
        f"Select an option from below to continue:"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=reply_markup)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to access Admin Panel.")
        return
    
    admin_text = (
        "👑 **ADMIN PANEL**\n\n"
        "Commands:\n"
        "• Add Balance: `/addbal USER_ID AMOUNT`"
    )
    await update.message.reply_text(admin_text, parse_mode="Markdown")

async def addbal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
        new_bal = update_user_balance(target_id, amount)
        await update.message.reply_text(f"✅ Balance Updated!\nUser `{target_id}` New Balance: `{new_bal} BDT`", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 **Deposit Added!**\n\n`{amount} BDT` has been added to your account.\nNew Balance: `{new_bal} BDT`",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    except Exception:
        await update.message.reply_text("❌ Usage: `/addbal USER_ID AMOUNT`", parse_mode="Markdown")

# --- DEPOSIT CONVERSATION FLOW ---
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
        f"📞 **{label_num}: {number}**\n\n"
        f"💳 **এবার অ্যামাউন্ট লিখুন:** ⚡"
    )
    
    await query.edit_message_text(text, parse_mode="Markdown")
    return WAITING_AMOUNT

async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text("❌ Invalid amount! Please enter a valid number:")
            return WAITING_AMOUNT
            
        context.user_data['deposit_amount'] = amount
        method = context.user_data.get('deposit_method', 'Bkash')
        number = BKASH_NUMBER if method == "Bkash" else NAGAD_NUMBER if method == "Nagad" else BINANCE_ID
        
        text = (
            f"📥 **DEPOSIT DETAILS**\n\n"
            f"• **Method:** {method}\n"
            f"• **Amount:** {amount} BDT\n"
            f"• **Send To:** `{number}`\n\n"
            f"After sending payment, click **Payment Done** button below:"
        )
        keyboard = [[InlineKeyboardButton("✅ Payment Done", callback_data="payment_done")]]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return WAITING_TRXID
        
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number for amount:")
        return WAITING_AMOUNT

async def payment_done_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "⚙️ **Enter Transaction ID (TrxID):**\n\n"
        "Please send your payment TrxID / TxID below:",
        parse_mode="Markdown"
    )
    return WAITING_TRXID

async def trxid_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trx_id = update.message.text.strip()
    user = update.effective_user
    method = context.user_data.get('deposit_method', 'N/A')
    amount = context.user_data.get('deposit_amount', 0.0)
    
    # User Response
    user_confirm_text = (
        "⏳ **Deposit Request Submitted!**\n\n"
        "Your request has been submitted to Admin.\n"
        "Please wait 2-3 minutes for verification."
    )
    await update.message.reply_text(user_confirm_text, parse_mode="Markdown", reply_markup=reply_markup)
    
    # Notify Admin
    admin_notify_text = (
        f"📥 **NEW DEPOSIT REQUEST**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **User:** {user.full_name} (`{user.id}`)\n"
        f"💳 **Method:** {method}\n"
        f"💰 **Amount:** `{amount} BDT`\n"
        f"🔑 **TrxID:** `{trx_id}`\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    admin_keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"dep_app_{user.id}_{amount}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"dep_rej_{user.id}_{amount}")
        ]
    ]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_notify_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(admin_keyboard)
    )
    
    return ConversationHandler.END

async def deposit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Deposit cancelled.", reply_markup=reply_markup)
    return ConversationHandler.END

# --- ADMIN DEPOSIT APPROVAL HANDLER ---
async def admin_deposit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    action = data[1]     
    target_id = int(data[2])
    amount = float(data[3])
    
    if action == "app":
        new_bal = update_user_balance(target_id, amount)
        await query.edit_message_text(
            f"{query.message.text}\n\n✅ **STATUS:** APPROVED (+{amount} BDT)",
            parse_mode="Markdown"
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"🎉 **Deposit Approved!**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💰 **Added:** `{amount} BDT`\n"
                    f"💳 **Current Balance:** `{new_bal} BDT`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Thank you for using our service!"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass
            
    elif action == "rej":
        await query.edit_message_text(
            f"{query.message.text}\n\n❌ **STATUS:** REJECTED",
            parse_mode="Markdown"
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"❌ **Deposit Rejected!**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Your `{amount} BDT` deposit request was rejected.\n"
                    f"Please try again with valid TrxID or contact support."
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

# --- GENERAL BUTTON HANDLERS ---
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text in ["💳 DEPOSIT", "DEPOSIT", "Deposit"]:
        await deposit_start(update, context)
    elif text in ["💰 BALANCE", "BALANCE", "Balance"]:
        bal = get_user_balance(user_id)
        await update.message.reply_text(f"📊 **ACCOUNT BALANCE**\n\n🆔 User ID: `{user_id}`\n💰 Balance: `{bal} BDT`", parse_mode="Markdown")
    elif text in ["🛡️ BUY VPN", "BUY VPN"]:
        await update.message.reply_text("🛡️ VPN store coming soon!")
    elif text in ["🌐 BUY PROXY", "BUY PROXY"]:
        await update.message.reply_text("🌐 Proxy store coming soon!")
    elif text in ["🔄 P2P(USDT BUY & SELL)", "P2P(USDT BUY & SELL)"]:
        await update.message.reply_text("🔄 P2P USDT Buy & Sell service coming soon!")

def main():
    # Start Dummy Web Server Thread
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    deposit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(method_selected, pattern="^method_"),
            MessageHandler(filters.Regex("^(💳 DEPOSIT|DEPOSIT|Deposit)$"), deposit_start)
        ],
        states={
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
            WAITING_TRXID: [
                CallbackQueryHandler(payment_done_clicked, pattern="^payment_done$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, trxid_received)
            ]
        },
        fallbacks=[CommandHandler("cancel", deposit_cancel)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("addbal", addbal_cmd))
    app.add_handler(deposit_conv)
    app.add_handler(CallbackQueryHandler(admin_deposit_callback, pattern="^dep_(app|rej)_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
