import logging
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    MessageHandler, ContextTypes, ConversationHandler, filters
)

# Logging Setup
logging.basicConfig(level=logging.INFO)

# Configs
TOKEN = "8733585059:AAHw7igMJkclCmEtOU1y73T2C2n0hILhWx0"
ADMIN_ID = 7753794493
DB_FILE = "bot_data.db"

# Payment Details
BKASH_NUMBER = "01610184434"
NAGAD_NUMBER = "01610184434"
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
    ["🛍️ Buy Now", "✉️ Mail Code"],
    ["🔐 2FA Code"],
    ["💰 Deposit", "📊 Dashboard"],
    ["🎧 Support"]
]
reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

# --- START & MENU HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_balance(user.id)
    
    welcome_msg = (
        f"👋 **Hello {user.first_name}!**\n"
        f"Welcome to **Quick Store**!\n\n"
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
        "• Add Balance: `/addbal USER_ID AMOUNT`\n\n"
        "Deposit requests will automatically arrive here for approval."
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
        [InlineKeyboardButton("💗 Bkash", callback_data="method_Bkash")],
        [InlineKeyboardButton("🧡 Nagad", callback_data="method_Nagad")],
        [InlineKeyboardButton("🟡 Binance", callback_data="method_Binance")]
    ]
    await update.message.reply_text(
        "💵 **Select Payment Method:**", 
        parse_mode="Markdown", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    method = query.data.split("_")[1]
    context.user_data['deposit_method'] = method
    
    await query.edit_message_text(
        f"💳 **Method Selected:** `{method}`\n\n"
        f"**কত টাকা ডিপোজিট করবেন তা লিখে পাঠান:**",
        parse_mode="Markdown"
    )
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
        instruction = f"এই নাম্বারে টাকা পাঠান: `{number}`" if method != "Binance" else f"Binance Pay ID: `{number}`"
        
        text = (
            f"📥 **Deposit Request**\n\n"
            f"• **Method:** {method}\n"
            f"• **Amount:** {amount} BDT\n\n"
            f"{instruction}\n\n"
            f"*(ট্যাপ করে নাম্বার/আইডি কপি করুন)*\n\n"
            f"পেমেন্ট সম্পন্ন হলে নিচের **Payment Done** বাটনে ক্লিক করুন:"
        )
        keyboard = [[InlineKeyboardButton("✅ Payment Done", callback_data="payment_done")]]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return WAITING_TRXID
        
    except ValueError:
        await update.message.reply_text("❌ Please send a valid number for amount:")
        return WAITING_AMOUNT

async def payment_done_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "⚙️ **Transaction ID (TrxID) দিন:**\n\n"
        "আপনার পেমেন্টের TrxID/TxID টি মেসেজে লিখে পাঠান:",
        parse_mode="Markdown"
    )
    return WAITING_TRXID

async def trxid_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trx_id = update.message.text.strip()
    user = update.effective_user
    method = context.user_data.get('deposit_method', 'N/A')
    amount = context.user_data.get('deposit_amount', 0.0)
    
    # 1. Reply to User
    user_confirm_text = (
        "⏳ **Deposit Request Submitted!**\n\n"
        "আপনার অনুরোধটি এডমিনের কাছে পাঠানো হয়েছে।\n"
        "অনুগ্রহ করে **২-৩ মিনিট** অপেক্ষা করুন, ভেরিফাই করে অ্যাপ্রুভ করে দেওয়া হবে।"
    )
    await update.message.reply_text(user_confirm_text, parse_mode="Markdown", reply_markup=reply_markup)
    
    # 2. Notify Admin with Buttons
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
    action = data[1]     # 'app' or 'rej'
    target_id = int(data[2])
    amount = float(data[3])
    
    if action == "app":
        new_bal = update_user_balance(target_id, amount)
        
        # Edit Admin Message
        await query.edit_message_text(
            f"{query.message.text}\n\n✅ **STATUS:** APPROVED (+{amount} BDT)",
            parse_mode="Markdown"
        )
        
        # Send User Notification
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"🎉 **Deposit Approved!**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💰 **Added:** `{amount} BDT`\n"
                    f"💳 **Current Balance:** `{new_bal} BDT`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"ধন্যবাদ আমাদের পরিষেবা ব্যবহার করার জন্য!"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass
            
    elif action == "rej":
        # Edit Admin Message
        await query.edit_message_text(
            f"{query.message.text}\n\n❌ **STATUS:** REJECTED",
            parse_mode="Markdown"
        )
        
        # Send User Notification
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"❌ **Deposit Rejected!**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"আপনার `{amount} BDT` ডিপোজিট রিকোয়েস্টটি বাতিল করা হয়েছে।\n"
                    f"সঠিক TrxID দিয়ে পুনরায় চেষ্টা করুন অথবা সাপোর্টে যোগাযোগ করুন।"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

# --- GENERAL BUTTON HANDLERS ---
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text in ["💰 Deposit", "Deposit"]:
        await deposit_start(update, context)
    elif text in ["📊 Dashboard", "Dashboard"]:
        bal = get_user_balance(user_id)
        await update.message.reply_text(f"📊 **Dashboard**\n\n🆔 User ID: `{user_id}`\n💰 Balance: `{bal} BDT`", parse_mode="Markdown")
    elif text in ["🛍️ Buy Now", "Buy Now"]:
        await update.message.reply_text("🛍️ Products catalog coming soon!")
    elif text in ["✉️ Mail Code", "Mail Code"]:
        await update.message.reply_text("✉️ Mail Code feature coming soon!")
    elif text in ["🔐 2FA Code", "2FA Code"]:
        await update.message.reply_text("🔐 2FA Code feature coming soon!")
    elif text in ["🎧 Support", "Support"]:
        await update.message.reply_text("🎧 Support Contact: @admin")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Deposit Conversation Handler
    deposit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(method_selected, pattern="^method_"),
            MessageHandler(filters.Regex("^(💰 Deposit|Deposit)$"), deposit_start)
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
