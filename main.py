"""
All-in-One AI Bot (Telegram + Website)
Features:
- Direct AI chat (OpenRouter)
- Commands: /ai, /wiki, /weather, /image, /meme, /speak, /joke, /notes, /pdf
- Image upload (Telegram + Website) + ask question about uploaded image
- Website chat UI (Flask) with file upload and same AI backend
- Notes (per chat) stored in JSON
- PDF generator (text -> pdf)
Install requirements:
aiogram
flask
requests
wikipedia
gTTS
fpdf
python-dotenv (optional)
"""
import os
import io
import json
import time
import random
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

from flask import Flask, request, send_from_directory, render_template_string, jsonify

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)

# ---------- Config from env ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
# Optional base URL (your railway domain), if not set we'll build from request.host_url
RAILWAY_BASE_URL = os.getenv("RAILWAY_BASE_URL", "")

if not TELEGRAM_TOKEN or not OPENROUTER_API_KEY:
    raise Exception("Set TELEGRAM_TOKEN and OPENROUTER_API_KEY in environment variables (Railway Secrets).")

# ---------- Paths ----------
DATA_DIR = Path("data")
UPLOADS_DIR = DATA_DIR / "uploads"
NOTES_FILE = DATA_DIR / "notes.json"
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
if not NOTES_FILE.exists():
    NOTES_FILE.write_text(json.dumps({}))

# ---------- Bot & Flask ----------
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
app = Flask(__name__, static_folder="static")

# ---------- Helpers ----------
def load_notes():
    try:
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except:
        return {}

def save_notes(d):
    NOTES_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def make_public_file_url(filename, host_url=None):
    # If RAILWAY_BASE_URL set, use it, else use host_url passed from request
    base = RAILWAY_BASE_URL.rstrip("/") if RAILWAY_BASE_URL else (host_url.rstrip("/") if host_url else "")
    if not base:
        # fallback: trying to construct but may not be accessible externally
        return f"/files/{filename}"
    return f"{base}/files/{quote_plus(filename)}"

def call_openrouter_ai_sync(prompt):
    """Synchronous call to OpenRouter Chat Completions (simple wrapper)."""
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.exception("OpenRouter error")
        return f"⚠️ AI error: {str(e)}"

async def call_openrouter_ai(prompt):
    return await asyncio.get_event_loop().run_in_executor(None, call_openrouter_ai_sync, prompt)

# ---------- Small utilities ----------
def generate_image_url(prompt):
    # Free quick image generator using Pollinations
    return f"https://image.pollinations.ai/prompt/{quote_plus(prompt)}"

def generate_meme_url(text):
    # simple memegen link (may vary)
    safe = text.replace(" ", "_")
    return f"https://api.memegen.link/images/custom/_/{safe}.png?background=https://i.imgur.com/8KcYpGf.png"

def text_to_speech_file(text, lang="en"):
    try:
        tts = gTTS(text=text, lang=lang)
        fname = f"{int(time.time())}_tts.mp3"
        path = UPLOADS_DIR / fname
        tts.save(str(path))
        return str(path)
    except Exception as e:
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
        # split text lines
        for line in text.split("\n"):
            pdf.multi_cell(0, 6, line)
        pdf.output(str(path))
        return str(path)
    except Exception as e:
        logging.exception("PDF creation failed")
        return None

# ---------- Telegram Handlers ----------

# set commands for three-dot menu
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply("👋 Hello! I'm Aditya Singh's All-in-One AI Bot.\nJust ask anything or use menu commands (three dots).")

@dp.message_handler(commands=["ai"])
async def cmd_ai(message: types.Message):
    query = message.get_args()
    if not query:
        await message.reply("Usage: /ai <your question>")
        return
    await message.reply("⏳ Thinking...")
    res = await call_openrouter_ai(query)
    await message.reply(res)

@dp.message_handler(commands=["wiki"])
async def cmd_wiki(message: types.Message):
    q = message.get_args()
    if not q:
        await message.reply("Usage: /wiki <topic>")
        return
    try:
        s = wikipedia.summary(q, sentences=3)
        await message.reply(s)
    except Exception:
        await message.reply("❌ Couldn't find on Wikipedia.")

