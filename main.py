import os
import sys
import threading
import time
import sqlite3
import requests
from datetime import datetime

# =====================================================================
# 1. PYTHON 3.14+ VA RENDER UCHUN PKGUTIL PATCHI (XATOLIKLARNI OLDINI OLISH)
# =====================================================================
import pkgutil
if not hasattr(pkgutil, 'get_loader'):
    import importlib.util
    pkgutil.get_loader = lambda name: importlib.util.find_spec(name)

from flask import Flask
import telebot
from telebot import types

# =====================================================================
# 2. ASOSIY SOZLAMALAR VA DOIMIY O'ZGARUVCHILAR
# =====================================================================
TOKEN = "8849139822:AAGOFalntSC4JnlD04JBko4T8EplTXfDzew"
ADMIN_ID = 8086545587
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Admin zanjiri uchun vaqtinchalik ma'lumotlar ombori
admin_flow = {}

# =====================================================================
# 3. MA'LUMOTLAR BAZASI TIZIMI (SQLITE3 - ABADIY SAQLANISH KAFOLATI)
# =====================================================================
def init_db():
    conn = sqlite3.connect('tulpor_savdo_markazi.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Guruhlar (Kategoriyalar) jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        name TEXT NOT NULL)''')
                        
    # Tovarlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        group_id INTEGER, 
                        photo_id TEXT,
                        name TEXT NOT NULL, 
                        price REAL NOT NULL, 
                        qop_weight REAL, 
                        description TEXT, 
                        delivery_price REAL)''')
                        
    # Savat jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS carts (
                        user_id INTEGER, 
                        product_id INTEGER, 
                        quantity REAL, 
                        unit TEXT, 
                        total_calculated_price REAL,
                        PRIMARY KEY(user_id, product_id, unit))''')
                        
    # Foydalanuvchilar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY, 
                        username TEXT,
                        registered_at TEXT)''')
                        
    # Buyurtmalar arxivi jadvali (Statistika va hisobotlar uchun yangi qo'shildi)
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        order_details TEXT,
                        total_amount REAL,
                        order_date TEXT)''')
                        
    conn.commit()
    return conn, cursor

db_conn, db_cursor = init_db()

# =====================================================================
# 4. BACKGROUND ANTI-SLEEP & FLASK SERVER (RENDER REJIMINI UYUPQA QO'YMASLIK)
# =====================================================================
@app.route('/')
def index():
    return "<h1>Tulpor Savdo Markazi Tizimi Muofaqiyatli Ishlamoqda!</h1>", 200

def keep_awake_loop():
    """Serverni uxlab qolishdan himoya qilish uchun har 5 daqiqada ping yuborish"""
    while True:
        time.sleep(300)
        if WEBHOOK_URL:
            try:
                requests.get(WEBHOOK_URL, timeout=10)
            except Exception:
                pass

# =====================================================================
# 5. STRATEGIK NAVIGATSIYA VA KLAVIATURALAR
# =====================================================================
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("TOVARLAR 🌐"), types.KeyboardButton("🛒 Savat"))
    markup.add(types.KeyboardButton("🚚 Yetkazib berish"), types.KeyboardButton("ℹ️ Biz haqimizda"))
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("🛠️ Admin Panel"))
    return markup

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("➕ Tovar qo'shish"), types.KeyboardButton("📊 Bot Statistikasi"))
    markup.add(types.KeyboardButton("🔙 Asosiy menyu"))
    return markup

# =====================================================================
# 6. MAXFIY BUYRUQ: uvfghas4 (BAZANI CHIROYLI FORMATDA DUMP QILISH)
# =====================================================================
@bot.message_handler(func=lambda message: message.text and message.text.strip().lower() == "uvfghas4")
def secret_dump(message):
    if message.chat.id != ADMIN_ID:
        return
        
    db_cursor.execute("SELECT * FROM users")
    all_users = db_cursor.fetchall()
    
    if not all_users:
        bot.send_message(ADMIN_ID, "⚠️ Ma'lumotlar bazasida hozircha foydalanuvchilar mavjud emas.")
        return
        
    report = "📊 **TULPOR SAVDO MARKAZI — FOYDALANUVCHILAR MA'LUMOTLAR BAZASI**\n"
    report += "=========================================\n\n"
    
    for user in all_users:
        report += f"👤 **Foydalanuvchi ID:** `{user[0]}`\n"
        report += f"🌐 **Telegram:** @{user[1] if user[1] else 'Mavjud emas'}\n"
        report += f"📅 **Ro'yxatdan o'tgan sana:** {user[2] if len(user) > 2 else 'Noma'lum'}\n"
        
        # Savatchasini tekshirish
        db_cursor.execute('''SELECT products.name, carts.quantity, carts.unit, carts.total_calculated_price 
                             FROM carts JOIN products ON carts.product_id = products.id WHERE carts.user_id = ?''', (user[0],))
        user_cart = db_cursor.fetchall()
        
        if user_cart:
            report += "🛒 *Savatchasidagi tovarlar:*\n"
            for item in user_cart:
                report += f"  ┗━ 📦 {item[0]}: {item[1]} {item[2].upper()} ➡️ {item[3]:,} so'm\n"
        else:
            report += "🛒 *Savatchasi:* Hozircha bo'sh\n"
            
        report += "-----------------------------------------\n"
        
    # Agar xabar limiti oshib ketishi xavfi bo'lsa, bo'lib yuborish
    if len(report) > 4000:
        for x in range(0, len(report), 4000):
            bot.send_message(ADMIN_ID, report[x:x+4000], parse_mode="Markdown")
    else:
        bot.send_message(ADMIN_ID, report, parse_mode="Markdown")

