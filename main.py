import os
import threading
import telebot
from telebot import types
from flask import Flask

# Botingiz tokeni
TOKEN = "8849139822:AAGOFalntSC4JnlD04JBko4T8EplTXfDzew"
bot = telebot.TeleBot(TOKEN)

# Sizning Admin ID raqamingiz
ADMIN_ID = 8086545587

# Ma'lumotlarni vaqtinchalik saqlash uchun lug'atlar (Bazada ishlashni osonlashtirish uchun)
products = {}  # Tovarlar ro'yxati: {'1': {'name': 'Choynak', 'price': 50000}}
user_carts = {} # Foydalanuvchi savatchalari: {chat_id: {'product_id': quantity}}
temp_product_data = {} # Admin tovar qo'shayotganda vaqtinchalik saqlash uchun

# Render xato bermasligi uchun kichkina veb-sayt
app = Flask(__name__)

@app.route('/')
def index():
    return "Tulpor Savdo Markazi veb-sayti va boti muvaffaqiyatli ishlamoqda!", 200

# Asosiy menyu tugmalari
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn_tovarlar = types.KeyboardButton("TOVARLAR 🌐")
    btn_savat = types.KeyboardButton("🛒 Savat")
    btn_delivery = types.KeyboardButton("🚚 Yetkazib berish")
    btn_about = types.KeyboardButton("ℹ️ Biz haqimizda")
    
    markup.add(btn_tovarlar, btn_savat)
    markup.add(btn_delivery, btn_about)
    
    # Faqat ADMIN_ID ga ega odamga Admin Panel tugmasi ko'rinadi
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("🛠️ Admin Panel"))
        
    return markup

# Admin panel tugmalari
def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("➕ Tovar qo'shish"), types.KeyboardButton("➖ Tovar o'chirish"))
    markup.add(types.KeyboardButton("🎟 Promokod qo'shish"), types.KeyboardButton("🔙 Asosiy menyu"))
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
        reply_markup=get_main_keyboard(message.chat.id)
    )

# ----------------- ASOSIY BO'LIMLAR -----------------

@bot.message_handler(func=lambda message: message.text == "ℹ️ Biz haqimizda")
def about_us(message):
    text = "BIZLAR \"TULPOR SAVDO MARKAZI\" 5 YILDAN BUYON ODAMLARGA HIZMAT KOʻRSATIB KELAMIZ\nSIFAT 1- OʻRINDA ➕"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda message: message.text == "🚚 Yetkazib berish")
def delivery_info(message):
    text = "Bizda Chortoq boʻylab dastafka hizmatimiz mavjud\nOdam tovarlardan buyurtma qilgan narsasini yetkazib beryapmiz."
    bot.send_message(message.chat.id, text)

# ----------------- TOVARLAR VA SAVAT -----------------

@bot.message_handler(func=lambda message: message.text == "TOVARLAR 🌐")
def show_products(message):
    if not products:
        bot.send_message(message.chat.id, "Hozircha do'konda tovarlar yo'q. Tez orada qo'shiladi!")
        return
    
    for pid, p in products.items():
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("🛒 Savatga qo'shish", callback_data=f"add_{pid}")
        markup.add(btn)
        
        text = f"📦 **Nomi:** {p['name']}\n💰 **Narxi:** {p['price']} so'm"
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_'))
def add_to_cart(call):
    pid = call.data.split('_')[1]
    user_id = call.message.chat.id
    
    if user_id not in user_carts:
        user_carts[user_id] = {}
        
    if pid in user_carts[user_id]:
        user_carts[user_id][pid] += 1
    else:
        user_carts[user_id][pid] = 1
        
    bot.answer_callback_query(call.id, "✅ Tovar savatga qo'shildi!", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "🛒 Savat")
def show_cart(message):
    user_id = message.chat.id
    if user_id not in user_carts or not user_carts[user_id]:
        bot.send_message(message.chat.id, "🛒 Savatchangiz hozircha boʻsh.")
        return
    
    text = "🛒 **Sizning savatchangizda:**\n\n"
    total_price = 0
    
    for pid, qty in user_carts[user_id].items():
        if pid in products:
            p = products[pid]
            cost = int(p['price']) * qty
            total_price += cost
            text += f"▪️ {p['name']} — {qty} ta = {cost} so'm\n"
            
    text += f"\n**Jami summa: {total_price} so'm**"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Rasmiylashtirish", callback_data="checkout"))
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'checkout')
def process_checkout(call):
    bot.send_message(call.message.chat.id, "✅ Buyurtmangiz muvaffaqiyatli rasmiylashtirildi! Yetkazib berish xizmati tez orada siz bilan bog'lanadi.")
    user_carts[call.message.chat.id] = {} # Xariddan so'ng savat tozalanadi
    bot.answer_callback_query(call.id)

# ----------------- ADMIN PANEL -----------------

@bot.message_handler(func=lambda message: message.text == "🛠️ Admin Panel")
def admin_panel(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(message.chat.id, "👨‍💻 Admin panelga xush kelibsiz. Nima amaliyot bajaramiz?", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.chat.id, "❌ Bu bo'limga kirish huquqingiz yo'q.")

@bot.message_handler(func=lambda message: message.text == "🔙 Asosiy menyu")
def back_to_main(message):
    bot.send_message(message.chat.id, "Asosiy menyuga qaytdingiz.", reply_markup=get_main_keyboard(message.chat.id))

# --- Tovar qo'shish jarayoni ---
@bot.message_handler(func=lambda message: message.text == "➕ Tovar qo'shish" and message.chat.id == ADMIN_ID)
def add_product_start(message):
    msg = bot.send_message(message.chat.id, "Yangi tovarning nomini kiriting:")
    bot.register_next_step_handler(msg, process_product_name)

def process_product_name(message):
    if message.text == "🔙 Asosiy menyu":
        back_to_main(message)
        return
    temp_product_data['name'] = message.text
    msg = bot.send_message(message.chat.id, "Tovar narxini kiriting (faqat raqam bilan, masalan: 50000):")
    bot.register_next_step_handler(msg, process_product_price)

def process_product_price(message):
    if message.text == "🔙 Asosiy menyu":
        back_to_main(message)
        return
    temp_product_data['price'] = message.text
    new_id = str(len(products) + 1)
    
    # Tovarni bazaga saqlash
    products[new_id] = {
        'name': temp_product_data['name'],
        'price': temp_product_data['price']
    }
    
    bot.send_message(
        message.chat.id, 
        f"✅ Tovar muvaffaqiyatli qo'shildi!\n\nNomi: {temp_product_data['name']}\nNarxi: {temp_product_data['price']} so'm",
        reply_markup=get_admin_keyboard()
    )

@bot.message_handler(func=lambda message: message.text in ["➖ Tovar o'chirish", "🎟 Promokod qo'shish"] and message.chat.id == ADMIN_ID)
def under_construction_admin(message):
    bot.send_message(message.chat.id, "⚙️ Bu bo'lim ustida ishlanmoqda. Keyingi bosqichda qo'shamiz.")


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
    
