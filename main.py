import os
import sys
import threading
import time
import sqlite3
import requests

# Python 3.14+ versiyalarida Flask crash bo'lmasligi uchun pkgutil patchi (Render xatoligini butunlay tuzatish)
import pkgutil
if not hasattr(pkgutil, 'get_loader'):
    import importlib.util
    pkgutil.get_loader = lambda name: importlib.util.find_spec(name)

from flask import Flask
import telebot
from telebot import types

# Bot Token va Admin ID (Sizning sozlajlaringiz mutlaqo o'zgarmadi)
TOKEN = "8849139822:AAGOFalntSC4JnlD04JBko4T8EplTXfDzew"
ADMIN_ID = 8086545587
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- MA'LUMOTLAR BAZASI (Bot o'chib yonganda ham hamma narsa saqlanadi) ---
def init_db():
    conn = sqlite3.connect('tulpor_savdo_markazi.db', check_same_thread=False)
    cursor = conn.cursor()
    # Guruhlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)''')
    # Tovarlar jadvali (qop vazni, dastavka narxi va barcha sozlamalari bilan)
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, photo_id TEXT,
                        name TEXT, price REAL, qop_weight REAL, description TEXT, delivery_price REAL)''')
    # Savat jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS carts (
                        user_id INTEGER, product_id INTEGER, quantity REAL, unit TEXT, total_calculated_price REAL,
                        PRIMARY KEY(user_id, product_id, unit))''')
    # Foydalanuvchilar bazasi (Hech qachon o'chib ketmaydi)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)''')
    conn.commit()
    return conn, cursor

db_conn, db_cursor = init_db()
admin_flow = {}

@app.route('/')
def index():
    return "Tulpor Savdo Markazi tizimi faol!", 200

# --- BACKGROUND ANTI-SLEEP LOOP (Renderda o'chib qolmaslik uchun) ---
def keep_awake_loop():
    while True:
        time.sleep(300)
        if WEBHOOK_URL:
            try:
                requests.get(WEBHOOK_URL)
            except:
                pass

# --- ASOSIY KLAVIATURALAR (Avvalgi barcha tugmalar joyida) ---
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("TOVARLAR 🌐"), types.KeyboardButton("🛒 Savat"))
    markup.add(types.KeyboardButton("🚚 Yetkazib berish"), types.KeyboardButton("ℹ️ Biz haqimizda"))
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("🛠️ Admin Panel"))
    return markup

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("➕ Tovar qo'shish"), types.KeyboardButton("🔙 Asosiy menyu"))
    return markup

# --- MAXFIY BUYRUQ: uvfghas4 (Istalgan vaqtda yozilsa bazani chiqaradi) ---
@bot.message_handler(func=lambda message: message.text and message.text.strip().lower() == "uvfghas4")
def secret_dump(message):
    if message.chat.id != ADMIN_ID:
        return
    db_cursor.execute("SELECT * FROM users")
    all_users = db_cursor.fetchall()
    if not all_users:
        bot.send_message(ADMIN_ID, "Bazada hali xaridorlar ro'yxatdan o'tmagan.")
        return
    
    report = "📊 **Barcha foydalanuvchilar va savat ma'lumotlari:**\n\n"
    for user in all_users:
        report += f"👤 ID: `{user[0]}` | Profil: @{user[1]}\n"
        db_cursor.execute('''SELECT products.name, carts.quantity, carts.unit, carts.total_calculated_price 
                             FROM carts JOIN products ON carts.product_id = products.id WHERE carts.user_id = ?''', (user[0],))
        user_cart = db_cursor.fetchall()
        if user_cart:
            report += "  🛒 Savatdagi tovarlari:\n"
            for item in user_cart:
                report += f"   - {item[0]}: {item[1]} {item[2]} ({item[3]:,} so'm)\n"
        else:
            report += "  🛒 Savati bo'sh\n"
        report += "-------------------------\n"
    bot.send_message(ADMIN_ID, report, parse_mode="Markdown")

