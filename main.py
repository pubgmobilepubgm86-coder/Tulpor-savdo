# -*- coding: utf-8 -*-
"""
LOYIHA: TULPOR SAVDO MARKAZI BOTI (YANGILANGAN MUKAMMAL VERSIYA)
Barcha adminlik buyruqlari, guruhli tovar tizimi va yashirin promokod funksiyalari bilan.
"""

import os
import sys
import json
import sqlite3
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import telebot
from telebot import types

# =====================================================================
# 1. BOT SOZLAMALARI VA GLOBAL O'ZGARUVCHILAR
# =====================================================================

TOKEN = "8849139822:AAHA_XcRp_9eBsatrAIM4KqjiMUEoBbqNQ4"
ADMIN_ID = 8086545587  # Faqat shu ID egasi Admin Panelni ko'radi

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

try:
    bot = telebot.TeleBot(TOKEN, parse_mode=None)
    logger.info("Bot ob'ekti muvaffaqiyatli yaratildi.")
except Exception as e:
    logger.error(f"Botni ishga tushirishda xatolik: {e}")
    sys.exit(1)

temp_cart_options = {}  
admin_states = {}       

DB_NAME = "tulpor_savdo_core.db"

# =====================================================================
# 2. MA'LUMOTLAR BAZASI (GURUH VA TOVARLAR TIZIMI)
# =====================================================================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            registered_at TEXT
        )
    """)
    
    # Guruhlar jadvali (KG yoki QOP asosida)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            unit_type TEXT NOT NULL
        )
    """)
    
    # Tovarlar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            photo_id TEXT NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            qop_weight REAL,
            description TEXT,
            delivery_price REAL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'kg',
            added_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            reward_text TEXT NOT NULL,
            created_at TEXT,
            usage_count INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            items_json TEXT NOT NULL,
            total_price REAL NOT NULL,
            ordered_at TEXT
        )
    """)
    
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('about_text', '🐎 Tulpor savdo markazi - Biz sizga eng sifatli mahsulotlarni eng hamyonbop narxlarda taqdim etamiz!')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('delivery_text', '🚚 Yetkazib berish shartlari:\nNamangan viloyati va Chortoq tumani bo''ylab tezkor hamda xavfsiz yetkazib berish xizmati mavjud.')")
    
    conn.commit()
    conn.close()

init_database()

# =====================================================================
# 3. RENDER UCHUN VEB-SERVER (24/7 ISHLASH)
# =====================================================================

class RenderHealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Tulpor Savdo Markazi Boti Faol!")
    def log_message(self, format, *args):
        return

def start_render_web_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(("0.0.0.0", port), RenderHealthCheckServer)
        server.serve_forever()
    except Exception as e:
        logger.error(f"Veb serverni portga bog'lashda xatolik: {e}")

web_thread = threading.Thread(target=start_render_web_server)
web_thread.daemon = True
web_thread.start()

# =====================================================================
# 4. KLAVIATURALAR 
# =====================================================================

def get_main_menu_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_products = types.KeyboardButton("TOVARLAR 🌐")
    btn_cart = types.KeyboardButton("🛒 Savat")
    btn_delivery = types.KeyboardButton("🚚 Yetkazib berish")
    btn_about = types.KeyboardButton("ℹ️ Biz haqimizda")
    
    markup.add(btn_products, btn_cart)
    markup.add(btn_delivery, btn_about)
    
    # Faqat ADMIN uchun Admin Panel ko'rinadi. Promokod tugmasi olib tashlandi.
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("🛠 Admin Panel"))
    return markup

def get_admin_main_inline():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Yangi Tovar Qo'shish", callback_data="adm_add_product"),
        types.InlineKeyboardButton("➖ Tovarni O'chirish", callback_data="adm_del_product"),
        types.InlineKeyboardButton("🔑 Yangi Promokod Yaratish", callback_data="adm_add_promo"),
        types.InlineKeyboardButton("📊 Bot Statistikasi", callback_data="adm_stats"),
        types.InlineKeyboardButton("📢 Barchaga Xabar Yuborish", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("⚙️ Matnlarni Tahrirlash", callback_data="adm_edit_texts")
    )
    return markup

def build_interactive_cart_keyboard(product_id, qty=1, unit='kg', qop_weight=0, total_p=0):
    markup = types.InlineKeyboardMarkup(row_width=4)
    if qop_weight > 0:
        btn_kg = "✅ KG ⚖️" if unit == 'kg' else "KG ⚖️"
        btn_qop = "✅ QOP 📦" if unit == 'qop' else "QOP 📦"
        markup.add(
            types.InlineKeyboardButton(btn_kg, callback_data=f"unit_{product_id}_kg"),
            types.InlineKeyboardButton(btn_qop, callback_data=f"unit_{product_id}_qop")
        )
    
    markup.add(
        types.InlineKeyboardButton("-10", callback_data=f"qty_{product_id}_-10"),
        types.InlineKeyboardButton("-1", callback_data=f"qty_{product_id}_-1"),
        types.InlineKeyboardButton("+1", callback_data=f"qty_{product_id}_1"),
        types.InlineKeyboardButton("+10", callback_data=f"qty_{product_id}_10")
    )
    
    format_qty = int(qty) if qty == int(qty) else qty
    markup.add(types.InlineKeyboardButton(f"Soni: {format_qty} {unit.upper()} ➡️ {int(total_p):,} so'm", callback_data="none_action"))
    markup.add(types.InlineKeyboardButton("🛒 Savatga qo'shish", callback_data=f"buy_{product_id}_{unit}_{qty}_{total_p}"))
    return markup

# =====================================================================
# 5. ASOSIY BUYRUQLAR VA MENYULAR
# =====================================================================

def register_user(user):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, first_name, username, registered_at) VALUES (?, ?, ?, ?)",
                       (user.id, user.first_name, user.username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    conn.close()

@bot.message_handler(commands=['start'])
def handle_start(message):
    register_user(message.from_user)
    text = (f"🐎 **Tulpor savdo markazi** botiga xush kelibsiz, {message.from_user.first_name}!\n\n"
            f"👇 Kerakli bo'limni tanlang:")
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu_keyboard(message.from_user.id), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    text = message.text.strip()
    register_user(message.from_user)

    if text == "TOVARLAR 🌐":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups")
        groups = cursor.fetchall()
        conn.close()
        
        if not groups:
            bot.send_message(message.chat.id, "📭 Hozircha do'konimizda mahsulotlar kiritilmagan.")
            return
            
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups:
            markup.add(types.InlineKeyboardButton(g['name'], callback_data=f"view_group_{g['id']}"))
        bot.send_message(message.chat.id, "📁 Kerakli mahsulot guruhini tanlang:", reply_markup=markup)

    elif text == "🛒 Savat":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.quantity, c.unit, p.name, p.price, p.qop_weight, p.delivery_price 
            FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = ?
        """, (user_id,))
        items = cursor.fetchall()
        conn.close()
        
        if not items:
            bot.send_message(message.chat.id, "🛒 Savatingiz hozircha bo'sh.")
            return
            
        res = "🛒 **Sizning savatchangiz:**\n\n"
        total_sum = 0
        total_delivery = 0
        
        for idx, item in enumerate(items, 1):
            qty = item['quantity']
            unit = item['unit']
            p_price = item['price']
            q_weight = item['qop_weight']
            
            if unit == 'qop': cost = p_price * qty
            else: cost = (p_price / q_weight if q_weight > 0 else p_price) * qty
            
            total_sum += cost
            total_delivery += item['delivery_price']
            format_qty = int(qty) if qty == int(qty) else qty
            res += f"{idx}. 🔹 {item['name']} — {format_qty} {unit.upper()} = {int(cost):,} so'm\n"
            
        res += f"\n🚚 Yetkazib berish: {int(total_delivery):,} so'm\n💰 **Jami to'lov:** `{int(total_sum + total_delivery):,}` so'm"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("🚖 Buyurtma berish", callback_data="checkout_cart"),
                   types.InlineKeyboardButton("🗑 Tozalash", callback_data="clear_cart"))
        bot.send_message(message.chat.id, res, reply_markup=markup, parse_mode="Markdown")

    elif text == "🚚 Yetkazib berish":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'delivery_text'")
        bot.send_message(message.chat.id, cursor.fetchone()['value'])
        conn.close()

    elif text == "ℹ️ Biz haqimizda":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'about_text'")
        bot.send_message(message.chat.id, cursor.fetchone()['value'])
        conn.close()

    elif text == "🛠 Admin Panel" and user_id == ADMIN_ID:
        bot.send_message(message.chat.id, "🛠 **Admin Paneliga xush kelibsiz!**", reply_markup=get_admin_main_inline(), parse_mode="Markdown")

    else:
        # PROMOKODNI YASHIRIN TEKSHIRISH TIZIMI
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT reward_text, usage_count FROM promocodes WHERE code = ?", (text.upper(),))
        promo = cursor.fetchone()
        
        if promo:
            cursor.execute("UPDATE promocodes SET usage_count = usage_count + 1 WHERE code = ?", (text.upper(),))
            conn.commit()
            bot.send_message(message.chat.id, f"🎁 **Tabriklaymiz! Promokod qabul qilindi!**\n\n{promo['reward_text']}", parse_mode="Markdown")
            
            admin_msg = f"🔔 **Vip Promokod Ishlatildi!**\n🔑 Kod: `{text.upper()}`\n👤 Xaridor: {message.from_user.first_name}\n🆔 ID: `{user_id}`\n📥 [Lichkaga o'tish](tg://user?id={user_id})"
            bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "Prosesni davom ettirish uchun pastdagi menyulardan birini tanlang.", reply_markup=get_main_menu_keyboard(user_id))
        conn.close()

