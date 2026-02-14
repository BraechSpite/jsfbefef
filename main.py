import asyncio
import subprocess
import signal
import sys
import os
import psutil
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== CONFIGURATION =====
BOT_TOKEN = "8252942642:AAEdq-4g81QlGK4vq5f-bFG09G-YzKPSf-U"
OWNER_ID = 7324136492  # Your Telegram User ID
USERBOT_SCRIPT = "user_bot.py"  # Your userbot script filename

# ===== GLOBAL VARIABLES =====
userbot_process = None
userbot_logs = []
MAX_LOG_LINES = 50

# ===== HELPER FUNCTIONS =====
def is_owner(user_id: int) -> bool:
    """Check if user is the owner"""
    return user_id == OWNER_ID

def is_userbot_running() -> bool:
    """Check if userbot process is running"""
    global userbot_process
    if userbot_process is None:
        return False
    return userbot_process.poll() is None

def get_process_info() -> dict:
    """Get userbot process information"""
    if not is_userbot_running():
        return None
    
    try:
        process = psutil.Process(userbot_process.pid)
        return {
            "pid": process.pid,
            "cpu": f"{process.cpu_percent(interval=0.1):.1f}%",
            "memory": f"{process.memory_info().rss / 1024 / 1024:.1f} MB",
            "status": process.status(),
            "uptime": f"{(psutil.time.time() - process.create_time()) / 60:.1f} min"
        }
    except:
        return None

