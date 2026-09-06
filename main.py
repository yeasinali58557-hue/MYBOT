import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler, ContextTypes
)

BOT_TOKEN = "8733585059:AAHw7igMJkclCmEtOU1y73T2C2n0hILhWx0"
ADMIN_ID = 7753794493

METHOD, AMOUNT, CONFIRM, TRXID = range(4)

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()

def get_or_create_user(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute('INSERT INTO users (user_id, balance) VALUES (?, ?)', (user_id, 0.0))
        conn.commit()
        balance = 0.0
    else:
        balance = row[0]
    conn.close()
    return balance

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_or_create_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🌐 BUY PROXY", callback_data='buy_proxy'), InlineKeyboardButton("🛡️ BUY VPN", callback_data='buy_vpn')],
        [InlineKeyboardButton("💱 P2P (USDT BUY & SELL)", callback_data='p2p')],
        [InlineKeyboardButton("💰 DEPOSIT", callback_data='deposit'), InlineKeyboardButton("📜 HISTORY", callback_data='history')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = f"Welcome to the Store!\n\nUser ID: {user_id}\nBalance: {balance} BDT\n\nPlease select an option below:"
    await update.message.reply_text(msg, reply_markup=reply_markup)

async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💖 Bkash", callback_data='Bkash'), InlineKeyboardButton("🚀 Rocket", callback_data='Rocket')],
        [InlineKeyboardButton("🔶 Binance", callback_data='Binance')],
        [InlineKeyboardButton("❌ Close", callback_data='close')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Select Payment Method:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Select Payment Method:", reply_markup=reply_markup)
        
    return METHOD

async def method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'close':
        await query.message.delete()
        return ConversationHandler.END
        
    context.user_data['method'] = query.data
    number = "01967922602"
    context.user_data['number'] = number
    
    msg = (
        f"📊 Method: {query.data}\n"
        f"🏷️ Send To: {number}\n\n"
        f"💲 Enter Amount (BDT):"
    )
    await query.message.reply_text(msg)
    return AMOUNT

async def amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text
    context.user_data['amount'] = amount
    method = context.user_data['method']
    number = context.user_data['number']
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm", callback_data='confirm_deposit'), 
         InlineKeyboardButton("🛑 Cancel", callback_data='cancel_deposit')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    summary = (
        f"🧾 Recharge Summary\n\n"
        f"Method: {method}\n"
        f"🧔 Send To: {number}\n"
        f"Amount: {amount}.0 ৳\n"
        f"💵 Converted: {amount}.0 ৳\n\n"
        f"Do you want to confirm this request?"
    )
    await update.message.reply_text(summary, reply_markup=reply_markup)
    return CONFIRM

async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel_deposit':
        await query.message.reply_text("Deposit Request Canceled.")
        return ConversationHandler.END
        
    msg = "✉️ Please enter your Transaction ID (TrxID): 🌠"
    await query.message.reply_text(msg)
    return TRXID

async def trxid_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    trx_id = update.message.text
    amount = context.user_data.get('amount')
    method = context.user_data.get('method')
    
    msg = (
        "⏳ Checking your payment...\n"
        "Please wait up to 1 minute. 🎁"
    )
    await update.message.reply_text(msg)
    
    admin_msg = (
        f"🔔 New Deposit Request!\n\n"
        f"User ID: {user_id}\n"
        f"Method: {method}\n"
        f"Amount: {amount} BDT\n"
        f"TrxID: {trx_id}"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
    except Exception as e:
        print(f"Failed to send alert to admin: {e}")
        
    return ConversationHandler.END

if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    deposit_handler = ConversationHandler(
        entry_points=[
            CommandHandler('deposit', deposit_start),
            CallbackQueryHandler(deposit_start, pattern='^deposit$')
        ],
        states={
            METHOD: [CallbackQueryHandler(method_selected)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_entered)],
            CONFIRM: [CallbackQueryHandler(confirm_deposit)],
            TRXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, trxid_entered)],
        },
        fallbacks=[]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(deposit_handler)
    
    print("Bot is running...")
    app.run_polling()
