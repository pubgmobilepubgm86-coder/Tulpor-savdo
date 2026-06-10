# -*- coding: utf-8 -*-
"""
LOYIHA: TULPOR SAVDO MARKAZI BOTI
YANGILANISH: Barcha eski sozlamalar (Statistika, Promokod, Top Xaridorlar) 100% saqlangan holda,
Yangi funksiyalar: Jonli lokatsiyani adminga yuborish, Do'kon lokatsiyasi, Video qo'llanma, Guruhni o'chirish va Tovarni mukammal tahrirlash qo'shildi.
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

MASTER_ADMIN_ID = 8086545587  

ORDER_ADMIN_1 = 5829527078
ORDER_ADMIN_2 = 8086545587
ORDER_ADMINS = [ORDER_ADMIN_1, ORDER_ADMIN_2]

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
# 2. MA'LUMOTLAR BAZASI (YANGILANGAN TIZIM)
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
            usage_count INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_promocodes (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            items_json TEXT NOT NULL,
            total_price REAL NOT NULL,
            ordered_at TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    
    # YANGI QO'SHILGAN BAZA JADVALLARI: Lokatsiya va Video qo'llanma uchun
    cursor.execute("CREATE TABLE IF NOT EXISTS shop_location (id INTEGER PRIMARY KEY, latitude REAL, longitude REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS manual (id INTEGER PRIMARY KEY, file_id TEXT, caption TEXT)")
    
    try: cursor.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'pending'")
    except sqlite3.OperationalError: pass
    
    try: cursor.execute("ALTER TABLE promocodes ADD COLUMN max_uses INTEGER DEFAULT 1")
    except sqlite3.OperationalError: pass
        
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('about_text', '🐎 Tulpor savdo markazi - Biz sizga eng sifatli mahsulotlarni eng hamyonbop narxlarda taqdim etamiz!')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('delivery_text', '🚚 Yetkazib berish shartlari:\nNamangan viloyati va Chortoq tumani bo''ylab tezkor hamda xavfsiz yetkazib berish xizmati mavjud.')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tovarlar_clicks', '0')")
    
    conn.commit()
    conn.close()

init_database()

# =====================================================================
# YORDAMCHI FUNKSIYALAR
# =====================================================================

def get_admin_contacts_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👨‍💻 1-Admin bilan bog'lanish", url=f"tg://user?id={ORDER_ADMIN_1}"),
        types.InlineKeyboardButton("👨‍💻 2-Admin bilan bog'lanish", url=f"tg://user?id={ORDER_ADMIN_2}")
    )
    return markup

# =====================================================================
# 3. RENDER UCHUN VEB-SERVER (24/7 ISHLASH)
# =====================================================================

class RenderHealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Tulpor Savdo Markazi Boti Faol!")
    def log_message(self, format, *args): return

def start_render_web_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(("0.0.0.0", port), RenderHealthCheckServer)
        server.serve_forever()
    except Exception as e: pass

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
    btn_loc = types.KeyboardButton("📍 Do'kon lokatsiyasi")
    btn_manual = types.KeyboardButton("📖 Botdan foydalanish")
    
    markup.add(btn_products, btn_cart)
    markup.add(btn_delivery, btn_about)
    markup.add(btn_loc, btn_manual)
    
    if user_id == MASTER_ADMIN_ID:
        markup.add(types.KeyboardButton("🛠 Admin Panel"))
    return markup

def get_admin_main_inline():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Yangi Tovar Qo'shish", callback_data="adm_add_product"),
        types.InlineKeyboardButton("📝 Tovarni Taxrirlash", callback_data="adm_edit_product_menu"),
        types.InlineKeyboardButton("❌ Tovar / Guruxni O'chirish", callback_data="adm_del_menu"),
        types.InlineKeyboardButton("📍 Do'kon Lokatsiyasini O'rnatish", callback_data="adm_set_loc"),
        types.InlineKeyboardButton("📖 Qo'llanma (Video) Yuklash", callback_data="adm_set_manual"),
        types.InlineKeyboardButton("🔑 Yangi Promokod Yaratish", callback_data="adm_add_promo"),
        types.InlineKeyboardButton("📊 Bot Statistikasi", callback_data="adm_stats"),
        types.InlineKeyboardButton("📢 Barchaga Xabar Yuborish", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("🏆 Top Xaridorlar Reytingi", callback_data="adm_top_buyers")
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

# YANGI: JONLI LOKATSIYANI QABUL QILISH VA ADMINLARGA FORWARD QILISH
@bot.message_handler(content_types=['location'])
def handle_location(message):
    if message.chat.id != MASTER_ADMIN_ID:
        for admin in ORDER_ADMINS:
            try:
                bot.send_message(admin, f"🔔 **Xaridordan joylashuv (Lokatsiya) keldi!**\n👤 Mijoz: {message.from_user.first_name}\n🆔 ID: `{message.chat.id}`", parse_mode="Markdown")
                bot.forward_message(admin, message.chat.id, message.message_id)
            except:
                pass
        bot.reply_to(message, "✅ Joylashuvingiz qabul qilindi va bot ma'muriyatiga muvaffaqiyatli yuborildi. Tez orada siz bilan bog'lanamiz!")

@bot.message_handler(func=lambda msg: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    text = message.text.strip()
    register_user(message.from_user)

    if text == "TOVARLAR 🌐":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = CAST(value AS INTEGER) + 1 WHERE key = 'tovarlar_clicks'")
        conn.commit()
        
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
        cursor.execute("SELECT items_json, total_price FROM orders WHERE user_id = ? AND status = 'accepted'", (user_id,))
        active_orders = cursor.fetchall()
        
        if active_orders:
            res_text = "🚚 **SIZNING FAOL BUYURTMALARingIZ:**\n\n"
            for idx, order in enumerate(active_orders, 1):
                items_data = json.loads(order['items_json'])
                res_text += f"📦 **{idx}-Buyurtmangiz:**\n"
                for item in items_data:
                     format_qty = int(item['qty']) if item['qty'] == int(item['qty']) else item['qty']
                     res_text += f"▪️ {item['name']} - {format_qty} {item['unit'].upper()} = {int(item['cost']):,} so'm\n"
                res_text += f"💰 **Jami:** {int(order['total_price']):,} so'm\n\n"
                
            res_text += "🏃‍♂️ **Holati:** Yetkazib berilyapti\n⏳ **24 soat ichida yetkazib beriladi!**"
            bot.send_message(message.chat.id, res_text, parse_mode="Markdown")
        else:
            cursor.execute("SELECT value FROM settings WHERE key = 'delivery_text'")
            bot.send_message(message.chat.id, cursor.fetchone()['value'])
            
        conn.close()

    elif text == "ℹ️ Biz haqimizda":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'about_text'")
        bot.send_message(message.chat.id, cursor.fetchone()['value'])
        conn.close()
        
    elif text == "📍 Do'kon lokatsiyasi":
        conn = get_db_connection()
        cursor = conn.cursor()
        loc = cursor.execute("SELECT latitude, longitude FROM shop_location").fetchone()
        conn.close()
        if loc:
            bot.send_message(message.chat.id, "📍 **Bizning do'konimiz xaritadagi joylashuvi:**", parse_mode="Markdown")
            bot.send_location(message.chat.id, loc['latitude'], loc['longitude'])
        else:
            bot.send_message(message.chat.id, "🚫 Do'kon lokatsiyasi hozircha kiritilmagan.")

    elif text == "📖 Botdan foydalanish":
        conn = get_db_connection()
        cursor = conn.cursor()
        data = cursor.execute("SELECT file_id, caption FROM manual").fetchone()
        conn.close()
        if data:
            bot.send_video(message.chat.id, data['file_id'], caption=data['caption'], parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "📖 Hozircha qo'llanma yuklanmagan.")

    elif text == "🛠 Admin Panel" and user_id == MASTER_ADMIN_ID:
        bot.send_message(message.chat.id, "🛠 **Admin Paneliga xush kelibsiz!**", reply_markup=get_admin_main_inline(), parse_mode="Markdown")

    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT reward_text, usage_count, max_uses FROM promocodes WHERE code = ?", (text.upper(),))
        promo = cursor.fetchone()
        
        if promo:
            if promo['usage_count'] >= promo['max_uses']:
                bot.send_message(message.chat.id, "❌ **Bu promokod ishlatib bo'lingan!** (Limit tugagan)", parse_mode="Markdown")
            else:
                cursor.execute("SELECT * FROM used_promocodes WHERE user_id = ? AND code = ?", (user_id, text.upper()))
                if cursor.fetchone():
                    bot.send_message(message.chat.id, "❌ **Siz bu promokoddan avval foydalangansiz!**", parse_mode="Markdown")
                else:
                    cursor.execute("INSERT INTO used_promocodes (user_id, code) VALUES (?, ?)", (user_id, text.upper()))
                    cursor.execute("UPDATE promocodes SET usage_count = usage_count + 1 WHERE code = ?", (text.upper(),))
                    conn.commit()
                    
                    bot.send_message(message.chat.id, f"🎁 **Tabriklaymiz! Promokod qabul qilindi!**\n\n{promo['reward_text']}", parse_mode="Markdown")
                    
                    admin_msg = f"🔔 **Vip Promokod Ishlatildi!**\n🔑 Kod: `{text.upper()}`\n👤 Xaridor: {message.from_user.first_name}\n🆔 ID: `{user_id}`\n📥 [Lichkaga o'tish](tg://user?id={user_id})"
                    bot.send_message(MASTER_ADMIN_ID, admin_msg, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "👇 Iltimos, pastdagi menyulardan birini tanlang.", reply_markup=get_main_menu_keyboard(user_id))
        conn.close()

# =====================================================================
# 6. INLINE CALLBACK HANDLERS
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

    # ------------------ YANGI ADMIN PANEL FUNKSIYALARI ------------------
    
    # DO'KON LOKATSIYASINI O'RNATISH
    if data == "adm_set_loc" and user_id == MASTER_ADMIN_ID:
        msg = bot.send_message(chat_id, "📍 Iltimos, do'kon joylashuvini (Location) Telegram xaritasi orqali yuboring:")
        bot.register_next_step_handler(msg, step_save_loc)
        bot.answer_callback_query(call.id)

    # VIDEO QO'LLANMA YUKLASH
    elif data == "adm_set_manual" and user_id == MASTER_ADMIN_ID:
        msg = bot.send_message(chat_id, "📹 Video qo'llanmani yuboring va tagiga uning tavsifini yozib qoldiring:")
        bot.register_next_step_handler(msg, step_save_manual)
        bot.answer_callback_query(call.id)

    # GURUX / TOVAR O'CHIRISH MENYUSI
    elif data == "adm_del_menu" and user_id == MASTER_ADMIN_ID:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🗑 Tovar O'chirish", callback_data="adm_del_product"),
            types.InlineKeyboardButton("🗂 Gurux O'chirish", callback_data="adm_del_group_list")
        )
        bot.edit_message_text("Nimani o'chirmoqchisiz? Tanlang:", chat_id, msg_id, reply_markup=markup)

    elif data == "adm_del_group_list" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        cursor = conn.cursor()
        groups = cursor.execute("SELECT id, name FROM groups").fetchall()
        conn.close()
        
        if not groups:
            bot.answer_callback_query(call.id, "O'chirish uchun guruxlar mavjud emas!", show_alert=True)
            return
            
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups:
            markup.add(types.InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"delg_{g['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="adm_del_menu"))
        bot.edit_message_text("O'chirmoqchi bo'lgan guruxni tanlang (DIQQAT: Gurux ichidagi tovarlar ham o'chib ketadi!):", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("delg_") and user_id == MASTER_ADMIN_ID:
        g_id = int(data.split("_")[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        groups = cursor.execute("SELECT id, name FROM groups").fetchall()
        conn.close()
        
        if not groups:
            bot.answer_callback_query(call.id, "O'chirish uchun guruxlar mavjud emas!", show_alert=True)
            return
            
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups:
            markup.add(types.InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"delg_{g['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="adm_del_menu"))
        bot.edit_message_text("O'chirmoqchi bo'lgan guruxni tanlang (DIQQAT: Gurux ichidagi tovarlar ham o'chib ketadi!):", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("delg_") and user_id == MASTER_ADMIN_ID:
        g_id = int(data.split("_")[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM groups WHERE id = ?", (g_id,))
        cursor.execute("DELETE FROM products WHERE group_id = ?", (g_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ Gurux va unga tegishli tovarlar o'chirildi!", show_alert=True)
        bot.edit_message_text("Gurux muvaffaqiyatli tozalandi.", chat_id, msg_id)

    # TOVARNI TAXRIRLASH
    elif data == "adm_edit_product_menu" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        cursor = conn.cursor()
        products = cursor.execute("SELECT id, name FROM products").fetchall()
        conn.close()
        
        if not products:
            bot.answer_callback_query(call.id, "Bazada taxrirlash uchun mahsulot topilmadi!", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        for prod in products:
            markup.add(types.InlineKeyboardButton(f"✏️ {prod['name']}", callback_data=f"p_edit_{prod['id']}"))
        
        bot.edit_message_text("Qaysi tovarni taxrirlamoqchisiz? Tanlang:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("p_edit_") and user_id == MASTER_ADMIN_ID:
        prod_id = int(data.split("_")[2])
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💰 Narxini o'zgartirish", callback_data=f"ch_price_{prod_id}"),
            types.InlineKeyboardButton("🖼 Rasmini o'zgartirish", callback_data=f"ch_photo_{prod_id}"),
            types.InlineKeyboardButton("📝 Sifatini (Tavsifini) o'zgartirish", callback_data=f"ch_desc_{prod_id}"),
            types.InlineKeyboardButton("🔙 Orqaga", callback_data="adm_edit_product_menu")
        )
        bot.edit_message_text("Ushbu tovarning qaysi qismini o'zgartiramiz?", chat_id, msg_id, reply_markup=markup)

    # Taxrirlash zanjirlari qabuli:
    elif data.startswith("ch_price_") and user_id == MASTER_ADMIN_ID:
        p_id = int(data.split("_")[2])
        msg = bot.send_message(chat_id, "💰 Yangi narxni kiriting (Faqat raqam):")
        bot.register_next_step_handler(msg, step_edit_price, p_id)
        bot.answer_callback_query(call.id)

    elif data.startswith("ch_photo_") and user_id == MASTER_ADMIN_ID:
        p_id = int(data.split("_")[2])
        msg = bot.send_message(chat_id, "🖼 Tovar uchun yangi rasmni yuboring:")
        bot.register_next_step_handler(msg, step_edit_photo, p_id)
        bot.answer_callback_query(call.id)

    elif data.startswith("ch_desc_") and user_id == MASTER_ADMIN_ID:
        p_id = int(data.split("_")[2])
        msg = bot.send_message(chat_id, "📝 Tovar uchun yangi sifat/tavsif matnini kiriting:")
        bot.register_next_step_handler(msg, step_edit_desc, p_id)
        bot.answer_callback_query(call.id)

    # 📊 BOT STATISTIKASI
    elif data == "adm_stats" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT value FROM settings WHERE key = 'tovarlar_clicks'")
        tovarlar_clicks = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM orders WHERE status = 'accepted'")
        real_buyers = cursor.fetchone()[0]
        conn.close()
        
        stats_msg = (
            "📊 **BOT STATISTIKASI:**\n\n"
            f"👥 Umumiy foydalanuvchilar: **{total_users} ta**\n"
            f"📦 'Tovarlar' bo'limi ochildi: **{tovarlar_clicks} marta**\n"
            f"🛍 Xarid qildi (Mijozlar soni): **{real_buyers} kishi**"
        )
        bot.send_message(chat_id, stats_msg, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    # 📢 BARCHAGA XABAR YUBORISH
    elif data == "adm_broadcast" and user_id == MASTER_ADMIN_ID:
        msg = bot.send_message(chat_id, "📢 **Barchaga yuborish uchun xabar yoki rasm yuboring:**\n\n_(Agar rasm yuborsangiz, tagiga yozgan ma'lumotingiz qo'shib yuboriladi)_", parse_mode="Markdown")
        bot.register_next_step_handler(msg, step_broadcast_receive)
        bot.answer_callback_query(call.id)

    # 🏆 TOP XARIDORLAR
    elif data == "adm_top_buyers" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            SELECT u.first_name, u.username, SUM(o.total_price) as total_spent 
            FROM orders o JOIN users u ON o.user_id = u.user_id 
            WHERE o.status = 'accepted' GROUP BY o.user_id ORDER BY total_spent DESC LIMIT 5
        """
        cursor.execute(query)
        top_buyers = cursor.fetchall()
        conn.close()
        
        if not top_buyers:
            bot.send_message(chat_id, "Hali hech kim xaridni tasdiqlamagan.")
            bot.answer_callback_query(call.id)
            return
            
        leaderboard = "🏆 **BOTDAGI ENG ZO'R 5 TA XARIDOR:**\n\n"
        for idx, buyer in enumerate(top_buyers, 1):
            name = buyer['first_name']
            username = f" (@{buyer['username']})" if buyer['username'] else ""
            spent = int(buyer['total_spent'])
            leaderboard += f"{idx}. 👤 {name}{username}\n💰 Jami xarid: **{spent:,} so'm**\n\n"
            
        bot.send_message(chat_id, leaderboard, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    # --------------------------------------------------------------------

    elif data.startswith("view_group_"):
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

    elif data.startswith("view_prod_"):
        p_id = int(data.split("_")[2])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (p_id,))
        p = cursor.fetchone()
        conn.close()
        
        if not p: return
        bot.delete_message(chat_id, msg_id)
        
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
        bot.register_next_step_handler(msg, process_direct_quantity_input, p_id)

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
            conn.close()
            return
            
        order_text = f"🔔 **Yangi Buyurtma!**\n👤 Xaridor: {call.from_user.first_name}\n🆔 ID: `{user_id}`\n\n"
        total = 0
        total_delivery = 0
        items_data = [] 
        
        for i in items:
            cost = i['price'] * i['quantity'] if i['unit'] == 'qop' else (i['price']/i['qop_weight'] if i['qop_weight'] > 0 else i['price']) * i['quantity']
            total += cost
            total_delivery += i['delivery_price']
            format_qty = int(i['quantity']) if i['quantity'] == int(i['quantity']) else i['quantity']
            
            items_data.append({"name": i['name'], "qty": i['quantity'], "unit": i['unit'], "cost": cost})
            order_text += f"▪️ {i['name']} - {format_qty} {i['unit'].upper()} = {int(cost):,} so'm\n"
            
        total_price_with_del = total + total_delivery
        order_text += f"\n🚚 Yetkazib berish: {int(total_delivery):,} so'm\n💰 Jami: {int(total_price_with_del):,} so'm\n📞 [Xaridor bilan bog'lanish](tg://user?id={user_id})"
        
        items_json_str = json.dumps(items_data)
        cursor.execute("INSERT INTO orders (user_id, items_json, total_price, ordered_at, status) VALUES (?, ?, ?, ?, 'pending')",
                       (user_id, items_json_str, total_price_with_del, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        order_id = cursor.lastrowid
        
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ Qabul qilish", callback_data=f"accept_ord_{order_id}_{user_id}"),
            types.InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_ord_{order_id}_{user_id}")
        )
        
        for ad_id in ORDER_ADMINS:
            try: bot.send_message(ad_id, order_text, reply_markup=admin_markup, parse_mode="Markdown")
            except Exception: pass

        bot.delete_message(chat_id, msg_id)
        msg_text = ("✅ **Sizning so'rovingizni 1 minutdan 1 soat oralig'ida ko'rib chiqamiz va sizga xabar beramiz.**\n\n"
                    "Savollar bo'yicha quyidagi buyurtma qabul qiluvchilarga yozishingiz mumkin:")
        bot.send_message(chat_id, msg_text, reply_markup=get_admin_contacts_markup(), parse_mode="Markdown")

    elif data.startswith("accept_ord_") or data.startswith("reject_ord_"):
        parts = data.split("_")
        action = parts[0]
        order_id = int(parts[2])
        client_id = int(parts[3])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
        order = cursor.fetchone()
        
        if order and order['status'] != 'pending':
            bot.answer_callback_query(call.id, "⚠️ Bu buyurtma allaqachon ko'rib chiqilgan!", show_alert=True)
            conn.close()
            return

        new_status = 'accepted' if action == 'accept' else 'rejected'
        cursor.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        conn.commit()
        conn.close()
        
        if action == "accept":
            client_msg = ("✅ **Buyurtmangiz qabul qilindi!**\n\n"
                          "📍 Jonli joylashuvingizni (Live Location) pastdagi qisqich tugmasi orqali yuborishingiz mumkin. "
                          "Bu buyurtmani tez va aniq yetkazib berishga yordam beradi!")
            bot.edit_message_text(call.message.text + "\n\n**HOLATI: ✅ QABUL QILINDI**", chat_id, msg_id)
        else:
            client_msg = ("❌ **Kechirasiz, buyurtmangiz rad etildi.**\n\n"
                          "Sababini bilish uchun quyidagi adminlarga murojaat qilishingiz mumkin:")
            bot.edit_message_text(call.message.text + "\n\n**HOLATI: ❌ RAD ETILDI**", chat_id, msg_id)
            
        try:
            bot.send_message(client_id, client_msg, reply_markup=get_admin_contacts_markup(), parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Muvaffaqiyatli bajarildi!")
        except Exception:
            bot.answer_callback_query(call.id, "Xaridor botni bloklagan bo'lishi mumkin.")

    # TOVAR QO'SHISH VA ADMINLIK
    elif data == "adm_add_product" and user_id == MASTER_ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📁 Mavjud guruh ichiga", callback_data="adm_exist_g"),
                   types.InlineKeyboardButton("✨ Yangi guruh ochish", callback_data="adm_new_g"))
        bot.send_message(chat_id, "Qanday guruhga tovar qo'shmoqchisiz?", reply_markup=markup)
        bot.answer_callback_query(call.id)

    elif data == "adm_new_g" and user_id == MASTER_ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ KG orqali", callback_data="adm_ng_kg"),
                   types.InlineKeyboardButton("📦 QOP orqali", callback_data="adm_ng_qop"))
        bot.edit_message_text("Yangi guruh uchun asosiy o'lchov turini tanlang:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("adm_ng_") and user_id == MASTER_ADMIN_ID:
        unit = data.split("_")[2]
        admin_states[user_id] = {"new_g_unit": unit}
        msg = bot.send_message(chat_id, "📝 Yangi guruhga nom bering:")
        bot.register_next_step_handler(msg, step_save_new_group)
        bot.answer_callback_query(call.id)

    elif data == "adm_exist_g" and user_id == MASTER_ADMIN_ID:
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

    elif data.startswith("adm_selg_") and user_id == MASTER_ADMIN_ID:
        g_id = int(data.split("_")[2])
        admin_states[user_id] = {"group_id": g_id}
        msg = bot.send_message(chat_id, "🖼 Endi tovar rasmini yuboring:")
        bot.register_next_step_handler(msg, step_save_photo)
        bot.answer_callback_query(call.id)
        
    elif data == "adm_del_product" and user_id == MASTER_ADMIN_ID:
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
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="adm_del_menu"))
        bot.edit_message_text("O'chirmoqchi bo'lgan tovaringiz ustiga bosing:", chat_id, msg_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        
    elif data.startswith("del_") and user_id == MASTER_ADMIN_ID:
        prod_id = int(data.split("_")[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (prod_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ Tovar muvaffaqiyatli o'chirildi!")
        bot.edit_message_text("Tovar o'chirildi. Admin panel orqali ishlashda davom etishingiz mumkin.", chat_id, msg_id)

    elif data == "adm_add_promo" and user_id == MASTER_ADMIN_ID:
        msg = bot.send_message(chat_id, "🔑 Yangi promokod so'zini kiriting (Masalan: VIP2026):")
        bot.register_next_step_handler(msg, step_promo_code)
        bot.answer_callback_query(call.id)

# =====================================================================
# 7. MAHSUS FUNKSIYA: FOYDALANUVCHI KLAVIATURADAN YOZIB XARID QILISHI
# =====================================================================
def process_direct_quantity_input(message, p_id):
    if message.text in ["TOVARLAR 🌐", "🛒 Savat", "🚚 Yetkazib berish", "ℹ️ Biz haqimizda", "📍 Do'kon lokatsiyasi", "📖 Botdan foydalanish", "🛠 Admin Panel"]:
        handle_text_messages(message)
        return

    text = message.text.lower().replace(" ", "").replace(",", ".")
    
    try:
        qty = 0
        unit = "qop"
        
        if "kg" in text:
            qty = float(text.replace("kg", ""))
            unit = "kg"
        else:
            qty = float(text)
            unit = "qop"
            
        if qty <= 0: raise ValueError
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT price, qop_weight FROM products WHERE id = ?", (p_id,))
        p = cursor.fetchone()
        conn.close()
        
        if not p: return

        if unit == 'qop': total_p = p['price'] * qty
        else: total_p = (p['price'] / p['qop_weight']) * qty if p['qop_weight'] > 0 else p['price'] * qty
            
        format_qty = int(qty) if qty == int(qty) else qty
        
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
# 8. ADMIN NEXT STEP ZANJIRLARI (YANGI VA ESKI)
# =====================================================================

# LOKATSIYA SAQLASH
def step_save_loc(message):
    if message.location:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shop_location")
        cursor.execute("INSERT INTO shop_location (latitude, longitude) VALUES (?, ?)", (message.location.latitude, message.location.longitude))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "✅ Do'kon xaritasi muvaffaqiyatli o'rnatildi!")
    else:
        bot.send_message(message.chat.id, "❌ Siz xarita (Location) yubormadingiz. Amaliyot bekor qilindi.")

# QO'LLANMA SAQLASH
def step_save_manual(message):
    if message.video:
        file_id = message.video.file_id
        caption = message.caption if message.caption else "Bu botdan qanday foydalanish bo'yicha video-qo'llanma."
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM manual")
        cursor.execute("INSERT INTO manual (file_id, caption) VALUES (?, ?)", (file_id, caption))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "✅ Video qo'llanma va uning tavsifi muvaffaqiyatli saqlandi!")
    else:
        bot.send_message(message.chat.id, "❌ Siz video yubormadingiz. Amaliyot bekor qilindi.")

# TOVARNI TAXRIRLASH (Narx)
def step_edit_price(message, p_id):
    try:
        new_price = float(message.text)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET price = ? WHERE id = ?", (new_price, p_id))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "✅ Tovar narxi muvaffaqiyatli yangilandi!")
    except:
        bot.send_message(message.chat.id, "❌ Xatolik! Narx faqat raqamlardan iborat bo'lishi shart.")

# TOVARNI TAXRIRLASH (Rasm)
def step_edit_photo(message, p_id):
    if message.photo:
        file_id = message.photo[-1].file_id
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET photo_id = ? WHERE id = ?", (file_id, p_id))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "✅ Tovar rasmi muvaffaqiyatli yangilandi!")
    else:
        bot.send_message(message.chat.id, "❌ Rasm yuborilmadi.")

# TOVARNI TAXRIRLASH (Sifat/Tavsif)
def step_edit_desc(message, p_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET description = ? WHERE id = ?", (message.text, p_id))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "✅ Tovarning sifati va tavsifi yangilandi!")

def step_broadcast_receive(message):
    if message.from_user.id != MASTER_ADMIN_ID: return
    
    conn = get_db_connection()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    
    bot.send_message(MASTER_ADMIN_ID, "⏳ **Xabaringiz barcha foydalanuvchilarga yuborilmoqda, kuting...**", parse_mode="Markdown")
    success = 0
    
    for u in users:
        try:
            if message.photo:
                bot.send_photo(u['user_id'], message.photo[-1].file_id, caption=message.caption, parse_mode="Markdown")
            else:
                bot.send_message(u['user_id'], message.text, parse_mode="Markdown")
            success += 1
        except Exception:
            pass
            
    bot.send_message(MASTER_ADMIN_ID, f"✅ **Muvaffaqiyatli!**\nXabaringiz {success} ta foydalanuvchiga yetkazildi.", parse_mode="Markdown")

def step_save_new_group(message):
    if message.from_user.id != MASTER_ADMIN_ID: return
    g_name = message.text.strip()
    g_unit = admin_states[MASTER_ADMIN_ID]["new_g_unit"]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO groups (name, unit_type) VALUES (?, ?)", (g_name, g_unit))
    g_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    admin_states[MASTER_ADMIN_ID] = {"group_id": g_id}
    msg = bot.send_message(message.chat.id, f"✅ Guruh yaratildi! Endi shu guruhga tovar qo'shamiz.\n\n🖼 Tovar rasmini yuboring:")
    bot.register_next_step_handler(msg, step_save_photo)

def step_save_photo(message):
    if not message.photo:
        msg = bot.send_message(MASTER_ADMIN_ID, "❌ Rasm yuboring:")
        bot.register_next_step_handler(msg, step_save_photo)
        return
    admin_states[MASTER_ADMIN_ID]["photo_id"] = message.photo[-1].file_id
    msg = bot.send_message(MASTER_ADMIN_ID, "📝 Tovar nomini kiriting:")
    bot.register_next_step_handler(msg, step_save_name)

def step_save_name(message):
    admin_states[MASTER_ADMIN_ID]["name"] = message.text
    msg = bot.send_message(MASTER_ADMIN_ID, "💰 Tovar narxini kiriting (Agar qop bo'lsa 1 qop narxi, kilo bo'lsa kg narxi):")
    bot.register_next_step_handler(msg, step_save_price)

def step_save_price(message):
    try:
        admin_states[MASTER_ADMIN_ID]["price"] = float(message.text)
        msg = bot.send_message(MASTER_ADMIN_ID, "📦 Qop necha kilo keladi? (Faqat kg da sotilsa 00 yozing):")
        bot.register_next_step_handler(msg, step_save_weight)
    except:
        msg = bot.send_message(MASTER_ADMIN_ID, "❌ Faqat raqam yozing:")
        bot.register_next_step_handler(msg, step_save_price)

def step_save_weight(message):
    try:
        admin_states[MASTER_ADMIN_ID]["q_weight"] = 0.0 if message.text == "00" else float(message.text)
        msg = bot.send_message(MASTER_ADMIN_ID, "📝 Tovar haqida tavsif yozing:")
        bot.register_next_step_handler(msg, step_save_desc)
    except:
        msg = bot.send_message(MASTER_ADMIN_ID, "❌ Kiloni faqat raqamda yoki 00 qilib yozing:")
        bot.register_next_step_handler(msg, step_save_weight)

def step_save_desc(message):
    admin_states[MASTER_ADMIN_ID]["desc"] = message.text
    msg = bot.send_message(MASTER_ADMIN_ID, "🚚 Dastavka narxini kiriting:")
    bot.register_next_step_handler(msg, step_save_final)

def step_save_final(message):
    try:
        del_price = float(message.text)
        state = admin_states[MASTER_ADMIN_ID]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (group_id, photo_id, name, price, qop_weight, description, delivery_price) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (state["group_id"], state["photo_id"], state["name"], state["price"], state["q_weight"], state["desc"], del_price))
        conn.commit()
        conn.close()
        
        bot.send_message(MASTER_ADMIN_ID, "✅ Tovar muvaffaqiyatli saqlandi!")
    except:
        msg = bot.send_message(MASTER_ADMIN_ID, "❌ Dastavka narxini raqamda yozing:")
        bot.register_next_step_handler(msg, step_save_final)

def step_promo_code(message):
    admin_states[MASTER_ADMIN_ID] = {"p_code": message.text.strip().upper()}
    msg = bot.send_message(MASTER_ADMIN_ID, "🎁 Ushbu promokod uchun mukofot matnini yozing:")
    bot.register_next_step_handler(msg, step_promo_text)

def step_promo_text(message):
    admin_states[MASTER_ADMIN_ID]["p_text"] = message.text
    msg = bot.send_message(MASTER_ADMIN_ID, "👥 **Bu promokodni jami necha kishi ishlata oladi?**\n\n_(Faqat raqam yozing, masalan 2, 5 yoki 10)_", parse_mode="Markdown")
    bot.register_next_step_handler(msg, step_promo_limit)

def step_promo_limit(message):
    try:
        limit = int(message.text)
        if limit <= 0: raise ValueError
        
        p_code = admin_states[MASTER_ADMIN_ID]["p_code"]
        p_text = admin_states[MASTER_ADMIN_ID]["p_text"]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO promocodes (code, reward_text, usage_count, max_uses) VALUES (?, ?, 0, ?)", (p_code, p_text, limit))
        conn.commit()
        conn.close()
        
        bot.send_message(MASTER_ADMIN_ID, f"✅ **Promokod tayyor!**\n\n🔑 Kod: `{p_code}`\n👥 Limit: **{limit} kishi**", parse_mode="Markdown")
    except ValueError:
        msg = bot.send_message(MASTER_ADMIN_ID, "❌ Iltimos, limit uchun faqat musbat raqam kiriting (masalan, 5):")
        bot.register_next_step_handler(msg, step_promo_limit)

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