@dp.message_handler(commands=["weather"])
async def cmd_weather(message: types.Message):
    city = message.get_args()
    if not city:
        await message.reply("Usage: /weather <city>")
        return
    if not OPENWEATHER_API_KEY:
        await message.reply("Weather API key not configured.")
        return
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={quote_plus(city)}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=10).json()
        if r.get("cod") != 200:
            await message.reply("City not found.")
            return
        text = f"🌤 Weather in {city}:\n🌡 {r['main']['temp']}°C\n💧 Humidity: {r['main']['humidity']}%\n{r['weather'][0]['description']}"
        await message.reply(text)
    except Exception as e:
        logging.exception("Weather error")
        await message.reply("Weather fetch error.")

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
    await message.reply_photo(url, caption="Here is your meme")

@dp.message_handler(commands=["speak"])
async def cmd_speak(message: types.Message):
    text = message.get_args()
    if not text:
        await message.reply("Usage: /speak <text>")
        return
    path = await asyncio.get_event_loop().run_in_executor(None, text_to_speech_file, text)
    if path:
        await message.reply_audio(open(path, "rb"))
        try:
            os.remove(path)
        except: pass
    else:
        await message.reply("TTS failed.")

@dp.message_handler(commands=["joke"])
async def cmd_joke(message: types.Message):
    jokes = [
        "Why did the programmer quit his job? Because he didn't get arrays.",
        "I told my computer I needed a break, and it said 'No problem — I'll go to sleep.'"
    ]
    await message.reply(random.choice(jokes))

@dp.message_handler(commands=["notes"])
async def cmd_notes(message: types.Message):
    arg = message.get_args()
    user = str(message.from_user.id)
    notes = load_notes()
    if arg.startswith("save "):
        text = arg[5:]
        notes.setdefault(user, []).append(text)
        save_notes(notes)
        await message.reply("✅ Note saved.")
    elif arg.startswith("show"):
        items = notes.get(user, [])
        if not items:
            await message.reply("No notes saved.")
        else:
            await message.reply("Your notes:\n" + "\n".join(f"{i+1}. {t}" for i,t in enumerate(items)))
    elif arg.startswith("clear"):
        notes[user] = []
        save_notes(notes)
        await message.reply("Notes cleared.")
    else:
        await message.reply("Usage: /notes save <text> | /notes show | /notes clear")

@dp.message_handler(commands=["pdf"])
async def cmd_pdf(message: types.Message):
    text = message.get_args()
    if not text:
        await message.reply("Usage: /pdf <text to convert to pdf>")
        return
    path = await asyncio.get_event_loop().run_in_executor(None, make_pdf_from_text, text)
    if path:
        await message.reply_document(open(path, "rb"))
        try: os.remove(path)
        except: pass
    else:
        await message.reply("PDF creation failed.")

# Image uploads from Telegram
@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    # save largest photo
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        data = await bot.download_file(file.file_path)
        fname = f"{int(time.time())}_tg.jpg"
        path = UPLOADS_DIR / fname
        with open(path, "wb") as f:
            f.write(data.read())
        # tell user how to ask question
        await message.reply(f"Image received and saved. To ask about this image, type:\nimg:{fname} <your question>\n(example: img:{fname} What is in this picture?)")
    except Exception as e:
        logging.exception("photo save error")
        await message.reply("Failed to save image.")

# Handling image-question format: img:filename question
@dp.message_handler()
async def handle_text(message: types.Message):
    text = message.text.strip()
    # ignore explicit commands (handled before)
    if text.startswith("/"):
        return
    # if text starts with img: then user asks question about saved image
    if text.startswith("img:"):
        try:
            parts = text.split(maxsplit=1)
            fname = parts[0][4:]
            question = parts[1] if len(parts) > 1 else ""
            if not question:
                await message.reply("Please add your question after image filename.")
                return
            # build public URL for image
            host = ""  # we'll let Flask handler fill if needed
            image_url = make_public_file_url(fname, host_url=RAILWAY_BASE_URL) if RAILWAY_BASE_URL else f"/files/{fname}"
            prompt = f"User question about image: {question}\nImage URL: {image_url}\nPlease describe and answer the question based on the image."
            await message.reply("⏳ Analyzing the image and answering...")
            response = await call_openrouter_ai(prompt)
            await message.reply(response)
        except Exception as e:
            logging.exception("img: handling error")
            await message.reply("Couldn't process your image question.")
        return

    # Normal direct AI chat
    await message.reply("⏳ Thinking...")
    resp = await call_openrouter_ai(text)
    await message.reply(resp)