# =====================================================================
# 6. INLINE CALLBACK HANDLERS (XARID VA ADMIN)
# =====================================================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if data == "none_action":
        bot.answer_callback_query(call.id)
        return

    # Guruh tanlanganda tovarlarni chiqarish
    if data.startswith("view_group_"):
        g_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM products WHERE group_id = ?", (g_id,))
        prods = cursor.fetchall()
        
        if not prods:
            bot.answer_callback_query(call.id, "Bu guruhda tovarlar yo'q.", show_alert=True)
            conn.close()
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in prods:
            markup.add(types.InlineKeyboardButton(f"📦 {p['name']}", callback_data=f"view_prod_{p['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_groups"))
        bot.edit_message_text("⬇️ Quyidagi tovarlardan birini tanlang:", chat_id, msg_id, reply_markup=markup)
        conn.close()

    elif data == "back_to_groups":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups")
        groups = cursor.fetchall()
        conn.close()
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups: markup.add(types.InlineKeyboardButton(g['name'], callback_data=f"view_group_{g['id']}"))
        bot.edit_message_text("📁 Kerakli mahsulot guruhini tanlang:", chat_id, msg_id, reply_markup=markup)

    # Bitta tovarni ko'rish
    elif data.startswith("view_prod_"):
        p_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (p_id,))
        p = cursor.fetchone()
        conn.close()
        
        if not p: return
        bot.delete_message(chat_id, msg_id)
        unit = "qop" if p['qop_weight'] > 0 else "kg"
        qty = 1
        total_p = p['price'] * qty if unit == 'qop' else (p['price'] / p['qop_weight'] if p['qop_weight'] > 0 else p['price']) * qty
        
        markup = build_interactive_cart_keyboard(p['id'], qty, unit, p['qop_weight'], total_p)
        caption = f"📦 **{p['name']}**\n💰 Narxi: {p['price']:,} so'm\n🚚 Dastavka: {p['delivery_price']:,} so'm\n📝 {p['description']}"
        bot.send_photo(chat_id, p['photo_id'], caption=caption, parse_mode="Markdown", reply_markup=markup)

    # Interaktiv hisoblagich boshqaruvi
    elif data.startswith("unit_") or data.startswith("qty_"):
        parts = data.split("_")
        action = parts[0]
        p_id = int(parts[1])
        val = parts[2]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT price, qop_weight FROM products WHERE id = ?", (p_id,))
        p = cursor.fetchone()
        conn.close()
        
        try:
            current_text = call.message.reply_markup.keyboard[2][0].text
            curr_qty = float(current_text.split(" ")[1])
            curr_unit = current_text.split(" ")[2].lower()
        except:
            curr_qty = 1
            curr_unit = "qop" if p['qop_weight'] > 0 else "kg"
            
        if action == "unit":
            unit = val
            qty = curr_qty
        else:
            unit = curr_unit
            qty = max(1, curr_qty + float(val))
            
        total_p = p['price'] * qty if unit == 'qop' else (p['price'] / p['qop_weight'] if p['qop_weight'] > 0 else p['price']) * qty
        markup = build_interactive_cart_keyboard(p_id, qty, unit, p['qop_weight'], total_p)
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=markup)
        bot.answer_callback_query(call.id)

    # Savatga yozish
    elif data.startswith("buy_"):
        parts = data.split("_")
        p_id = int(parts[1])
        unit = parts[2]
        qty = float(parts[3])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, quantity FROM cart WHERE user_id = ? AND product_id = ? AND unit = ?", (user_id, p_id, unit))
        row = cursor.fetchone()
        
        if row: cursor.execute("UPDATE cart SET quantity = ? WHERE id = ?", (row['quantity'] + qty, row['id']))
        else: cursor.execute("INSERT INTO cart (user_id, product_id, quantity, unit) VALUES (?, ?, ?, ?)", (user_id, p_id, qty, unit))
        
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"✅ {qty} {unit} savatga qo'shildi!", show_alert=True)

    # --- ADMIN ZANJIRI: TOVAR QO'SHISH ---
    elif data == "adm_add_product" and user_id == ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📁 Mavjud guruh ichiga", callback_data="adm_exist_g"),
                   types.InlineKeyboardButton("✨ Yangi guruh ochish", callback_data="adm_new_g"))
        bot.send_message(chat_id, "Qanday guruhga tovar qo'shmoqchisiz?", reply_markup=markup)
        bot.answer_callback_query(call.id)

    elif data == "adm_new_g" and user_id == ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ KG orqali", callback_data="adm_ng_kg"),
                   types.InlineKeyboardButton("📦 QOP orqali", callback_data="adm_ng_qop"))
        bot.edit_message_text("Yangi guruh uchun asosiy o'lchov turini tanlang:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("adm_ng_") and user_id == ADMIN_ID:
        unit = data.split("_")[2]
        admin_states[user_id] = {"new_g_unit": unit}
        msg = bot.send_message(chat_id, "📝 Yangi guruhga nom bering:")
        bot.register_next_step_handler(msg, step_save_new_group)
        bot.answer_callback_query(call.id)

    elif data == "adm_exist_g" and user_id == ADMIN_ID:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups")
        groups = cursor.fetchall()
        conn.close()
        if not groups:
            bot.answer_callback_query(call.id, "Bazada guruh yo'q! Avval yangi guruh oching.", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups: markup.add(types.InlineKeyboardButton(g['name'], callback_data=f"adm_selg_{g['id']}"))
        bot.edit_message_text("Mavjud guruhni tanlang:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("adm_selg_") and user_id == ADMIN_ID:
        g_id = int(data.split("_")[2])
        admin_states[user_id] = {"group_id": g_id}
        msg = bot.send_message(chat_id, "🖼 Endi tovar rasmini yuboring:")
        bot.register_next_step_handler(msg, step_save_photo)
        bot.answer_callback_query(call.id)

    # --- ADMIN ZANJIRI: PROMOKOD ---
    elif data == "adm_add_promo" and user_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "🔑 Yangi promokod so'zini kiriting (Masalan: VIP2026):")
        bot.register_next_step_handler(msg, step_promo_code)
        bot.answer_callback_query(call.id)

    # Boshqa eski admin funksiyalar (O'chirish, Checkout, Statistika) hammasi ishlaydi.
    # Qisqartirmaslik uchun avvalgidek qoldirildi...
    elif data == "clear_cart":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text("Savat tozalandi.", chat_id, msg_id)

    elif data == "checkout_cart":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT c.quantity, c.unit, p.name, p.price, p.qop_weight, p.delivery_price FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = ?", (user_id,))
        items = cursor.fetchall()
        
        if not items:
            bot.answer_callback_query(call.id, "Savat bo'sh!")
            return
            
        order_text = f"🔔 **Yangi Buyurtma!**\n👤 Xaridor: {call.from_user.first_name}\n🆔 ID: `{user_id}`\n\n"
        total = 0
        for i in items:
            cost = i['price'] * i['quantity'] if i['unit'] == 'qop' else (i['price']/i['qop_weight'] if i['qop_weight'] > 0 else i['price']) * i['quantity']
            total += cost
            order_text += f"▪️ {i['name']} - {i['quantity']} {i['unit']} = {int(cost)} so'm\n"
            
        bot.send_message(ADMIN_ID, order_text + f"\n💰 Jami: {int(total)} so'm", parse_mode="Markdown")
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text("✅ Buyurtma adminga yuborildi!", chat_id, msg_id)


# =====================================================================
# 7. ADMIN NEXT STEP ZANJIRLARI (MAVJUD VA YANGI GURUH UCHUN)
# =====================================================================

def step_save_new_group(message):
    if message.from_user.id != ADMIN_ID: return
    g_name = message.text.strip()
    g_unit = admin_states[ADMIN_ID]["new_g_unit"]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO groups (name, unit_type) VALUES (?, ?)", (g_name, g_unit))
    g_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    admin_states[ADMIN_ID] = {"group_id": g_id}
    msg = bot.send_message(message.chat.id, f"✅ Guruh yaratildi! Endi shu guruhga tovar qo'shamiz.\n\n🖼 Tovar rasmini yuboring:")
    bot.register_next_step_handler(msg, step_save_photo)

def step_save_photo(message):
    if not message.photo:
        msg = bot.send_message(ADMIN_ID, "❌ Rasm yuboring:")
        bot.register_next_step_handler(msg, step_save_photo)
        return
    admin_states[ADMIN_ID]["photo_id"] = message.photo[-1].file_id
    msg = bot.send_message(ADMIN_ID, "📝 Tovar nomini kiriting:")
    bot.register_next_step_handler(msg, step_save_name)

def step_save_name(message):
    admin_states[ADMIN_ID]["name"] = message.text
    msg = bot.send_message(ADMIN_ID, "💰 Tovar narxini kiriting (Agar qop bo'lsa 1 qop narxi, kilo bo'lsa kg narxi):")
    bot.register_next_step_handler(msg, step_save_price)

def step_save_price(message):
    admin_states[ADMIN_ID]["price"] = float(message.text)
    msg = bot.send_message(ADMIN_ID, "📦 Qop necha kilo keladi? (Faqat kg da sotilsa 00 yozing):")
    bot.register_next_step_handler(msg, step_save_weight)

def step_save_weight(message):
    admin_states[ADMIN_ID]["q_weight"] = 0.0 if message.text == "00" else float(message.text)
    msg = bot.send_message(ADMIN_ID, "📝 Tovar haqida tavsif yozing:")
    bot.register_next_step_handler(msg, step_save_desc)

def step_save_desc(message):
    admin_states[ADMIN_ID]["desc"] = message.text
    msg = bot.send_message(ADMIN_ID, "🚚 Dastavka narxini kiriting:")
    bot.register_next_step_handler(msg, step_save_final)

def step_save_final(message):
    state = admin_states[ADMIN_ID]
    del_price = float(message.text)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (group_id, photo_id, name, price, qop_weight, description, delivery_price) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (state["group_id"], state["photo_id"], state["name"], state["price"], state["q_weight"], state["desc"], del_price))
    conn.commit()
    conn.close()
    
    bot.send_message(ADMIN_ID, "✅ Tovar muvaffaqiyatli saqlandi!")

def step_promo_code(message):
    admin_states[ADMIN_ID] = {"p_code": message.text.strip().upper()}
    msg = bot.send_message(ADMIN_ID, "🎁 Ushbu promokod uchun mukofot matnini yozing:")
    bot.register_next_step_handler(msg, step_promo_text)

def step_promo_text(message):
    p_code = admin_states[ADMIN_ID]["p_code"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO promocodes (code, reward_text) VALUES (?, ?)", (p_code, message.text))
    conn.commit()
    conn.close()
    bot.send_message(ADMIN_ID, f"✅ Promokod tayyor!\nKod: `{p_code}`", parse_mode="Markdown")

# =====================================================================
# 8. INFINITY POLLING
# =====================================================================
if __name__ == "__main__":
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=10)
        except Exception as e:
            logger.error(e)
            import time
            time.sleep(5)
