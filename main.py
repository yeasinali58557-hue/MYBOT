import logging
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Logging setup
logging.basicConfig(level=logging.INFO)

# Configs
TOKEN = "8733585059:AAHw7igMJkclCmEtOU1y73T2C2n0hILhWx0"
ADMIN_ID = 7753794493  # Replace with your actual Admin ID
BINANCE_PAY_ID = "7753794493"  # Change to your actual Binance Pay ID / Number
DB_FILE = "bot_data.db"

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

def add_user_balance(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_bal = get_user_balance(user_id)
    new_bal = current_bal + amount
    cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_bal, user_id))
    conn.commit()
    conn.close()
    return new_bal

# --- BOT KEYBOARDS ---
KEYBOARD = [
    ["🌐 BUY PROXY", "🛡 BUY VPN"],
    ["💱 P2P (USDT BUY & SELL)"],
    ["💰 DEPOSIT", "📜 HISTORY"]
]
reply_markup = ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True)

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_user_balance(user_id)
    
    welcome_text = (
        f"Welcome to the Store!\n\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"💰 **Balance:** {balance} BDT\n\n"
        f"Please select an option below:"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to access the admin panel.")
        return
    
    admin_text = (
        "👑 **ADMIN PANEL**\n\n"
        "To add balance to a user, use command:\n"
        "`/addbal USER_ID AMOUNT`\n\n"
        "Example: `/addbal 123456789 500`"
    )
    await update.message.reply_text(admin_text, parse_mode="Markdown")

async def addbal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
        new_bal = add_user_balance(user_id, amount)
        
        await update.message.reply_text(f"✅ Successfully added {amount} BDT to User `{user_id}`.\nNew Balance: {new_bal} BDT", parse_mode="Markdown")
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 **Deposit Successful!**\n\n`{amount}` BDT has been added to your account.\nYour New Balance: `{new_bal}` BDT",
                parse_mode="Markdown"
            )
        except Exception:
            pass
            
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Invalid Format!\nUse: `/addbal USER_ID AMOUNT`", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "💰 DEPOSIT":
        deposit_keyboard = [
            [InlineKeyboardButton("🟡 Binance Pay", callback_data="dep_binance")],
            [InlineKeyboardButton("📱 bKash / Nagad", callback_data="dep_mfs")]
        ]
        await update.message.reply_text(
            "💳 **Select Payment Method:**", 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(deposit_keyboard)
        )
    elif text == "🌐 BUY PROXY":
        balance = get_user_balance(user_id)
        await update.message.reply_text(f"Proxy catalog coming soon!\nYour Current Balance: {balance} BDT")
    elif text == "🛡 BUY VPN":
        await update.message.reply_text("VPN catalog coming soon!")
    elif text == "💱 P2P (USDT BUY & SELL)":
        await update.message.reply_text("P2P trading desk coming soon!")
    elif text == "📜 HISTORY":
        balance = get_user_balance(user_id)
        await update.message.reply_text(f"📜 **Account Summary**\n\nBalance: {balance} BDT\nNo past transactions.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "dep_binance":
        binance_text = (
            "🟡 **Binance Deposit**\n\n"
            f"Send payment to Binance Pay ID:\n`{BINANCE_PAY_ID}`\n\n"
            "*(Tap on the number above to copy)*\n\n"
            "After sending, submit transaction proof to Admin."
        )
        back_keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_deposit")]]
        await query.edit_message_text(binance_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(back_keyboard))
        
    elif query.data == "back_deposit":
        deposit_keyboard = [
            [InlineKeyboardButton("🟡 Binance Pay", callback_data="dep_binance")],
            [InlineKeyboardButton("📱 bKash / Nagad", callback_data="dep_mfs")]
        ]
        await query.edit_message_text(
            "💳 **Select Payment Method:**", 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(deposit_keyboard)
        )

def main():
    init_db()  # Initialize Database Table
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("addbal", addbal_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running with SQLite Database...")
    app.run_polling()

if __name__ == "__main__":
    main()
