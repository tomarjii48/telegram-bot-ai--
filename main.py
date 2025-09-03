"""
All-in-One AI Bot (Telegram + Website)
Stable for Railway deploy
Owner: Aditya Singh
"""

import os
import io
import json
import time
import logging
import asyncio
from pathlib import Path
from urllib.parse import quote_plus

import requests
import wikipedia
from gtts import gTTS
from fpdf import FPDF

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from flask import Flask, request, send_from_directory, jsonify

# Logging
logging.basicConfig(level=logging.INFO)

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
RAILWAY_BASE_URL = os.getenv("RAILWAY_BASE_URL", "")

if not TELEGRAM_TOKEN or not OPENROUTER_API_KEY:
    raise Exception("Set TELEGRAM_TOKEN and OPENROUTER_API_KEY in environment variables.")

# Paths
DATA_DIR = Path("data")
UPLOADS_DIR = DATA_DIR / "uploads"
NOTES_FILE = DATA_DIR / "notes.json"
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
if not NOTES_FILE.exists():
    NOTES_FILE.write_text(json.dumps({}))

# Bot & Flask
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
app = Flask(__name__, static_folder="static")

# Helpers
def load_notes():
    try:
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except:
        return {}

def save_notes(d):
    NOTES_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def make_public_file_url(filename, host_url=None):
    base = RAILWAY_BASE_URL.rstrip("/") if RAILWAY_BASE_URL else (host_url.rstrip("/") if host_url else "")
    if not base:
        return f"/files/{filename}"
    return f"{base}/files/{quote_plus(filename)}"

def call_openrouter_ai_sync(prompt):
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {"model":"openai/gpt-3.5-turbo","messages":[{"role":"user","content":prompt}],"max_tokens":800}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.exception("OpenRouter error")
        return f"⚠️ AI error: {str(e)}"

async def call_openrouter_ai(prompt):
    return await asyncio.get_event_loop().run_in_executor(None, call_openrouter_ai_sync, prompt)

# Utilities
def generate_image_url(prompt):
    return f"https://image.pollinations.ai/prompt/{quote_plus(prompt)}"

def generate_meme_url(text):
    safe = text.replace(" ", "_")
    return f"https://api.memegen.link/images/custom/_/{safe}.png?background=https://i.imgur.com/8KcYpGf.png"

def text_to_speech_file(text, lang="en"):
    try:
        tts = gTTS(text=text, lang=lang)
        fname = f"{int(time.time())}_tts.mp3"
        path = UPLOADS_DIR / fname
        tts.save(str(path))
        return str(path)
    except:
        logging.exception("TTS failed")
        return None

def make_pdf_from_text(text, filename=None):
    try:
        if not filename:
            filename = f"{int(time.time())}_doc.pdf"
        path = DATA_DIR / filename
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_font("Arial", size=12)
        for line in text.split("\n"):
            pdf.multi_cell(0, 6, line)
        pdf.output(str(path))
        return str(path)
    except Exception as e:
        logging.exception("PDF creation failed")
        return None

# Telegram Handlers
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply("👋 Hello! I'm Aditya Singh's All-in-One AI Bot.\nUse commands or chat directly!")

@dp.message_handler(commands=["ai"])
async def cmd_ai(message: types.Message):
    query = message.get_args()
    if not query:
        await message.reply("Usage: /ai <your question>")
        return
    await message.reply("⏳ Thinking...")
    res = await call_openrouter_ai(query)
    await message.reply(res)

@dp.message_handler(commands=["image"])
async def cmd_image(message: types.Message):
    prompt = message.get_args()
    if not prompt:
        await message.reply("Usage: /image <prompt>")
        return
    url = generate_image_url(prompt)
    await message.reply_photo(url, caption=f"Image for: {prompt}")

@dp.message_handler(commands=["meme"])
async def cmd_meme(message: types.Message):
    text = message.get_args()
    if not text:
        await message.reply("Usage: /meme <text>")
        return
    url = generate_meme_url(text)
    await message.reply_photo(url, caption=f"Meme: {text}")

