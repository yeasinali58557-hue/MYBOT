import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Logging setup
logging.basicConfig(level=logging.INFO)

# Configs
TOKEN = "8733585059:AAHw7igMJkclCmEtOU1y73T2C2n0hILhWx0"
ADMIN_ID = 7753794493  # Replace with your actual Admin ID if different
BINANCE_PAY_ID = "7753794493"  # Change to your actual Binance Pay ID / Number

# Reply Keyboard (Bottom Keyboard)
KEYBOARD = [
    ["🌐 BUY PROXY", "🛡 BUY VPN"],
    ["💱 P2P (USDT BUY & SELL)"],
    ["💰 DEPOSIT", "📜 HISTORY"]
]
reply_markup = ReplyKeyboardMarkup(KEYBOARD, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    welcome_text = (
        f"Welcome to the Store!\n\n"
        f"User ID: `{user_id}`\n"
        f"Balance: 0.0 BDT\n\n"
        f"Please select an option below:"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to access the admin panel.")
        return
    
    admin_text = (
        "👑 **ADMIN PANEL**\n\n"
        "Welcome Admin! Select an action:"
    )
    keyboard = [
        [InlineKeyboardButton("➕ Add Balance", callback_data="admin_add_bal")],
        [InlineKeyboardButton("📊 User Stats", callback_data="admin_stats")]
    ]
    await update.message.reply_text(admin_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
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
        await update.message.reply_text("Proxy catalog coming soon!")
    elif text == "🛡 BUY VPN":
        await update.message.reply_text("VPN catalog coming soon!")
    elif text == "💱 P2P (USDT BUY & SELL)":
        await update.message.reply_text("P2P trading desk coming soon!")
    elif text == "📜 HISTORY":
        await update.message.reply_text("No transaction history found.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "dep_binance":
        # Delete/Edit old message and show new message with copyable ID
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
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
