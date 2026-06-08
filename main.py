import os
import threading
import telebot
from telebot import types
from flask import Flask

# Botingiz tokeni
TOKEN = "8849139822:AAGOFalntSC4JnlD04JBko4T8EplTXfDzew"
bot = telebot.TeleBot(TOKEN)

# Render xato bermasligi uchun kichkina veb-sayt
app = Flask(__name__)

@app.route('/')
def index():
    return "Tulpor Savdo Markazi veb-sayti va boti muvaffaqiyatli ishlamoqda!", 200

# Asosiy menyu
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn_tovarlar = types.KeyboardButton("TOVARLAR 🌐")
    btn_savat = types.KeyboardButton("🛒 Savat")
    btn_delivery = types.KeyboardButton("🚚 Yetkazib berish")
    btn_about = types.KeyboardButton("ℹ️ Biz haqimizda")
    btn_admin = types.KeyboardButton("🛠️ Admin Panel")
    
    markup.add(btn_tovarlar, btn_savat)
    markup.add(btn_delivery, btn_about)
    markup.add(btn_admin)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "🐎 **Tulpor savdo markazi** botiga xush kelibsiz!\n\n"
        "Quyidagi menyudan kerakli boʻlimni tanlang:"
    )
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode="Markdown", 
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda message: True)
def handle_menu(message):
    if message.text == "TOVARLAR 🌐":
        bot.send_message(message.chat.id, "🌐 Mahsulotlar boʻlimi tez orada ishga tushadi.")
    elif message.text == "🛒 Savat":
        bot.send_message(message.chat.id, "🛒 Savatchangiz hozircha boʻsh.")
    elif message.text == "🚚 Yetkazib berish":
        bot.send_message(message.chat.id, "🚚 Yetkazib berish shartlari haqida maʼlumot.")
    elif message.text == "ℹ️ Biz haqimizda":
        bot.send_message(message.chat.id, "ℹ️ Tulpor savdo markazi haqida maʼlumot.")
    elif message.text == "🛠️ Admin Panel":
        bot.send_message(message.chat.id, "🛠️ Admin panel boʻlimiga xush kelibsiz.")

# Botni alohida oqimda ishga tushirish funksiyasi
def run_bot():
    print("Bot ishlashni boshladi...")
    bot.infinity_polling()

if __name__ == "__main__":
    # Botni fon rejimida ishga tushiramiz
    threading.Thread(target=run_bot).start()
    
    # Veb-saytni asosiy oqimda ishga tushiramiz (Render uchun)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
      