async def start_userbot() -> tuple[bool, str]:
    """Start the userbot script"""
    global userbot_process, userbot_logs
    
    # Check if already running
    if is_userbot_running():
        return False, "❌ Userbot is already running!"
    
    # Check if script exists
    if not os.path.exists(USERBOT_SCRIPT):
        return False, f"❌ Script '{USERBOT_SCRIPT}' not found in current directory!"
    
    # Start the process
    try:
        userbot_logs = []
        userbot_process = subprocess.Popen(
            [sys.executable, USERBOT_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        
        # Wait a moment to check if it started successfully
        await asyncio.sleep(2)
        
        if not is_userbot_running():
            return False, "❌ Userbot failed to start! Check the script for errors."
        
        return True, f"✅ Userbot started successfully!\n📍 PID: {userbot_process.pid}"
    
    except Exception as e:
        return False, f"❌ Failed to start userbot: {str(e)}"

async def stop_userbot() -> tuple[bool, str]:
    """Stop the userbot script gracefully"""
    global userbot_process
    
    if not is_userbot_running():
        return False, "❌ Userbot is not running!"
    
    try:
        pid = userbot_process.pid
        
        # Send SIGTERM for graceful shutdown (works with your signal handlers)
        if sys.platform == "win32":
            # Windows: send Ctrl+C event
            userbot_process.send_signal(signal.CTRL_C_EVENT)
        else:
            # Unix: send SIGTERM
            userbot_process.send_signal(signal.SIGTERM)
        
        # Wait for graceful shutdown (max 10 seconds)
        try:
            userbot_process.wait(timeout=10)
            userbot_process = None
            return True, f"✅ Userbot stopped gracefully!\n📍 PID: {pid}"
        except subprocess.TimeoutExpired:
            # Force kill if graceful shutdown fails
            userbot_process.kill()
            userbot_process.wait()
            userbot_process = None
            return True, f"⚠️ Userbot force-killed (didn't respond to graceful shutdown)\n📍 PID: {pid}"
    
    except Exception as e:
        return False, f"❌ Failed to stop userbot: {str(e)}"

# ===== COMMAND HANDLERS =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized. This bot is private.")
        return
    
    welcome_msg = f"""👋 **Welcome to Userbot Control Panel!**

🤖 **Your User ID:** `{user_id}`
✅ **Access:** Authorized

**Available Commands:**
/on - Start the userbot
/off - Stop the userbot
/status - Check userbot status
/restart - Restart the userbot
/logs - View recent logs
/info - Show process information

🔒 **Security:** Only you can control this bot.
"""
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /on command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return
    
    status_msg = await update.message.reply_text("🔄 Starting userbot...")
    success, message = await start_userbot()
    
    await status_msg.edit_text(message, parse_mode="Markdown")
    
    # Wait a bit and show ngrok URL if available
    if success:
        await asyncio.sleep(3)
        info = get_process_info()
        if info:
            await update.message.reply_text(
                f"📊 **Userbot Running**\n"
                f"🆔 PID: `{info['pid']}`\n"
                f"⏱ Uptime: {info['uptime']}\n\n"
                f"💡 Check your Telegram for ngrok URL!",
                parse_mode="Markdown"
            )

async def off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /off command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return
    
    status_msg = await update.message.reply_text("🔄 Stopping userbot...")
    success, message = await stop_userbot()
    
    await status_msg.edit_text(message, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return
    
    if not is_userbot_running():
        await update.message.reply_text(
            "🔴 **Userbot Status: OFFLINE**\n\n"
            "Use /on to start the userbot.",
            parse_mode="Markdown"
        )
        return
    
    info = get_process_info()
    if info:
        status_text = f"""🟢 **Userbot Status: RUNNING**

🆔 **PID:** `{info['pid']}`
💻 **CPU:** {info['cpu']}
🧠 **Memory:** {info['memory']}
📊 **Status:** {info['status']}
⏱ **Uptime:** {info['uptime']}

Use /off to stop the userbot.
"""
    else:
        status_text = "🟡 **Userbot Status: UNKNOWN**\n\nProcess exists but cannot read info."
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restart command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return
    
    status_msg = await update.message.reply_text("🔄 Restarting userbot...")
    
    # Stop if running
    if is_userbot_running():
        success, message = await stop_userbot()
        if not success:
            await status_msg.edit_text(f"❌ Failed to stop: {message}")
            return
        await asyncio.sleep(2)
    
    # Start again
    success, message = await start_userbot()
    await status_msg.edit_text(f"🔄 **Restart Complete**\n\n{message}", parse_mode="Markdown")

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logs command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return
    
    if not is_userbot_running():
        await update.message.reply_text("❌ Userbot is not running. No logs available.")
        return
    
    # Read recent output from process
    try:
        # Note: This is a simple implementation. For production, consider using a proper logging system
        await update.message.reply_text(
            "📋 **Recent Logs:**\n\n"
            "Logs are printed to console where user_bot.py is running.\n"
            "Check the terminal/console for detailed logs.\n\n"
            f"🆔 Process PID: `{userbot_process.pid}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error reading logs: {str(e)}")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /info command"""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return
    
    script_exists = "✅" if os.path.exists(USERBOT_SCRIPT) else "❌"
    script_path = os.path.abspath(USERBOT_SCRIPT)
    
    info_text = f"""ℹ️ **Control Bot Information**

👤 **Owner ID:** `{OWNER_ID}`
📄 **Userbot Script:** `{USERBOT_SCRIPT}`
📁 **Script Path:** `{script_path}`
{script_exists} **Script Found**

🤖 **Platform:** {sys.platform}
🐍 **Python:** {sys.version.split()[0]}

**Working Directory:**
`{os.getcwd()}`
"""
    await update.message.reply_text(info_text, parse_mode="Markdown")

# ===== CLEANUP ON EXIT =====
async def cleanup():
    """Cleanup before bot exits"""
    global userbot_process
    
    if is_userbot_running():
        print("\n🧹 Cleaning up: Stopping userbot...")
        await stop_userbot()
        print("✅ Userbot stopped.")

# ===== MAIN =====
def main():
    """Start the control bot"""
    print("=" * 60)
    print("🤖 TELEGRAM USERBOT CONTROL BOT")
    print("=" * 60)
    print(f"\n🔐 Owner ID: {OWNER_ID}")
    print(f"📄 Userbot Script: {USERBOT_SCRIPT}")
    print(f"📁 Working Directory: {os.getcwd()}")
    
    # Check if userbot script exists
    if not os.path.exists(USERBOT_SCRIPT):
        print(f"\n⚠️  WARNING: '{USERBOT_SCRIPT}' not found in current directory!")
        print(f"   Make sure the file is in: {os.getcwd()}")
    else:
        print(f"\n✅ Userbot script found!")
    
    print("\n🚀 Starting control bot...")
    print("💡 Send /start to your bot to see available commands")
    print("\n" + "=" * 60 + "\n")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("on", on_command))
    application.add_handler(CommandHandler("off", off_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("info", info_command))
    
    # Run the bot
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down control bot...")
        # Cleanup will be handled by the cleanup function
        asyncio.run(cleanup())
        print("👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        asyncio.run(cleanup())

if __name__ == "__main__":
    main()