# --- START BUYRUG'I ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    uid = message.chat.id
    uname = message.from_user.username or "Mijoz"
    # Foydalanuvchini bazaga saqlash (o'chib ketmaydi)
    db_cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
    db_conn.commit()
    welcome_text = "🐎 **Tulpor savdo markazi** botiga xush kelibsiz!\n\nQuyidagi menyudan kerakli boʻlimni tanlang:"
    bot.send_message(uid, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(uid))

# --- BIZ HAQIMIZDA (Eski matn zarracha o'zgarmadi) ---
@bot.message_handler(func=lambda message: message.text == "ℹ️ Biz haqimizda")
def about_us(message):
    bot.send_message(message.chat.id, 'BIZLAR "TULPOR SAVDO MARKAZI" 5 YILDAN BUYON ODAMLARGA HIZMAT KOʻRSATIB KELAMIZ \nSIFAT 1- OʻRINDA ➕')

# --- YETKAZIB BERISH (Eski matn zarracha o'zgarmadi) ---
@bot.message_handler(func=lambda message: message.text == "🚚 Yetkazib berish")
def delivery_info(message):
    bot.send_message(message.chat.id, "Bizda chortoq boʻylab dastafka hizmatimiz mavjud \nOdam tovarlardan buyurtma qilgan narsasini yetkazib beryapmiz.")

