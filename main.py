# -*- coding: utf-8 -*-
"""
LOYIHA: TULPOR SAVDO MARKAZI BOTI
Barcha adminlik buyruqlari, guruhli tovar tizimi va yashirin promokod funksiyalari to'liq saqlangan.
YANGILANISH: Xaridni osonlashtirish uchun foydalanuvchi klaviaturadan to'g'ridan-to'g'ri "1" (qop) yoki "14kg" (kilo) deb yozadigan soddalashtirilgan tizim birlashtirildi.
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            unit_type TEXT NOT NULL
        )
    """)
    
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
        # PROMOKODNI YASHIRIN TEKSHIRISH
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
            bot.send_message(message.chat.id, "👇 Iltimos, pastdagi menyulardan birini tanlang.", reply_markup=get_main_menu_keyboard(user_id))
        conn.close()

# =====================================================================
# 6. INLINE CALLBACK HANDLERS (GURUHLAR VA XARID JARAYONI)
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

    # =====================================================================
    # YANGI SODDALASHTIRILGAN TOVAR KO'RISH VA XARID QILISH QISMI
    # =====================================================================
    elif data.startswith("view_prod_"):
        p_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (p_id,))
        p = cursor.fetchone()
        conn.close()
        
        if not p: return
        bot.delete_message(chat_id, msg_id)
        
        # Odamlarga tushunarli formatda buyurtma berishni o'rgatamiz
        caption = (
            f"📦 **{p['name']}**\n"
            f"💰 Narxi: {p['price']:,} so'm\n"
            f"🚚 Dastavka: {p['delivery_price']:,} so'm\n\n"
            f"📝 **Tavsif:** {p['description']}\n\n"
            f"❗️ **QANDAY BUYURTMA QILINADI?**\n"
            f"✍️ Shunchaki klaviaturaga yozib yuboring!\n"
            f"• Agar qop olmoqchi bo'lsangiz faqat raqam yozing: masalan **1** yoki **5**\n"
            f"• Agar kilo olmoqchi bo'lsangiz raqam yoniga kg qo'shib yozing: masalan **14kg** yoki **50kg**"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_groups"))
        
        msg = bot.send_photo(chat_id, p['photo_id'], caption=caption, parse_mode="Markdown", reply_markup=markup)
        
        # Aynan shu tovarga foydalanuvchidan klaviaturadan yozishini kutamiz:
        bot.register_next_step_handler(msg, process_direct_quantity_input, p_id)

    # Savatga yozish (Oxirgi bosqich)
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
        
        format_qty = int(qty) if qty == int(qty) else qty
        bot.answer_callback_query(call.id, f"✅ {format_qty} {unit.upper()} savatga qo'shildi!", show_alert=True)
        bot.edit_message_text(f"🛒 Sizning tovaringiz savatga o'tdi. Yana xarid qilish uchun 'TOVARLAR 🌐' tugmasini bosing.", chat_id, msg_id)


    # =====================================================================
    # ADMIN ZANJIRI (HECH QANDAY O'ZGARISHSİZ TO'LIQ SAQLANDI)
    # =====================================================================
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
        
    elif data == "adm_del_product" and user_id == ADMIN_ID:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM products")
        products = cursor.fetchall()
        conn.close()
        if not products:
            bot.answer_callback_query(call.id, "Hozirda bazada o'chirish uchun tovar yo'q.", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for prod in products:
            markup.add(types.InlineKeyboardButton(f"❌ {prod['name']}", callback_data=f"del_{prod['id']}"))
        bot.send_message(chat_id, "O'chirmoqchi bo'lgan tovaringiz ustiga bosing:", reply_markup=markup)
        bot.answer_callback_query(call.id)
        
    elif data.startswith("del_") and user_id == ADMIN_ID:
        prod_id = int(data.split("_")[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (prod_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Tovar muvaffaqiyatli o'chirildi!")
        bot.edit_message_text("Tovar o'chirildi. Admin panel orqali ishlashda davom etishingiz mumkin.", chat_id, msg_id)

    elif data == "adm_add_promo" and user_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "🔑 Yangi promokod so'zini kiriting (Masalan: VIP2026):")
        bot.register_next_step_handler(msg, step_promo_code)
        bot.answer_callback_query(call.id)

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
            format_qty = int(i['quantity']) if i['quantity'] == int(i['quantity']) else i['quantity']
            order_text += f"▪️ {i['name']} - {format_qty} {i['unit'].upper()} = {int(cost)} so'm\n"
            
        bot.send_message(ADMIN_ID, order_text + f"\n💰 Jami: {int(total)} so'm\n📞 [Xaridor bilan bog'lanish](tg://user?id={user_id})", parse_mode="Markdown")
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text("✅ Buyurtma adminga yuborildi! Tez orada siz bilan bog'lanamiz.", chat_id, msg_id)

# =====================================================================
# 7. MAHSUS FUNKSIYA: FOYDALANUVCHI KLAVIATURADAN YOZIB XARID QILISHI
# =====================================================================
def process_direct_quantity_input(message, p_id):
    # Agar foydalanuvchi menyudagi tugmalardan birini bossa jarayonni bekor qilamiz
    if message.text in ["TOVARLAR 🌐", "🛒 Savat", "🚚 Yetkazib berish", "ℹ️ Biz haqimizda", "🛠 Admin Panel"]:
        handle_text_messages(message)
        return

    text = message.text.lower().replace(" ", "").replace(",", ".")
    
    try:
        qty = 0
        unit = "qop"
        
        # Agar "kg" yozuvi bo'lsa
        if "kg" in text:
            qty = float(text.replace("kg", ""))
            unit = "kg"
        else:
            # Agar faqat raqam bo'lsa
            qty = float(text)
            unit = "qop"
            
        if qty <= 0: raise ValueError
        
        # Bazadan tovar malumotini olamiz
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT price, qop_weight FROM products WHERE id = ?", (p_id,))
        p = cursor.fetchone()
        conn.close()
        
        if not p: return

        # Narxni hisoblash
        if unit == 'qop':
            total_p = p['price'] * qty
        else:
            total_p = (p['price'] / p['qop_weight']) * qty if p['qop_weight'] > 0 else p['price'] * qty
            
        format_qty = int(qty) if qty == int(qty) else qty
        
        # Tasdiqlash va Savatga qoshish tugmasi
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🛒 {format_qty} {unit.upper()} = {int(total_p):,} so'm (Savatga qo'shish)", 
                                       callback_data=f"buy_{p_id}_{unit}_{qty}"),
            types.InlineKeyboardButton("❌ Bekor qilish", callback_data="back_to_groups")
        )
        
        bot.send_message(message.chat.id, f"Siz **{format_qty} {unit.upper()}** tanladingiz.\nTasdiqlash uchun quyidagi tugmani bosing:", parse_mode="Markdown", reply_markup=markup)

    except ValueError:
        bot.send_message(message.chat.id, "❌ Noto'g'ri yozdingiz. Iltimos faqat raqam (Masalan: `1` yoki `14kg`) deb yozing. Qayta urinib ko'rish uchun tovarlar bo'limiga kiring.", parse_mode="Markdown")

# =====================================================================
# 8. ADMIN NEXT STEP ZANJIRLARI (O'ZGARISHSİZ SAQLANDI)
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
    try:
        admin_states[ADMIN_ID]["price"] = float(message.text)
        msg = bot.send_message(ADMIN_ID, "📦 Qop necha kilo keladi? (Faqat kg da sotilsa 00 yozing):")
        bot.register_next_step_handler(msg, step_save_weight)
    except:
        msg = bot.send_message(ADMIN_ID, "❌ Faqat raqam yozing:")
        bot.register_next_step_handler(msg, step_save_price)

def step_save_weight(message):
    try:
        admin_states[ADMIN_ID]["q_weight"] = 0.0 if message.text == "00" else float(message.text)
        msg = bot.send_message(ADMIN_ID, "📝 Tovar haqida tavsif yozing:")
        bot.register_next_step_handler(msg, step_save_desc)
    except:
        msg = bot.send_message(ADMIN_ID, "❌ Kiloni faqat raqamda yoki 00 qilib yozing:")
        bot.register_next_step_handler(msg, step_save_weight)

def step_save_desc(message):
    admin_states[ADMIN_ID]["desc"] = message.text
    msg = bot.send_message(ADMIN_ID, "🚚 Dastavka narxini kiriting:")
    bot.register_next_step_handler(msg, step_save_final)

def step_save_final(message):
    try:
        del_price = float(message.text)
        state = admin_states[ADMIN_ID]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (group_id, photo_id, name, price, qop_weight, description, delivery_price) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (state["group_id"], state["photo_id"], state["name"], state["price"], state["q_weight"], state["desc"], del_price))
        conn.commit()
        conn.close()
        
        bot.send_message(ADMIN_ID, "✅ Tovar muvaffaqiyatli saqlandi!")
    except:
        msg = bot.send_message(ADMIN_ID, "❌ Dastavka narxini raqamda yozing:")
        bot.register_next_step_handler(msg, step_save_final)

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
# 9. INFINITY POLLING (ASOSIY ISHGA TUSHIRISH)
# =====================================================================
if __name__ == "__main__":
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=10)
        except Exception as e:
            logger.error(e)
            import time
            time.sleep(5)
