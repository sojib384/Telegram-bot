import os
import telebot
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "ভাই, Bot 24/7 Online আছে 🔥")

@bot.message_handler(commands=['ping'])
def send_ping(message):
    bot.reply_to(message, "Pong! Bot জিন্দা আছে ✅")

print("Bot Running...")
bot.infinity_polling()