@dp.message_handler(commands=["tts"])
async def cmd_tts(message: types.Message):
    text = message.get_args()
    if not text:
        await message.reply("Usage: /tts <text>")
        return
    path = text_to_speech_file(text)
    if path:
        await message.reply_audio(open(path, "rb"))
    else:
        await message.reply("⚠️ TTS failed.")

@dp.message_handler(commands=["pdf"])
async def cmd_pdf(message: types.Message):
    text = message.get_args()
    if not text:
        await message.reply("Usage: /pdf <text>")
        return
    path = make_pdf_from_text(text)
    if path:
        await message.reply_document(open(path, "rb"))
    else:
        await message.reply("⚠️ PDF creation failed.")

@dp.message_handler(commands=["note"])
async def cmd_note(message: types.Message):
    args = message.get_args()
    notes = load_notes()
    if not args:
        if not notes:
            await message.reply("No notes yet.")
        else:
            msg = "\n".join([f"{k}: {v}" for k, v in notes.items()])
            await message.reply(msg)
        return
    key, _, val = args.partition(" ")
    if key and val:
        notes[key] = val
        save_notes(notes)
        await message.reply(f"Note saved: {key}")
    else:
        await message.reply("Usage: /note <title> <content>")

# Photo upload via Telegram
@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    data = await bot.download_file(file.file_path)
    fname = f"{int(time.time())}_tg.jpg"
    path = UPLOADS_DIR / fname
    with open(path, "wb") as f:
        f.write(data.read())
    await message.reply(f"Image saved. Ask about it: img:{fname} <your question>")

# Text message handler
@dp.message_handler()
async def handle_text(message: types.Message):
    text = message.text.strip()
    if text.startswith("/"):
        return
    await message.reply("⏳ Thinking...")
    resp = await call_openrouter_ai(text)
    await message.reply(resp)

# Set commands
async def set_commands():
    cmds = [types.BotCommand("start","Start bot"), types.BotCommand("ai","Chat AI"),
            types.BotCommand("image","Generate image"), types.BotCommand("meme","Make meme"),
            types.BotCommand("tts","Text-to-Speech"), types.BotCommand("pdf","Text → PDF"),
            types.BotCommand("note","Add/View notes")]
    await bot.set_my_commands(cmds)

# Flask Web Chat
CHAT_HTML = """
<!doctype html>
<html>
<body>
<h2>Aditya Singh AI Bot</h2>
<div id="chat"></div>
<input id="msg"><button onclick="send()">Send</button>
<input type="file" id="fileinput"><button onclick="uploadFile()">Upload</button>
<script>
async function send(){
 let t=document.getElementById('msg').value;
 document.getElementById('msg').value='';
 let resp=await fetch('/webchat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
 let j=await resp.json();
 document.getElementById('chat').innerHTML+="<div><b>You:</b> "+t+"</div><div><b>Bot:</b> "+j.reply+"</div>";
}
async function uploadFile(){
 let fi=document.getElementById('fileinput');
 if(!fi.files.length)return;
 let fd=new FormData(); fd.append('file', fi.files[0]);
 let res=await fetch('/upload',{method:'POST',body:fd});
 let j=await res.json();
 document.getElementById('chat').innerHTML+="<div>Uploaded: "+j.filename+"</div>";
}
</script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return CHAT_HTML

@app.route("/webchat", methods=["POST"])
def webchat():
    data = request.get_json() or {}
    text = data.get("text","").strip()
    reply = call_openrouter_ai_sync(text) if text else "Send text."
    return jsonify({"reply": reply})

@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"ok":False,"error":"No file"})
    f = request.files['file']
    fname = f"{int(time.time())}_{f.filename}"
    path = UPLOADS_DIR / fname
    f.save(path)
    host = request.host_url.rstrip("/")
    return jsonify({"ok":True,"filename": fname, "url": make_public_file_url(fname, host_url=host)})

@app.route("/files/<path:filename>")
def serve_file(filename):
    return send_from_directory(str(UPLOADS_DIR), filename, as_attachment=False)

# Start Flask & Bot
def start_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__=="__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_commands())
    import threading
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    executor.start_polling(dp, skip_updates=True)