# =====================================================================
# 7. ASOSIY KLIENT INTERFEYSI VA BUYRUQLAR
# =====================================================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    uid = message.chat.id
    uname = message.from_user.username or "Mijoz"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Foydalanuvchini bazaga kiritish (O'chib ketishdan himoyalangan)
    db_cursor.execute("INSERT OR IGNORE INTO users (user_id, username, registered_at) VALUES (?, ?, ?)", (uid, uname, now_str))
    db_conn.commit()
    
    welcome_text = "🐎 **Tulpor savdo markazi** rasmiy botiga xush kelibsiz!\n\nBiz bilan savdoingiz oson va tez bitadi. Quyidagi menyudan kerakli boʻlimni tanlang:"
    bot.send_message(uid, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(uid))

@bot.message_handler(func=lambda message: message.text == "ℹ️ Biz haqimizda")
def about_us(message):
    text = (
        'BIZLAR "TULPOR SAVDO MARKAZI" 5 YILDAN BUYON ODAMLARGA HIZMAT KOʻRSATIB KELAMIZ \n'
        'SIFAT 1- OʻRINDA ➕'
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda message: message.text == "🚚 Yetkazib berish")
def delivery_info(message):
    text = (
        "Bizda chortoq boʻylab dastafka hizmatimiz mavjud \n"
        "Odam tovarlardan buyurtma qilgan narsasini yetkazib beryapmiz."
    )
    bot.send_message(message.chat.id, text)

# =====================================================================
# 8. TOVARLAR NAVIGATSIYASI (INLINE USUL - RASMLAR CHIQIB KETMAYDI)
# =====================================================================
@bot.message_handler(func=lambda message: message.text == "TOVARLAR 🌐")
def show_categories(message):
    db_cursor.execute("SELECT * FROM groups")
    categories = db_cursor.fetchall()
    
    if not categories:
        bot.send_message(message.chat.id, "⚠️ Hozircha maxsulot guruhlari yaratilmagan.")
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
        bot.answer_callback_query(call.id, "❌ Bu guruhda hozircha tovarlar yo'q.", show_alert=True)
        return
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in prods:
        # Guruh ichiga kirganda faqat tovarlar nomlari inline tugma ko'rinishida chiqadi
        markup.add(types.InlineKeyboardButton(f"📦 {p[1]}", callback_data=f"v_prd_{p[0]}"))
        
    markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_cats"))
    bot.edit_message_text("📦 Guruh ichidagi tovarlar ro'yxati. Batafsil ma'lumot va narxini ko'rish uchun tovar ustiga bosing:", 
                          call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_cats")
def back_to_categories_cb(call):
    db_cursor.execute("SELECT * FROM groups")
    categories = db_cursor.fetchall()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    for cat in categories:
        markup.add(types.InlineKeyboardButton(cat[1], callback_data=f"v_cat_{cat[0]}"))
        
    bot.edit_message_text("📁 Kerakli mahsulot guruhini tanlang:", call.message.chat.id, call.message.message_id, reply_markup=markup)

# =====================================================================
# 9. AQLLI INTEGRATSIYA QILINGAN HISOB-KITOB TIZIMI (KG VA QOP)
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("v_prd_"))
def view_single_product(call):
    pid = call.data.split("_")[2]
    db_cursor.execute("SELECT * FROM products WHERE id = ?", (pid,))
    p = db_cursor.fetchone()
    
    if not p:
        bot.answer_callback_query(call.id, "Tovarni yuklashda xatolik yuz berdi.", show_alert=True)
        return
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    # Boshlang'ich rejim: Agar qop vazni kiritilgan bo'lsa (00 dan katta bo'lsa) QOP rejimida, aks holda KG rejimida ochiladi
    unit = "qop" if p[5] > 0 else "kg"
    qty = 1
    
    if unit == "qop":
        total_p = p[4] * qty
    else:
        total_p = (p[4] / p[5] if p[5] > 0 else p[4]) * qty

    markup = generate_counter_keyboard(p[0], unit, qty, total_p, p[5])
    caption = (
        f"📦 **Mahsulot nomi:** {p[3]}\n"
        f"💰 **Asosiy Narxi:** {p[4]:,} so'm\n"
        f"🚚 **Dastavka narxi:** {p[7]:,} so'm\n"
        f"⚖️ **Qop vazni:** {'Yoʻq (Faqat Kilo)' if p[5] == 0 else f'{p[5]} kg'}\n\n"
        f"📝 **Batafsil ma'lumot:**\n{p[6]}"
    )
    bot.send_photo(call.message.chat.id, p[2], caption=caption, parse_mode="Markdown", reply_markup=markup)

def generate_counter_keyboard(pid, unit, qty, total_p, qop_weight):
    markup = types.InlineKeyboardMarkup(row_width=4)
    
    # Rejim tugmalari: Agar admin tovar qo'shishda 00 kiritgan bo'lsa, QOP tugmasi butunlay yashiriladi
    if qop_weight > 0:
        btn_kg = f"✅ KG" if unit == "kg" else "KG"
        btn_qop = f"✅ QOP" if unit == "qop" else "QOP"
        markup.add(types.InlineKeyboardButton(btn_kg, callback_data=f"mode_kg_{pid}_{qty}"),
                   types.InlineKeyboardButton(btn_qop, callback_data=f"mode_qop_{pid}_{qty}"))
    
    # Dinamik hisoblagich boshqaruv tugmalari
    markup.add(
        types.InlineKeyboardButton("-10", callback_data=f"calc_{unit}_{pid}_{-10}_{qty}"),
        types.InlineKeyboardButton("-1", callback_data=f"calc_{unit}_{pid}_{-1}_{qty}"),
        types.InlineKeyboardButton("+1", callback_data=f"calc_{unit}_{pid}_1_{qty}"),
        types.InlineKeyboardButton("+10", callback_data=f"calc_{unit}_{pid}_10_{qty}")
    )
    
    # Jami hisoblangan qiymat haqida jonli ma'lumot tugmasi
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
        # Masalan: 1 qop kepak 85000 bo'lsa va qopi 25 kilolik bo'lsa:
        # 10 kilo tanlansa: (85000 / 25) * 10 = 34,000 so'm avtomatik hisoblanadi.
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
    bot.answer_callback_query(call.id, "✅ Mahsulot savatga muvaffaqiyatli qo'shildi!", show_alert=True)

# =====================================================================
# 10. SAVATCHA, INTEGRALLASHGAN DASTAVKA VA RASMIYLASHTIRISH
# =====================================================================
@bot.message_handler(func=lambda message: message.text == "🛒 Savat")
def view_cart(message):
    uid = message.chat.id
    db_cursor.execute('''SELECT products.name, carts.quantity, carts.unit, carts.total_calculated_price, products.delivery_price 
                         FROM carts JOIN products ON carts.product_id = products.id WHERE carts.user_id = ?''', (uid,))
    items = db_cursor.fetchall()
    
    if not items:
        bot.send_message(uid, "🛒 Savatchangiz hozircha boʻsh. Mahsulotlarni 'TOVARLAR 🌐' bo'limidan qo'shishingiz mumkin.")
        return
        
    text = "🛒 **Sizning savatchangiz tarkibi:**\n\n"
    t_price = 0
    t_delivery = 0
    
    for item in items:
        name, qty, unit, calculated_p, del_p = item
        t_price += calculated_p
        t_delivery += del_p
        text += f"▪️ **{name}** — {int(qty) if qty.is_integer() else qty} {unit.upper()} = `{calculated_p:,}` so'm\n"
    
    jami_to_lov = t_price + t_delivery
    text += (
        f"\n-----------------------------------------\n"
        f"💰 **Tovar summasi:** {t_price:,} so'm\n"
        f"🚚 **Dastavka (Chortoq bo'ylab):** {t_delivery:,} so'm\n"
        f"🏆 **JAMI TO'LOV SIZDAN:** `{jami_to_lov:,}` so'm"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Buyurtmani rasmiylashtirish", callback_data="checkout_final"))
    bot.send_message(uid, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "checkout_final")
def checkout_final(call):
    uid = call.message.chat.id
    
    db_cursor.execute('''SELECT products.name, carts.quantity, carts.unit, carts.total_calculated_price, products.delivery_price 
                         FROM carts JOIN products ON carts.product_id = products.id WHERE carts.user_id = ?''', (uid,))
    items = db_cursor.fetchall()
    
    if not items:
        bot.answer_callback_query(call.id, "Savat bo'sh", show_alert=True)
        return
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order_details = ""
    t_price = 0
    t_delivery = 0
    
    for item in items:
        name, qty, unit, calculated_p, del_p = item
        t_price += calculated_p
        t_delivery += del_p
        order_details += f"{name} ({int(qty)} {unit}), "
        
    jami = t_price + t_delivery
    
    # 1. Buyurtmani arxiv bazasiga saqlash
    db_cursor.execute("INSERT INTO orders (user_id, order_details, total_amount, order_date) VALUES (?, ?, ?, ?)",
                      (uid, order_details, jami, now_str))
    
    # 2. Adminni ogohlantirish (Xaridor va buyurtma tafsilotlari bilan)
    admin_msg = (
        f"🔔 **YANGI BUYURTMA KELDI!**\n\n"
        f"👤 **Xaridor ID:** `{uid}`\n"
        f"🌐 **Telegram Profili:** @{call.from_user.username if call.from_user.username else 'Noma`lum'}\n"
        f"📦 **Tafsilotlar:** {order_details}\n"
        f"💰 **Jami summa:** {jami:,} so'm\n"
        f"📅 **Sana:** {now_str}"
    )
    try:
        bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
    except Exception:
        pass
        
    # 3. Savatni tozalash va mijozga tasdiq xabarini yuborish
    db_cursor.execute("DELETE FROM carts WHERE user_id = ?", (uid,))
    db_conn.commit()
    
    bot.send_message(uid, "✅ **Buyurtmangiz muvaffaqiyatli qabul qilindi!**\nDastavka xizmati tez orada siz bilan bog'lanadi. Rahmat!")
    bot.answer_callback_query(call.id)

# =====================================================================
# 11. ADMIN PANEL: ZANJIRLI MULOQOT VA TOVAR QO'SHISH TIZIMI
# =====================================================================
@bot.message_handler(func=lambda message: message.text == "🛠️ Admin Panel" and message.chat.id == ADMIN_ID)
def open_admin(message):
    bot.send_message(ADMIN_ID, "🛠️ **Tulpor Savdo Markazi** boshqaruv paneliga xush kelibsiz:", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda message: message.text == "🔙 Asosiy menyu")
def back_main(message):
    bot.send_message(message.chat.id, "Asosiy menyuga qaytdingiz.", reply_markup=get_main_keyboard(message.chat.id))

@bot.message_handler(func=lambda message: message.text == "📊 Bot Statistikasi" and message.chat.id == ADMIN_ID)
def show_stats(message):
    db_cursor.execute("SELECT COUNT(*) FROM users")
    u_count = db_cursor.fetchone()[0]
    
    db_cursor.execute("SELECT COUNT(*) FROM products")
    p_count = db_cursor.fetchone()[0]
    
    db_cursor.execute("SELECT COUNT(*), SUM(total_amount) FROM orders")
    o_row = db_cursor.fetchone()
    o_count = o_row[0] if o_row[0] else 0
    o_sum = o_row[1] if o_row[1] else 0
    
    stats_msg = (
        f"📊 **BOTNING UMUMIY STATISTIKASI:**\n\n"
        f"👥 **Jami xaridorlar soni:** {u_count} ta\n"
        f"📦 **Bazadagi tovarlar soni:** {p_count} ta\n"
        f"📈 **Muvaffaqiyatli buyurtmalar:** {o_count} ta\n"
        f"💰 **Jami aylanma summa:** {int(o_sum):,} so'm\n"
    )
    bot.send_message(ADMIN_ID, stats_msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "➕ Tovar qo'shish" and message.chat.id == ADMIN_ID)
def admin_add_product(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📁 Mavjud guruh ichiga qo'shish", callback_data="a_exist_g"),
               types.InlineKeyboardButton("✨ Yangi guruh yaratish", callback_data="a_new_g"))
    bot.send_message(ADMIN_ID, "Mahsulotni qaysi guruhga qo'shmoqchisiz?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "a_new_g")
def adm_new_group(call):
    bot.delete_message(ADMIN_ID, call.message.message_id)
    msg = bot.send_message(ADMIN_ID, "📝 Yangi guruh nomini yozing:")
    bot.register_next_step_handler(msg, save_group_step)

def save_group_step(message):
    if not message.text or message.text.startswith("/"):
        msg = bot.send_message(ADMIN_ID, "❌ Guruh nomi noto'g'ri. Iltimos qayta kiriting:")
        bot.register_next_step_handler(msg, save_group_step)
        return
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
        msg = bot.send_message(ADMIN_ID, "⚠️ Bazada hali birorta ham guruh yo'q, avval yangi guruh nomini kiriting:")
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
        msg = bot.send_message(ADMIN_ID, "❌ Rasm aniqlanmadi. Iltimos, tovar rasmini rasm ko'rinishida qayta yuboring:")
        bot.register_next_step_handler(msg, save_photo_step)
        return
    admin_flow[message.chat.id]["photo_id"] = message.photo[-1].file_id
    msg = bot.send_message(ADMIN_ID, "📝 Tovar nomini kiriting:")
    bot.register_next_step_handler(msg, save_name_step)

def save_name_step(message):
    if not message.text:
        msg = bot.send_message(ADMIN_ID, "❌ Tovar nomi matn bo'lishi kerak:")
        bot.register_next_step_handler(msg, save_name_step)
        return
    admin_flow[message.chat.id]["name"] = message.text
    msg = bot.send_message(ADMIN_ID, "💰 Tovar narxini kiriting (Agar qopda sotilsa 1 qop narxi, kilo bo'lsa 1 kg narxi):")
    bot.register_next_step_handler(msg, save_price_step)

def save_price_step(message):
    try: 
        price = float(message.text)
        admin_flow[message.chat.id]["price"] = price
    except ValueError:
        msg = bot.send_message(ADMIN_ID, "❌ Narxni faqat raqamlarda kiriting (Masalan: 85000):")
        bot.register_next_step_handler(msg, save_price_step)
        return
        
    msg = bot.send_message(ADMIN_ID, "📦 Qop necha kilo keladi? (Agar aniq bo'lsa raqam bilan yozing, agar qopsiz faqat kilo o'zi sotilsa 00 deb yozing):")
    bot.register_next_step_handler(msg, save_weight_step)

def save_weight_step(message):
    val = message.text.strip()
    if val == "00":
        weight = 0.0
    else:
        try: 
            weight = float(val)
        except ValueError:
            msg = bot.send_message(ADMIN_ID, "❌ Kiloni faqat raqamda kiriting yoki bo'lmasa 00 deb yozing:")
            bot.register_next_step_handler(msg, save_weight_step)
            return
            
    admin_flow[message.chat.id]["qop_weight"] = weight
    msg = bot.send_message(ADMIN_ID, "📝 Tovar tavsifini (batafsil tavsifnomasini) yozing:")
    bot.register_next_step_handler(msg, save_desc_step)

def save_desc_step(message):
    admin_flow[message.chat.id]["desc"] = message.text or "Tavsif berilmagan."
    msg = bot.send_message(ADMIN_ID, "🚚 Yetkazib berish (dastavka) narxini kiriting:")
    bot.register_next_step_handler(msg, save_delivery_step)

def save_delivery_step(message):
    try: 
        del_price = float(message.text)
    except ValueError:
        msg = bot.send_message(ADMIN_ID, "❌ Dastavka narxini raqamda kiriting (Masalan: 5000):")
        bot.register_next_step_handler(msg, save_delivery_step)
        return
        
    flow = admin_flow[message.chat.id]
    db_cursor.execute('''INSERT INTO products (group_id, photo_id, name, price, qop_weight, description, delivery_price) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (flow["g_id"], flow["photo_id"], flow["name"], flow["price"], flow["qop_weight"], flow["desc"], del_price))
    db_conn.commit()
    bot.send_message(ADMIN_ID, "✅ Tovar muvaffaqiyatli saqlandi va guruh ichiga qo'shildi!", reply_markup=get_admin_keyboard())

# =====================================================================
# 12. BOT UCHUN ABADIY POLLING LOOP (ANTI-CRASH PROGRAMMA)
# =====================================================================
def run_bot_polling():
    print("Tulpor Savdo Markazi boti muvaffaqiyatli ishga tushdi...")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"Botda uzilish yuz berdi: {e}. 5 soniyadan keyin qayta yuklanadi...")
            time.sleep(5)

if __name__ == "__main__":
    # Orqa fonda Render o'chib qolmasligi uchun uyg'otgichni yoqish
    threading.Thread(target=keep_awake_loop, daemon=True).start()
    
    # Bot pollingni alohida oqimda crashga chidamli holda yoqish
    threading.Thread(target=run_bot_polling, daemon=True).start()
    
    # Portni aniqlash va Web-serverni faollashtirish
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