# Set commands menu on startup
async def set_commands():
    cmds = [
        types.BotCommand("start", "Start the bot"),
        types.BotCommand("ai", "Chat with AI"),
        types.BotCommand("wiki", "Search Wikipedia"),
        types.BotCommand("weather", "Weather info"),
        types.BotCommand("image", "Generate Image"),
        types.BotCommand("meme", "Make Meme"),
        types.BotCommand("speak", "Text to Speech"),
        types.BotCommand("joke", "Random Joke"),
        types.BotCommand("notes", "Notes commands"),
        types.BotCommand("pdf", "Text -> PDF")
    ]
    await bot.set_my_commands(cmds)

# ---------- Flask Web UI (chat + upload) ----------
CHAT_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Aditya Singh AI Bot</title>
  <style>
    body{font-family:Arial;max-width:720px;margin:20px auto;}
    #chat{border:1px solid #ddd;padding:10px;height:400px;overflow:auto;background:#f9f9f9}
    .me{color:#111;text-align:right}
    .bot{color:#0b78e3;text-align:left}
    .bubble{display:inline-block;padding:8px 12px;border-radius:12px;margin:6px 0;max-width:80%}
    .me .bubble{background:#cfe9ff}
    .bot .bubble{background:#e8f0ff}
    #controls{margin-top:10px}
  </style>
</head>
<body>
  <h2>Aditya Singh AI Bot (Web)</h2>
  <div id="chat"></div>
  <div id="controls">
    <input id="msg" placeholder="Ask anything..." style="width:70%;padding:8px;">
    <button onclick="send()">Send</button>
    <input type="file" id="fileinput">
    <button onclick="uploadFile()">Upload Image</button>
  </div>
<script>
async function send(){
  let t=document.getElementById('msg').value.trim();
  if(!t) return;
  appendMessage('me', t);
  document.getElementById('msg').value='';
  const resp=await fetch('/webchat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
  const data=await resp.json();
  appendMessage('bot', data.reply);
}
function appendMessage(who, text){
  let c=document.getElementById('chat');
  let div=document.createElement('div'); div.className=who;
  let span=document.createElement('span'); span.className='bubble'; span.innerText=text;
  div.appendChild(span); c.appendChild(div); c.scrollTop=c.scrollHeight;
}
async function uploadFile(){
  const fi=document.getElementById('fileinput');
  if(!fi.files.length) return alert('Select a file');
  let fd=new FormData(); fd.append('file', fi.files[0]);
  let res=await fetch('/upload', {method:'POST', body:fd});
  let j=await res.json();
  if(j.ok){
    appendMessage('me', 'Uploaded image: '+j.filename);
    appendMessage('bot', 'To ask about this image, type: img:'+j.filename+' Your question');
  } else {
    appendMessage('bot','Upload failed');
  }
}
</script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(CHAT_HTML)

@app.route("/webchat", methods=["POST"])
def webchat():
    data = request.get_json(silent=True) or {}
    text = data.get("text","").strip()
    if not text:
        return jsonify({"reply":"Send some text."})
    # handle image-question pattern as Telegram: img:filename question
    if text.startswith("img:"):
        try:
            parts = text.split(maxsplit=1)
            fname = parts[0][4:]
            question = parts[1] if len(parts)>1 else ""
            if not question:
                return jsonify({"reply":"Please include question after image filename."})
            host = request.host_url.rstrip("/")
            image_url = make_public_file_url(fname, host_url=host)
            prompt = f"User asks about image: {question}\nImage URL: {image_url}\nDescribe and answer based on image."
            reply = call_openrouter_ai_sync(prompt)
            return jsonify({"reply": reply})
        except Exception as e:
            logging.exception("web img error")
            return jsonify({"reply":"Could not process image question."})
    # normal chat
    reply = call_openrouter_ai_sync(text)
    return jsonify({"reply": reply})

@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"ok":False,"error":"No file"})
    f = request.files['file']
    fname = f"{int(time.time())}_{f.filename}"
    path = UPLOADS_DIR / fname
    f.save(path)
    # public url: build using host or env base
    host = request.host_url.rstrip("/")
    public = make_public_file_url(fname, host_url=host)
    return jsonify({"ok":True,"filename": fname, "url": public})

@app.route("/files/<path:filename>")
def serve_file(filename):
    # serve uploaded files
    return send_from_directory(str(UPLOADS_DIR), filename, as_attachment=False)

# ---------- Start both Flask and Bot ----------
def start_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # set commands then start bot and flask concurrently
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_commands())
    # run flask in a thread then bot polling
    import threading
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    executor.start_polling(dp, skip_updates=True)
