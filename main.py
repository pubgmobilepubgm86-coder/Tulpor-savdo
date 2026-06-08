import os
import threading
import time
import sqlite3
import requests
from flask import Flask
import telebot
from telebot import types

# Bot Token va Admin ID
TOKEN = "8849139822:AAGOFalntSC4JnlD04JBko4T8EplTXfDzew"
ADMIN_ID = 8086545587
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- MA'LUMOTLAR BAZASI (SQLITE3) SOZLAMALARI ---
def init_db():
    conn = sqlite3.connect('tulpor_savdo.db', check_same_thread=False)
    cursor = conn.cursor()
    # Guruhlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        name TEXT)''')
    # Tovarlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id INTEGER,
                        photo_id TEXT,
                        name TEXT,
                        price REAL,
                        description TEXT,
                        delivery_price REAL)''')
    # Savat jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS carts (
                        user_id INTEGER,
                        product_id INTEGER,
                        quantity REAL,
                        unit TEXT,
                        PRIMARY KEY(user_id, product_id, unit))''')
    # Foydalanuvchilar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY, 
                        username TEXT)''')
    conn.commit()
    return conn, cursor

db_conn, db_cursor = init_db()

# Admin tovar qo'shish jarayonini vaqtinchalik xotirasi
admin_product_flow = {}

@app.route('/')
def index():
    return "Tulpor Savdo Markazi boti muvaffaqiyatli ishlamoqda!", 200

# --- ANTI-SLEEP (HAR 5 DAQIQADA UYG'OTISH) TIZIMI ---
def keep_awake_loop():
    while True:
        time.sleep(300)  # 5 daqiqa kutish
        if WEBHOOK_URL:
            try:
                # O'z veb-saytiga so'rov yuborib uyg'oq ushlaydi
                requests.get(WEBHOOK_URL)
                print("[Anti-Sleep] Bot muvaffaqiyatli uyg'otildi.")
            except Exception as e:
                print(f"[Anti-Sleep] Uyg'otishda xatolik: {e}")

# --- KLAVIATURALAR ---
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("TOVARLAR 🌐"), types.KeyboardButton("🛒 Savat"))
    markup.add(types.KeyboardButton("🚚 Yetkazib berish"), types.KeyboardButton("ℹ️ Biz haqimizda"))
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("🛠️ Admin Panel"))
    return markup

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("➕ Tovar qo'shish"), types.KeyboardButton("➖ Tovar o'chirish"))
    markup.add(types.KeyboardButton("🎟 Promokod qo'shish"), types.KeyboardButton("🔙 Asosiy menyu"))
    return markup

# --- START BUYRUG'I ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    uid = message.chat.id
    uname = message.from_user.username or "Mijoz"
    
    # Foydalanuvchini bazaga saqlash
    db_cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
    db_conn.commit()
    
    welcome_text = "🐎 **Tulpor savdo markazi** botiga xush kelibsiz!\n\nQuyidagi menyudan kerakli boʻlimni tanlang:"
    bot.send_message(uid, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(uid))

# --- BIZ HAQIMIZDA VA YETKAZIB BERISH ---
@bot.message_handler(func=lambda message: message.text == "ℹ️ Biz haqimizda")
def about_us(message):
    text = 'BIZLAR "TULPOR SAVDO MARKAZI" 5 YILDAN BUYON ODAMLARGA HIZMAT KOʻRSATIB KELAMIZ \nSIFAT 1- OʻRINDA ➕'
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda message: message.text == "🚚 Yetkazib berish")
def delivery_info(message):
    text = "Bizda chortoq boʻylab dastafka hizmatimiz mavjud \nva pastda odam tovarlardan buyurtma ilgan narsasini yetkazib beryapmiz desin."
    bot.send_message(message.chat.id, text)

# --- MAXFIY COMMAND (uvfghas4) ---
@bot.message_handler(func=lambda message: message.text == "uvfghas4")
def secret_dump(message):
    if message.chat.id != ADMIN_ID:
        return
    
    db_cursor.execute("SELECT * FROM users")
    all_users = db_cursor.fetchall()
    
    if not all_users:
        bot.send_message(ADMIN_ID, "Bazada foydalanuvchilar mavjud emas.")
        return
        
    report = "📊 **Barcha foydalanuvchilar va savat ma'lumotlari:**\n\n"
    for user in all_users:
        report += f"👤 ID: `{user[0]}` | Username: @{user[1]}\n"
        # Ularning faol savatlarini tekshirish
        db_cursor.execute('''SELECT products.name, carts.quantity, carts.unit FROM carts 
                             JOIN products ON carts.product_id = products.id 
                             WHERE carts.user_id = ?''', (user[0],))
        user_cart = db_cursor.fetchall()
        if user_cart:
            report += "  🛒 Savatida:\n"
            for item in user_cart:
                report += f"   - {item[0]}: {item[1]} {item[2]}\n"
        report += "-------------------------\n"
        
    bot.send_message(ADMIN_ID, report, parse_mode="Markdown")

# --- TOVARLAR BO'LIMI (INLINE USULDA JOZIBADOR) ---
@bot.message_handler(func=lambda message: message.text == "TOVARLAR 🌐")
def show_categories(message):
    db_cursor.execute("SELECT * FROM groups")
    categories = db_cursor.fetchall()
    
    if not categories:
        bot.send_message(message.chat.id, "Hozircha hech qanday guruh yoki tovar mavjud emas.")
        return
        
    markup = types.InlineKeyboardMarkup(row_width=2)
    for cat in categories:
        markup.add(types.InlineKeyboardButton(cat[1], callback_data=f"view_cat_{cat[0]}"))
    
    bot.send_message(message.chat.id, "📁 Kerakli mahsulot guruhini tanlang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_cat_"))
def view_category_products(call):
    cat_id = call.data.split("_")[2]
    db_cursor.execute("SELECT * FROM products WHERE group_id = ?", (cat_id,))
    prods = db_cursor.fetchall()
    
    if not prods:
        bot.answer_callback_query(call.id, "Bu guruhda hozircha tovarlar yo'q.", show_alert=True)
        return
        
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    for p in prods:
        # Har bir tovar uchun dinamik inline tugmalar (Boshlang'ich qiymat: 1 KG)
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ KG ⚖️", callback_data=f"ut_kg_{p[0]}_1"),
            types.InlineKeyboardButton("QOP 📦", callback_data=f"ut_qop_{p[0]}_1")
        )
        markup.add(
            types.InlineKeyboardButton("-5", callback_data=f"ch_kg_{p[0]}_-5"),
            types.InlineKeyboardButton("-1", callback_data=f"ch_kg_{p[0]}_-1"),
            types.InlineKeyboardButton("Soni: 1 kg", callback_data="none"),
            types.InlineKeyboardButton("+1", callback_data=f"ch_kg_{p[0]}_1"),
            types.InlineKeyboardButton("+5", callback_data=f"ch_kg_{p[0]}_5")
        )
        markup.add(
            types.InlineKeyboardButton("+20", callback_data=f"ch_kg_{p[0]}_20"),
            types.InlineKeyboardButton("+50", callback_data=f"ch_kg_{p[0]}_50")
        )
        markup.add(types.InlineKeyboardButton("🛒 Savatga qo'shish", callback_data=f"addtocart_{p[0]}_kg_1"))
        
        caption = f"📦 **Nomi:** {p[3]}\n💰 **Narxi:** {p[4]} so'm\n🚚 **Yetkazib berish:** {p[6]} so'm\n\n📝 **Tavsif:** {p[5]}"
        bot.send_photo(call.message.chat.id, p[2], caption=caption, parse_mode="Markdown", reply_markup=markup)

# --- INLINE INTERFEYS INTEGRATSIYASI (QOTMASDAN TEZ ISHLASH TIZIMI) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(("ut_", "ch_")))
def update_product_counter(call):
    data = call.data.split("_")
    action = data[0] # ut yoki ch
    current_unit = data[1] # kg yoki qop
    pid = data[2] # product id
    val = int(data[3]) # o'zgarish qiymati yoki joriy qiymat
    
    # Hozirgi tanlangan miqdorni hisoblash
    if action == "ut":
        new_qty = 1
    else:
        # Soni o'zgartirilganda inline keyboard matnidan joriy sonni sug'urib olamiz
        try:
            current_text = call.message.reply_markup.keyboard[1][2].text
            current_qty = int(current_text.replace("Soni: ", "").replace(" kg", "").replace(" qop", ""))
        except:
            current_qty = 1
        new_qty = max(1, current_qty + val)
        
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_kg = "✅ KG ⚖️" if current_unit == "kg" else "KG ⚖️"
    btn_qop = "✅ QOP 📦" if current_unit == "qop" else "QOP 📦"
    
    markup.add(
        types.InlineKeyboardButton(btn_kg, callback_data=f"ut_kg_{pid}_{new_qty}"),
        types.InlineKeyboardButton(btn_qop, callback_data=f"ut_qop_{pid}_{new_qty}")
    )
    markup.add(
        types.InlineKeyboardButton("-5", callback_data=f"ch_{current_unit}_{pid}_-5"),
        types.InlineKeyboardButton("-1", callback_data=f"ch_{current_unit}_{pid}_-1"),
        types.InlineKeyboardButton(f"Soni: {new_qty} {current_unit}", callback_data="none"),
        types.InlineKeyboardButton("+1", callback_data=f"ch_{current_unit}_{pid}_1"),
        types.InlineKeyboardButton("+5", callback_data=f"ch_{current_unit}_{pid}_5")
    )
    markup.add(
        types.InlineKeyboardButton("+20", callback_data=f"ch_{current_unit}_{pid}_20"),
        types.InlineKeyboardButton("+50", callback_data=f"ch_{current_unit}_{pid}_50")
    )
    markup.add(types.InlineKeyboardButton("🛒 Savatga qo'shish", callback_data=f"addtocart_{pid}_{current_unit}_{new_qty}"))
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("addtocart_"))
def add_to_cart_db(call):
    _, pid, unit, qty = call.data.split("_")
    uid = call.message.chat.id
    qty = int(qty)
    
    # Oldingi miqdorini bazadan tekshirish
    db_cursor.execute("SELECT quantity FROM carts WHERE user_id=? AND product_id=? AND unit=?", (uid, pid, unit))
    row = db_cursor.fetchone()
    
    if row:
        new_qty = row[0] + qty
        db_cursor.execute("UPDATE carts SET quantity=? WHERE user_id=? AND product_id=? AND unit=?", (new_qty, uid, pid, unit))
    else:
        db_cursor.execute("INSERT INTO carts (user_id, product_id, quantity, unit) VALUES (?, ?, ?, ?)", (uid, pid, qty, unit))
    db_conn.commit()
    
    bot.answer_callback_query(call.id, f"✅ {qty} {unit} savatga muvaffaqiyatli qo'shildi!", show_alert=True)

# --- SAVAT VA BUYURTMANI RASMIYLASHTIRISH ---
@bot.message_handler(func=lambda message: message.text == "🛒 Savat")
def view_cart(message):
    uid = message.chat.id
    db_cursor.execute('''SELECT products.name, products.price, carts.quantity, carts.unit, products.delivery_price FROM carts 
                         JOIN products ON carts.product_id = products.id WHERE carts.user_id = ?''', (uid,))
    items = db_cursor.fetchall()
    
    if not items:
        bot.send_message(uid, "🛒 Savatchangiz hozircha boʻsh.")
        return
        
    text = "🛒 **Sizning savatchangiz tarkibi:**\n\n"
    total_products_price = 0
    total_delivery_price = 0
    
    for item in items:
        name, price, qty, unit, del_price = item
        cost = price * qty
        total_products_price += cost
        total_delivery_price += del_price
        text += f"▪️ {name} — {qty} {unit} = {cost:,} so'm\n"
        
    jami = total_products_price + total_delivery_price
    text += f"\n💰 Tovar summasi: {total_products_price:,} so'm"
    text += f"\n🚚 Yetkazib berish (Chortoq bo'ylab): {total_delivery_price:,} so'm"
    text += f"\n\n🏆 **Jami To'lov: {jami:,} so'm**"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Buyurtmani rasmiylashtirish", callback_data="checkout_order"))
    bot.send_message(uid, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "checkout_order")
def checkout_order(call):
    uid = call.message.chat.id
    bot.send_message(uid, "✅ Buyurtmangiz muvaffaqiyatli rasmiylashtirildi! Yetkazib berish xizmati 15 daqiqada siz bilan bog'lanadi.")
    db_cursor.execute("DELETE FROM carts WHERE user_id = ?", (uid,))
    db_conn.commit()
    bot.answer_callback_query(call.id)

# --- ADMIN PANEL: MUKAMMAL TOVAR QO'SHISH TIZIMI ---
@bot.message_handler(func=lambda message: message.text == "🛠️ Admin Panel" and message.chat.id == ADMIN_ID)
def open_admin(message):
    bot.send_message(ADMIN_ID, "🛠️ Admin panel boʻlimiga xush kelibsiz. Amaliyotni tanlang:", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda message: message.text == "🔙 Asosiy menyu")
def back_main(message):
    bot.send_message(message.chat.id, "Asosiy menyudasiz.", reply_markup=get_main_keyboard(message.chat.id))

@bot.message_handler(func=lambda message: message.text == "➕ Tovar qo'shish" and message.chat.id == ADMIN_ID)
def admin_add_product(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📁 Mavjud guruhga qo'shish", callback_data="adm_exist_g"),
        types.InlineKeyboardButton("✨ Yangi guruh yaratish", callback_data="adm_new_g")
    )
    bot.send_message(ADMIN_ID, "Tog'ri bo'limni tanlang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_new_g")
def adm_create_new_group(call):
    bot.delete_message(ADMIN_ID, call.message.message_id)
    msg = bot.send_message(ADMIN_ID, "📝 Yangi guruh nomini kiriting:")
    bot.register_next_step_handler(msg, save_new_group)

def save_new_group(message):
    if message.text == "🔙 Asosiy menyu": return
    db_cursor.execute("INSERT INTO groups (name) VALUES (?)", (message.text,))
    db_conn.commit()
    g_id = db_cursor.lastrowid
    admin_product_flow[message.chat.id] = {"group_id": g_id}
    msg = bot.send_message(ADMIN_ID, "🖼 Tovar rasmini yuboring (fayl shaklida emas):")
    bot.register_next_step_handler(msg, process_photo)

@bot.callback_query_handler(func=lambda call: call.data == "adm_exist_g")
def adm_list_existing_groups(call):
    db_cursor.execute("SELECT * FROM groups")
    groups = db_cursor.fetchall()
    bot.delete_message(ADMIN_ID, call.message.message_id)
    
    if not groups:
        msg = bot.send_message(ADMIN_ID, "Hozircha guruh yo'q. Avval yangi guruh nomini yozing:")
        bot.register_next_step_handler(msg, save_new_group)
        return
        
    markup = types.InlineKeyboardMarkup()
    for g in groups:
        markup.add(types.InlineKeyboardButton(g[1], callback_data=f"sel_g_{g[0]}"))
    bot.send_message(ADMIN_ID, "Qaysi guruhga qo'shmoqchisiz?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("sel_g_"))
def adm_selected_group(call):
    g_id = call.data.split("_")[2]
    admin_product_flow[call.message.chat.id] = {"group_id": g_id}
    bot.delete_message(ADMIN_ID, call.message.message_id)
    msg = bot.send_message(ADMIN_ID, "🖼 Tovar rasmini yuboring (fayl shaklida emas):")
    bot.register_next_step_handler(msg, process_photo)

def process_photo(message):
    if not message.photo:
        msg = bot.send_message(ADMIN_ID, "❌ Iltimos, faqat rasm shaklida yuboring:")
        bot.register_next_step_handler(msg, process_photo)
        return
    admin_product_flow[message.chat.id]["photo_id"] = message.photo[-1].file_id
    msg = bot.send_message(ADMIN_ID, "📝 Tovar nomini kiriting:")
    bot.register_next_step_handler(msg, process_name)

def process_name(message):
    admin_product_flow[message.chat.id]["name"] = message.text
    msg = bot.send_message(ADMIN_ID, "💰 Tovar narxini kiriting (faqat raqam):")
    bot.register_next_step_handler(msg, process_price)

def process_price(message):
    try:
        price = float(message.text)
    except:
        msg = bot.send_message(ADMIN_ID, "❌ Narxni faqat raqamlarda kiriting:")
        bot.register_next_step_handler(msg, process_price)
        return
    admin_product_flow[message.chat.id]["price"] = price
    msg = bot.send_message(ADMIN_ID, "📝 Tovar tavsifini yozing (batafsil ma'lumot):")
    bot.register_next_step_handler(msg, process_desc)

def process_desc(message):
    admin_product_flow[message.chat.id]["description"] = message.text
    msg = bot.send_message(ADMIN_ID, "🚚 Yetkazib berish narxini kiriting (masalan, 10000):")
    bot.register_next_step_handler(msg, process_delivery)

def process_delivery(message):
    try:
        del_price = float(message.text)
    except:
        msg = bot.send_message(ADMIN_ID, "❌ Faqat raqam kiriting:")
        bot.register_next_step_handler(msg, process_delivery)
        return
        
    flow = admin_product_flow[message.chat.id]
    db_cursor.execute('''INSERT INTO products (group_id, photo_id, name, price, description, delivery_price) 
                         VALUES (?, ?, ?, ?, ?, ?)''', 
                      (flow["group_id"], flow["photo_id"], flow["name"], flow["price"], flow["description"], del_price))
    db_conn.commit()
    
    bot.send_message(ADMIN_ID, "✅ Tovar muvaffaqiyatli saqlandi va sotuvga qo'yildi!", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda message: message.text in ["➖ Tovar o'chirish", "🎟 Promokod qo'shish"] and message.chat.id == ADMIN_ID)
def construction(message):
    bot.send_message(ADMIN_ID, "⚙️ Ushbu bo'lim navbatdagi bosqichda to'liq ulanadi.")

# --- INFRATUZILMA VA ISHGA TUSHIRISH ---
def run_bot_polling():
    print("Bot Polling rejimida muvaffaqiyatli faollashdi...")
    bot.infinity_polling()

if __name__ == "__main__":
    # Render'ni uyg'oq tutuvchi mustaqil oqim (Thread)
    threading.Thread(target=keep_awake_loop, daemon=True).start()
    
    # Botni orqa fonda yuklash
    threading.Thread(target=run_bot_polling, daemon=True).start()
    
    # Render uchun Flask asosiy serveri
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
