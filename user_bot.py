import asyncio
import re
import signal
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient, events
from telethon.tl.types import Message
import uvicorn
import os

# ===== CONFIGURATION =====
# Get credentials from environment variables (more secure)
API_ID = int(os.getenv("API_ID", "22557209"))
API_HASH = os.getenv("API_HASH", "2c2cc680074bcfa5e77f2773ff6e565b")
PHONE = os.getenv("PHONE", "+919956915970")
SESSION_NAME = os.getenv("SESSION_NAME", "stream_session")

# Dynamic base URL detection
def get_base_url():
    """
    Get the base URL dynamically from environment variables.
    Koyeb sets KOYEB_PUBLIC_DOMAIN or you can set BASE_URL manually.
    """
    # Check for manually set BASE_URL first
    if os.getenv("BASE_URL"):
        return os.getenv("BASE_URL").rstrip('/')
    
    # Check for Koyeb's public domain
    if os.getenv("KOYEB_PUBLIC_DOMAIN"):
        return f"https://{os.getenv('KOYEB_PUBLIC_DOMAIN')}"
    
    # Check for Koyeb app name (format: https://APP_NAME-ORG_NAME.koyeb.app)
    koyeb_app = os.getenv("KOYEB_APP_NAME")
    koyeb_org = os.getenv("KOYEB_ORG_NAME")
    if koyeb_app and koyeb_org:
        return f"https://{koyeb_app}-{koyeb_org}.koyeb.app"
    
    # Fallback to local
    port = int(os.getenv("PORT", "8000"))
    return f"http://localhost:{port}"

BASE_URL = get_base_url()
PORT = int(os.getenv("PORT", "8000"))

# ===== INITIALIZE =====
app = FastAPI(title="Telegram File Streamer")
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Enable CORS for HTML player
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== SHUTDOWN HANDLER =====
shutdown_flag = asyncio.Event()

def signal_handler(signum, frame):
    print("\n\n🛑 Shutdown signal received. Cleaning up...")
    shutdown_flag.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ===== HELPER FUNCTIONS =====
async def get_message(chat_id: int, message_id: int) -> Message:
    try:
        message = await client.get_messages(chat_id, ids=message_id)
        if not message or not message.media:
            raise HTTPException(status_code=404, detail="Message or media not found")
        return message
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching message: {str(e)}")

def parse_range_header(range_header: str, file_size: int) -> tuple:
    if not range_header:
        return 0, file_size - 1
    match = re.search(r'bytes=(\d+)-(\d*)', range_header)
    if not match:
        return 0, file_size - 1
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    return start, end

# ===== API ENDPOINTS =====
@app.get("/")
async def root():
    return {
        "status": "Telegram Stream Server Running",
        "bot": "Connected" if client.is_connected() else "Disconnected",
        "server_url": BASE_URL,
        "environment": os.getenv("KOYEB_DEPLOYMENT_ID", "local")
    }

@app.get("/info/{chat_id}/{message_id}")
async def get_file_info(chat_id: int, message_id: int):
    message = await get_message(chat_id, message_id)
    media = message.media
    if hasattr(media, 'document'):
        doc = media.document
        filename = next((attr.file_name for attr in doc.attributes if hasattr(attr, 'file_name')), f"file_{message_id}")
        mime_type = doc.mime_type
        size = doc.size
    elif hasattr(media, 'photo'):
        filename = f"photo_{message_id}.jpg"
        mime_type = "image/jpeg"
        size = max(media.photo.sizes, key=lambda x: getattr(x, 'size', 0))
    else:
        filename = f"media_{message_id}"
        mime_type = "application/octet-stream"
        size = 0
    return JSONResponse({
        "chat_id": chat_id,
        "message_id": message_id,
        "filename": filename,
        "mime_type": mime_type,
        "size": size,
        "size_mb": round(size / (1024 * 1024), 2)
    })