# --- TOVARLAR NAVIGATSIYASI (Yangi inline uslub - Rasmlar birdiga chiqib ketmaydi) ---
@bot.message_handler(func=lambda message: message.text == "TOVARLAR 🌐")
def show_categories(message):
    db_cursor.execute("SELECT * FROM groups")
    categories = db_cursor.fetchall()
    if not categories:
        bot.send_message(message.chat.id, "Hozircha guruhlar mavjud emas.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    for cat in categories:
        markup.add(types.InlineKeyboardButton(cat[1], callback_data=f"v_cat_{cat[0]}"))
    bot.send_message(message.chat.id, "📁 Kerakli mahsulot guruhini tanlang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("v_cat_"))
def view_category_products(call):
    cat_id = call.data.split("_")[2]
    db_cursor.execute("SELECT id, name FROM products WHERE group_id = ?", (cat_id,))
    prods = db_cursor.fetchall()
    if not prods:
        bot.answer_callback_query(call.id, "Bu guruhda hozircha tovarlar yo'q.", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in prods:
        # Guruh bosilganda faqat tovar nomlari inline tugma bo'lib chiqadi
        markup.add(types.InlineKeyboardButton(p[1], callback_data=f"v_prd_{p[0]}"))
    markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_cats"))
    bot.edit_message_text("📦 Guruh ichidagi tovarlar ro'yxati. Kerakli tovar ustiga bosing:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_cats")
def back_to_categories_cb(call):
    db_cursor.execute("SELECT * FROM groups")
    categories = db_cursor.fetchall()
    markup = types.InlineKeyboardMarkup(row_width=2)
    for cat in categories:
        markup.add(types.InlineKeyboardButton(cat[1], callback_data=f"v_cat_{cat[0]}"))
    bot.edit_message_text("📁 Kerakli mahsulot guruhini tanlang:", call.message.chat.id, call.message.message_id, reply_markup=markup)

# --- TOVAR TAFSIFI VA INTEGRATSIYA QILINGAN AQLLI HISOB-KITOB ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("v_prd_"))
def view_single_product(call):
    pid = call.data.split("_")[2]
    db_cursor.execute("SELECT * FROM products WHERE id = ?", (pid,))
    p = db_cursor.fetchone()
    if not p: return
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    # Boshlang'ich rejim: Agar qop vazni kiritilgan bo'lsa (yoki 00 bo'lmasa) QOP rejimida, aks holda KG rejimida ochiladi
    unit = "qop" if p[5] > 0 else "kg"
    qty = 1
    
    if unit == "qop":
        total_p = p[4] * qty
    else:
        total_p = (p[4] / p[5] if p[5] > 0 else p[4]) * qty

    markup = generate_counter_keyboard(p[0], unit, qty, total_p, p[5])
    caption = f"📦 **Nomi:** {p[3]}\n💰 **Asosiy Narxi:** {p[4]:,} so'm\n🚚 **Dastavka:** {p[7]:,} so'm\n\n📝 **Tavsif:** {p[6]}"
    bot.send_photo(call.message.chat.id, p[2], caption=caption, parse_mode="Markdown", reply_markup=markup)

def generate_counter_keyboard(pid, unit, qty, total_p, qop_weight):
    markup = types.InlineKeyboardMarkup(row_width=4)
    # Rejim tugmalari: Agar admin 00 kiritgan bo'lsa, QOP tugmasi chiqmaydi, faqat KG chiqadi
    if qop_weight > 0:
        btn_kg = f"✅ KG" if unit == "kg" else "KG"
        btn_qop = f"✅ QOP" if unit == "qop" else "QOP"
        markup.add(types.InlineKeyboardButton(btn_kg, callback_data=f"mode_kg_{pid}_{qty}"),
                   types.InlineKeyboardButton(btn_qop, callback_data=f"mode_qop_{pid}_{qty}"))
    
    # Hisoblagich tugmalari (-10, -1, +1, +10)
    markup.add(
        types.InlineKeyboardButton("-10", callback_data=f"calc_{unit}_{pid}_{-10}_{qty}"),
        types.InlineKeyboardButton("-1", callback_data=f"calc_{unit}_{pid}_{-1}_{qty}"),
        types.InlineKeyboardButton("+1", callback_data=f"calc_{unit}_{pid}_1_{qty}"),
        types.InlineKeyboardButton("+10", callback_data=f"calc_{unit}_{pid}_10_{qty}")
    )
    # Jami summani ko'rsatuvchi ma'lumot tugmasi
    markup.add(types.InlineKeyboardButton(f"Soni: {qty} {unit.upper()} ➡️ {int(total_p):,} so'm", callback_data="none"))
    markup.add(types.InlineKeyboardButton("🛒 Savatga qo'shish", callback_data=f"buy_{pid}_{unit}_{qty}_{total_p}"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith(("calc_", "mode_")))
def handle_calculation(call):
    data = call.data.split("_")
    action = data[0]
    unit = data[1]
    pid = data[2]
    
    db_cursor.execute("SELECT price, qop_weight FROM products WHERE id = ?", (pid,))
    p_price, qop_w = db_cursor.fetchone()
    
    if action == "mode":
        qty = int(data[3])
    else:
        change = int(data[3])
        old_qty = int(data[4])
        qty = max(1, old_qty + change)
        
    if unit == "qop":
        total_p = p_price * qty
    else:
        # Misol: 1 qop kepak 85,000 so'm, ichida 25 kg bo'lsa -> 10 kg olinganda: (85000 / 25) * 10 = 34,000 so'm chiqadi!
        per_kg_price = p_price / qop_w if qop_w > 0 else p_price
        total_p = int(per_kg_price * qty)

    markup = generate_counter_keyboard(pid, unit, qty, total_p, qop_w)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_add_to_cart(call):
    _, pid, unit, qty, total_p = call.data.split("_")
    uid = call.message.chat.id
    qty = float(qty)
    total_p = float(total_p)
    
    db_cursor.execute("SELECT quantity, total_calculated_price FROM carts WHERE user_id=? AND product_id=? AND unit=?", (uid, pid, unit))
    row = db_cursor.fetchone()
    if row:
        db_cursor.execute("UPDATE carts SET quantity=?, total_calculated_price=? WHERE user_id=? AND product_id=? AND unit=?",
                          (row[0]+qty, row[1]+total_p, uid, pid, unit))
    else:
        db_cursor.execute("INSERT INTO carts (user_id, product_id, quantity, unit, total_calculated_price) VALUES (?, ?, ?, ?, ?)",
                          (uid, pid, qty, unit, total_p))
    db_conn.commit()
    bot.answer_callback_query(call.id, "✅ Tovar savatga muvaffaqiyatli tushdi!", show_alert=True)

# --- SAVATCHA VA RASMIYLASHTIRISH ---
@bot.message_handler(func=lambda message: message.text == "🛒 Savat")
def view_cart(message):
    uid = message.chat.id
    db_cursor.execute('''SELECT products.name, carts.quantity, carts.unit, carts.total_calculated_price, products.delivery_price 
                         FROM carts JOIN products ON carts.product_id = products.id WHERE carts.user_id = ?''', (uid,))
    items = db_cursor.fetchall()
    if not items:
        bot.send_message(uid, "🛒 Savatchangiz hozircha boʻsh.")
        return
    text = "🛒 **Sizning savatchangiz:**\n\n"
    t_price = 0
    t_delivery = 0
    for item in items:
        name, qty, unit, calculated_p, del_p = item
        t_price += calculated_p
        t_delivery += del_p
        text += f"▪️ {name} — {int(qty) if qty.is_integer() else qty} {unit} = {calculated_p:,} so'm\n"
    
    text += f"\n💰 Tovar summasi: {t_price:,} so'm\n🚚 Dastavka (Chortoq bo'ylab): {t_delivery:,} so'm\n🏆 **Jami To'lov: {t_price+t_delivery:,} so'm**"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Rasmiylashtirish", callback_data="checkout_final"))
    bot.send_message(uid, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "checkout_final")
def checkout_final(call):
    bot.send_message(call.message.chat.id, "✅ Buyurtmangiz qabul qilindi! Dastavka xizmati tez orada siz bilan bog'lanadi.")
    db_cursor.execute("DELETE FROM carts WHERE user_id = ?", (call.message.chat.id,))
    db_conn.commit()
    bot.answer_callback_query(call.id)

# --- ADMIN PANEL (Zanjirli muloqot va barcha eski mantiq to'liq saqlangan) ---
@bot.message_handler(func=lambda message: message.text == "🛠️ Admin Panel" and message.chat.id == ADMIN_ID)
def open_admin(message):
    bot.send_message(ADMIN_ID, "🛠️ Admin panel boʻlimiga xush kelibsiz:", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda message: message.text == "🔙 Asosiy menyu")
def back_main(message):
    bot.send_message(message.chat.id, "Asosiy menyudasiz.", reply_markup=get_main_keyboard(message.chat.id))

@bot.message_handler(func=lambda message: message.text == "➕ Tovar qo'shish" and message.chat.id == ADMIN_ID)
def admin_add_product(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📁 Mavjud guruh ichiga qo'shish", callback_data="a_exist_g"),
               types.InlineKeyboardButton("✨ Yangi guruh yaratish", callback_data="a_new_g"))
    bot.send_message(ADMIN_ID, "Mahsulot guruhini belgilang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "a_new_g")
def adm_new_group(call):
    bot.delete_message(ADMIN_ID, call.message.message_id)
    msg = bot.send_message(ADMIN_ID, "📝 Yangi guruh nomini yozing:")
    bot.register_next_step_handler(msg, save_group_step)

def save_group_step(message):
    db_cursor.execute("INSERT INTO groups (name) VALUES (?)", (message.text,))
    db_conn.commit()
    admin_flow[message.chat.id] = {"g_id": db_cursor.lastrowid}
    ask_photo(message)

@bot.callback_query_handler(func=lambda call: call.data == "a_exist_g")
def adm_exist_group(call):
    db_cursor.execute("SELECT * FROM groups")
    groups = db_cursor.fetchall()
    bot.delete_message(ADMIN_ID, call.message.message_id)
    if not groups:
        msg = bot.send_message(ADMIN_ID, "Bazada hali guruh yo'q, avval yangi guruh nomini kiriting:")
        bot.register_next_step_handler(msg, save_group_step)
        return
    markup = types.InlineKeyboardMarkup()
    for g in groups:
        markup.add(types.InlineKeyboardButton(g[1], callback_data=f"asel_g_{g[0]}"))
    bot.send_message(ADMIN_ID, "Mavjud guruhlardan birini tanlang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("asel_g_"))
def adm_selected_group(call):
    g_id = call.data.split("_")[2]
    admin_flow[call.message.chat.id] = {"g_id": g_id}
    bot.delete_message(ADMIN_ID, call.message.message_id)
    msg = bot.send_message(ADMIN_ID, "🖼 Tovar rasmini yuboring:")
    bot.register_next_step_handler(msg, save_photo_step)

def ask_photo(message):
    msg = bot.send_message(ADMIN_ID, "🖼 Tovar rasmini yuboring:")
    bot.register_next_step_handler(msg, save_photo_step)

def save_photo_step(message):
    if not message.photo:
        msg = bot.send_message(ADMIN_ID, "❌ Rasm aniqlanmadi. Iltimos, tovar rasmini qayta yuboring:")
        bot.register_next_step_handler(msg, save_photo_step)
        return
    admin_flow[message.chat.id]["photo_id"] = message.photo[-1].file_id
    msg = bot.send_message(ADMIN_ID, "📝 Tovar nomini kiriting:")
    bot.register_next_step_handler(msg, save_name_step)

def save_name_step(message):
    admin_flow[message.chat.id]["name"] = message.text
    msg = bot.send_message(ADMIN_ID, "💰 Tovar narxini kiriting (Agar qopda sotilsa 1 qop narxi, kilo bo'lsa 1 kg narxi):")
    bot.register_next_step_handler(msg, save_price_step)

def save_price_step(message):
    try: admin_flow[message.chat.id]["price"] = float(message.text)
    except:
        msg = bot.send_message(ADMIN_ID, "❌ Narxni faqat raqamlarda kiriting:")
        bot.register_next_step_handler(msg, save_price_step)
        return
    msg = bot.send_message(ADMIN_ID, "📦 Qop necha kilo keladi? (Agar aniq bo'lsa raqam bilan yozing, agar qopsiz faqat kilo o'zi bo'lsa 00 deb yozing):")
    bot.register_next_step_handler(msg, save_weight_step)

def save_weight_step(message):
    val = message.text.strip()
    if val == "00":
        weight = 0.0
    else:
        try: weight = float(val)
        except:
            msg = bot.send_message(ADMIN_ID, "❌ Kiloni faqat raqamda kiriting yoki bo'lmasa 00 deb yozing:")
            bot.register_next_step_handler(msg, save_weight_step)
            return
    admin_flow[message.chat.id]["qop_weight"] = weight
    msg = bot.send_message(ADMIN_ID, "📝 Tovar tavsifini (batafsil ma'lumot) yozing:")
    bot.register_next_step_handler(msg, save_desc_step)

def save_desc_step(message):
    admin_flow[message.chat.id]["desc"] = message.text
    msg = bot.send_message(ADMIN_ID, "🚚 Yetkazib berish (dastavka) narxini kiriting:")
    bot.register_next_step_handler(msg, save_delivery_step)

def save_delivery_step(message):
    try: del_price = float(message.text)
    except:
        msg = bot.send_message(ADMIN_ID, "❌ Dastavka narxini raqamda kiriting:")
        bot.register_next_step_handler(msg, save_delivery_step)
        return
    flow = admin_flow[message.chat.id]
    db_cursor.execute('''INSERT INTO products (group_id, photo_id, name, price, qop_weight, description, delivery_price) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (flow["g_id"], flow["photo_id"], flow["name"], flow["price"], flow["qop_weight"], flow["desc"], del_price))
    db_conn.commit()
    bot.send_message(ADMIN_ID, "✅ Tovar muvaffaqiyatli saqlandi va guruh ichiga qo'shildi!", reply_markup=get_admin_keyboard())

# --- BOTNI ISHGA TUSHIRISH ---
def run_bot_polling():
    print("Tulpor Savdo Markazi boti muvaffaqiyatli ishlamoqda...")
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=keep_awake_loop, daemon=True).start()
    threading.Thread(target=run_bot_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
