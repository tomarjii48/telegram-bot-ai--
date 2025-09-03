import telebot
import requests
import wikipedia
from gtts import gTTS
import os
from flask import Flask, request

# 🔑 Secrets (Railway pe ENV variables set karna hoga)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
server = Flask(__name__)

# ✅ Start Command
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "🤖 Namaste! Main Aditya Singh ka AI Bot hoon.\nMujhse baat karo ya commands try karo!")

# ✅ Wikipedia Search
@bot.message_handler(commands=["wiki"])
def wiki_search(message):
    try:
        query = message.text.replace("/wiki ", "")
        result = wikipedia.summary(query, sentences=2)
        bot.reply_to(message, result)
    except:
        bot.reply_to(message, "⚠️ Sorry, kuch nahi mila Wikipedia pe.")

# ✅ Weather Info
@bot.message_handler(commands=["weather"])
def weather(message):
    city = message.text.replace("/weather ", "")
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=hi"
    data = requests.get(url).json()
    if data.get("cod") != 200:
        bot.reply_to(message, "⚠️ City not found!")
    else:
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]
        reply = f"🌤 Weather in {city}:\n🌡 Temp: {temp}°C\n☁️ {desc}"
        bot.reply_to(message, reply)

# ✅ AI Chat (via OpenRouter)
@bot.message_handler(commands=["ai"])
def ai_chat(message):
    query = message.text.replace("/ai ", "")
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [{"role": "user", "content": query}]
    }
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
        res = r.json()["choices"][0]["message"]["content"]
        bot.reply_to(message, res)
    except:
        bot.reply_to(message, "⚠️ AI se jawab nahi mila.")

# ✅ Text to Speech
@bot.message_handler(commands=["speak"])
def speak(message):
    text = message.text.replace("/speak ", "")
    speech = gTTS(text=text, lang="hi")
    filename = "voice.mp3"
    speech.save(filename)
    with open(filename, "rb") as audio:
        bot.send_voice(message.chat.id, audio)
    os.remove(filename)

# ✅ Normal Chat (fallback)
@bot.message_handler(func=lambda m: True)
def echo_all(message):
    bot.reply_to(message, "👍 Command try karo: /wiki, /weather, /ai, /speak")

# 🌍 Flask Route (for Railway uptime)
@server.route("/")
def home():
    return "🤖 Aditya Singh AI Bot Running!"

@server.route("/" + TELEGRAM_TOKEN, methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

import threading
def run_bot():
    bot.polling(non_stop=True)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 8080))
    server.run(host="0.0.0.0", port=port)