@app.get("/stream/{chat_id}/{message_id}")
async def stream_file(chat_id: int, message_id: int, request: Request):
    message = await get_message(chat_id, message_id)
    media = message.media
    if hasattr(media, 'document'):
        doc = media.document
        file_size = doc.size
        mime_type = doc.mime_type
        filename = next((attr.file_name for attr in doc.attributes if hasattr(attr, 'file_name')), f"file_{message_id}")
    elif hasattr(media, 'photo'):
        file_size = max(media.photo.sizes, key=lambda x: getattr(x, 'size', 0))
        mime_type = "image/jpeg"
        filename = f"photo_{message_id}.jpg"
    else:
        raise HTTPException(status_code=400, detail="Unsupported media type")

    range_header = request.headers.get("range")
    start, end = parse_range_header(range_header, file_size)
    content_length = end - start + 1

    async def stream_generator():
        chunk_size = 512 * 1024
        offset = start
        remaining = content_length
        try:
            async for chunk in client.iter_download(
                message.media, offset=offset, limit=content_length, chunk_size=chunk_size
            ):
                if not chunk:
                    break
                yield chunk
                remaining -= len(chunk)
                if remaining <= 0:
                    break
        except Exception as e:
            print(f"Error streaming: {e}")
            raise

    headers = {
        "Content-Type": mime_type,
        "Content-Disposition": f'inline; filename="{filename}"',
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
    }
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        status_code = 206
    else:
        status_code = 200

    return StreamingResponse(stream_generator(), status_code=status_code, headers=headers, media_type=mime_type)

@app.get("/player")
async def serve_player(request: Request):
    player_path = os.path.join(os.path.dirname(__file__), "player2.html")
    if not os.path.exists(player_path):
        raise HTTPException(status_code=404, detail="Player HTML file not found.")
    with open(player_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# ===== TELEGRAM EVENT HANDLERS =====
@client.on(events.NewMessage(pattern=r'^/stream$'))
async def handle_stream_command(event):
    if not event.is_reply:
        await event.reply("❌ Please reply to a video or document with /stream")
        return
    replied_msg = await event.get_reply_message()
    if not replied_msg.media:
        await event.reply("❌ The message you replied to doesn't contain any media")
        return
    if not (hasattr(replied_msg.media, 'document') or hasattr(replied_msg.media, 'photo')):
        await event.reply("❌ Only documents, videos, and photos are supported")
        return

    chat_id = event.chat_id
    message_id = replied_msg.id
    stream_url = f"{BASE_URL}/stream/{chat_id}/{message_id}"
    info_url = f"{BASE_URL}/info/{chat_id}/{message_id}"
    player_url = f"{BASE_URL}/player?stream={stream_url}"

    try:
        if hasattr(replied_msg.media, 'document'):
            doc = replied_msg.media.document
            filename = next((attr.file_name for attr in doc.attributes if hasattr(attr, 'file_name')), "Unknown")
            size_mb = round(doc.size / (1024 * 1024), 2)
            file_info = f"📁 **File:** `{filename}`\n📊 **Size:** `{size_mb} MB`"
        else:
            file_info = "📷 **Type:** Photo"
    except:
        file_info = "📄 **Type:** Media file"

    response = f"""✅ **Stream Link Generated!**

{file_info}

🎬 **Click or Copy URLs below:**

▶️ **Open in Player:**
`{player_url}`

🔗 **Direct Stream:**
`{stream_url}`

ℹ️ **File Info:**
`{info_url}`
"""
    await event.reply(response, link_preview=False)

# ===== STARTUP =====
async def start_bot():
    print("🚀 Starting Telegram client...")
    await client.start(phone=PHONE)
    print("✅ Telegram client connected!")
    print(f"📱 Logged in as: {await client.get_me()}")
    print(f"🌐 Server URL: {BASE_URL}")
    print("\n💡 Send /stream as a reply to any video/document in Telegram to get stream link!")

@app.on_event("startup")
async def startup_handler():
    asyncio.create_task(start_bot())

@app.on_event("shutdown")
async def shutdown_handler():
    print("🧹 Disconnecting Telegram client...")
    await client.disconnect()
    print("✅ Cleanup complete!")

# ===== RUN SERVER =====
async def run_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    print("=" * 60)
    print("🎬 TELEGRAM FILE STREAMER SERVER")
    print("=" * 60)
    print(f"\n🌐 Server URL: {BASE_URL}")
    print(f"🔌 Port: {PORT}")
    print("\n📋 Instructions:")
    print("1. Reply to any video/document in Telegram with: /stream")
    print("2. Click the inline buttons to open player or get stream links")
    print("\n💡 Press Ctrl+C to stop the server gracefully")
    print("=" * 60 + "\n")
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    finally:
        print("🛑 Application closed.")