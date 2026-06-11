# -*- coding: utf-8 -*-
"""
LOYIHA: TULPOR SAVDO MARKAZI BOTI
YANGILANISH: Barcha eski sozlamalar 100% saqlangan holda:
- Mijozdan lokatsiya/manzil so'rash tizimi (qabul qilingandan so'ng).
- Adminlar uchun mijoz profiliga to'g'ridan-to'g'ri yozish havolasi (Lichka).
- "Yetkazib berildi" holati va tugmasi qo'shildi.
- Emojilar va chiroyli dizayn tiklandi.
- Promokod istalgan bo'limda ishlashi va limitligi ta'minlandi.
"""

import os
import sys
import json
import sqlite3
import logging
import threading
import time
import urllib.request
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

DB_NAME = "tulpor_savdo_core.db"

# =====================================================================
# 2. MA'LUMOTLAR BAZASI ULANISHI (WAL REJIMIDA - RAVON ISHLASH)
# =====================================================================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
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
    
    cursor.execute("CREATE TABLE IF NOT EXISTS shop_location (id INTEGER PRIMARY KEY, latitude REAL, longitude REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS manual (id INTEGER PRIMARY KEY, file_id TEXT, caption TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS user_persistent_states (user_id INTEGER PRIMARY KEY, state TEXT, context TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    
    # Emojilar bilan chiroyli ma'lumotlar kiritilmoqda
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('about_text', '🐎 *Tulpor savdo markazi* 🌟\n\n🤝 Biz sizga eng sifatli mahsulotlarni eng hamyonbop narxlarda taqdim etamiz!\n✅ Ishonchli xizmat, halollik va tezkorlik bizning oliy maqsadimizdir.')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('delivery_text', '🚚 *Yetkazib berish shartlari:* 📦\n\n📍 Namangan viloyati va Chortoq tumani bo''ylab tezkor hamda xavfsiz yetkazib berish xizmati maqsadga muvofiq.\n⚡️ Buyurtmangiz xavfsiz va o\\"z"vaqtida yetib boradi!')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tovarlar_clicks', '0')")
    
    conn.commit()
    conn.close()

init_database()

# =====================================================================
# BAZA ORQALI STATE (HOLAT) BOSHQARUVI TIZIMI
# =====================================================================

def set_user_state(user_id, state_name, context_dict=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    context_json = json.dumps(context_dict) if context_dict else "{}"
    cursor.execute("INSERT OR REPLACE INTO user_persistent_states (user_id, state, context) VALUES (?, ?, ?)", 
                   (user_id, state_name, context_json))
    conn.commit()
    conn.close()

def get_user_state(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT state, context FROM user_persistent_states WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['state'], json.loads(row['context'])
    return None, {}

def clear_user_state(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_persistent_states WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_admin_contacts_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👨‍💻 1-Admin bilan bog'lanish", url=f"tg://user?id={ORDER_ADMIN_1}"),
        types.InlineKeyboardButton("👨‍💻 2-Admin bilan bog'lanish", url=f"tg://user?id={ORDER_ADMIN_2}")
    )
    return markup

# =====================================================================
# 3. RENDER UCHUN VEB-SERVER VA ANTI-SLEEP (KEEPALIVE) TIZIMI
# =====================================================================

class RenderHealthCheckServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Tulpor Savdo Markazi Boti Faol va Uyg'oq!")
    def log_message(self, format, *args): return

def start_render_web_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(("0.0.0.0", port), RenderHealthCheckServer)
        server.serve_forever()
    except Exception: pass

def self_ping_keepalive_loop():
    time.sleep(20)
    while True:
        try:
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if render_url:
                urllib.request.urlopen(render_url, timeout=15)
            else:
                urllib.request.urlopen("http://localhost:8080", timeout=15)
        except Exception as e: pass
        time.sleep(420) 

web_thread = threading.Thread(target=start_render_web_server, daemon=True)
web_thread.start()

ping_thread = threading.Thread(target=self_ping_keepalive_loop, daemon=True)
ping_thread.start()

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
# 5. ASOSIY ENTRYLAR VA JOYLASHUV (LOCATION) ISHLOVCHISI
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
    clear_user_state(message.from_user.id)
    register_user(message.from_user)
    text = f"🐎 **Tulpor savdo markazi** botiga xush kelibsiz, {message.from_user.first_name}!\n\n👇 Kerakli bo'limni tanlang:"
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu_keyboard(message.from_user.id), parse_mode="Markdown")

@bot.message_handler(content_types=['location'])
def handle_location(message):
    user_id = message.from_user.id
    register_user(message.from_user)
    state, context = get_user_state(user_id)
    
    if user_id == MASTER_ADMIN_ID and state == "WAITING_FOR_SHOP_LOCATION":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shop_location")
        cursor.execute("INSERT INTO shop_location (latitude, longitude) VALUES (?, ?)", (message.location.latitude, message.location.longitude))
        conn.commit()
        conn.close()
        clear_user_state(user_id)
        bot.send_message(message.chat.id, "✅ Do'kon xaritasi muvaffaqiyatli o'rnatildi va bazaga saqlandi!")
        return

    # Yangi: Mijozdan buyurtma uchun lokatsiya kutayotgan holat
    if state == "WAITING_FOR_LOCATION_OR_ADDRESS":
        for admin in ORDER_ADMINS:
            try:
                bot.send_message(admin, f"📍 **Mijozdan buyurtma yetkazish uchun LOKATSIYA keldi!**\n👤 Mijoz: [{message.from_user.first_name}](tg://user?id={user_id})\n🆔 ID: `{user_id}`", parse_mode="Markdown")
                bot.send_location(admin, message.location.latitude, message.location.longitude)
            except: pass
        clear_user_state(user_id)
        bot.send_message(user_id, "✅ Lokatsiyangiz qabul qilindi! Buyurtma tez orada yetkazib beriladi.", reply_markup=get_main_menu_keyboard(user_id))
        return

    # Oddiy vaqtda tashlangan lokatsiya
    if message.chat.id != MASTER_ADMIN_ID:
        for admin in ORDER_ADMINS:
            try:
                bot.send_message(admin, f"🔔 **Xaridordan joylashuv (Lokatsiya) keldi!**\n👤 Mijoz: [{message.from_user.first_name}](tg://user?id={user_id})\n🆔 ID: `{message.chat.id}`", parse_mode="Markdown")
                bot.forward_message(admin, message.chat.id, message.message_id)
            except: pass
        bot.reply_to(message, "✅ Joylashuvingiz qabul qilindi. Tez orada siz bilan bog'lanamiz!")

# =====================================================================
# 6. DOIMIY STATE INTEGRATSIYASI BILAN ALL_MESSAGES HANDLERI
# =====================================================================
@bot.message_handler(content_types=['text', 'photo', 'video'])
def handle_all_messages(message):
    user_id = message.from_user.id
    register_user(message.from_user)
    state, context = get_user_state(user_id)
    text = message.text.strip() if message.text else ""
    
    # Asosiy menyu tugmalari bosilsa holatni tozalash
    if message.content_type == 'text' and text in ["TOVARLAR 🌐", "🛒 Savat", "🚚 Yetkazib berish", "ℹ️ Biz haqimizda", "📍 Do'kon lokatsiyasi", "📖 Botdan foydalanish", "🛠 Admin Panel"]:
        clear_user_state(user_id)
        state = None

    if state:
        if state == "WAITING_FOR_QUANTITY":
            process_direct_quantity_input(message, context.get('prod_id'))
            return
            
        # Yangi: Mijoz manzilni matn ko'rinishida yozsa
        elif state == "WAITING_FOR_LOCATION_OR_ADDRESS":
            if text == "🏠 Bosh menyu":
                clear_user_state(user_id)
                bot.send_message(user_id, "Bosh menyuga qaytdik.", reply_markup=get_main_menu_keyboard(user_id))
                return
            else:
                for admin in ORDER_ADMINS:
                    try:
                        bot.send_message(admin, f"📝 **Mijozdan buyurtma yetkazish uchun MANZIL (Matn) keldi!**\n👤 Mijoz: [{message.from_user.first_name}](tg://user?id={user_id})\n🆔 ID: `{user_id}`\n\n🗺 Manzil: {text}", parse_mode="Markdown")
                    except: pass
                clear_user_state(user_id)
                bot.send_message(user_id, "✅ Manzilingiz qabul qilindi! Buyurtma tez orada yetkazib beriladi.", reply_markup=get_main_menu_keyboard(user_id))
                return

        elif user_id == MASTER_ADMIN_ID:
            if state == "WAITING_FOR_MANUAL_VIDEO":
                if message.video:
                    file_id = message.video.file_id
                    caption = message.caption if message.caption else "Bu botdan qanday foydalanish bo'yicha video-qo'llanma."
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM manual")
                    cursor.execute("INSERT INTO manual (file_id, caption) VALUES (?, ?)", (file_id, caption))
                    conn.commit()
                    conn.close()
                    clear_user_state(user_id)
                    bot.send_message(message.chat.id, "✅ Video qo'llanma muvaffaqiyatli saqlandi!")
                else:
                    bot.send_message(message.chat.id, "❌ Iltimos, faqat video formatida qo'llanma yuboring:")
                return
                
            elif state == "WAITING_FOR_EDIT_PRICE":
                try:
                    new_price = float(text)
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE products SET price = ? WHERE id = ?", (new_price, context.get('prod_id')))
                    conn.commit()
                    conn.close()
                    clear_user_state(user_id)
                    bot.send_message(message.chat.id, "✅ Tovar narxi muvaffaqiyatli yangilandi!")
                except:
                    bot.send_message(message.chat.id, "❌ Xatolik! Narxni faqat raqamda kiriting:")
                return
                
            elif state == "WAITING_FOR_EDIT_PHOTO":
                if message.photo:
                    file_id = message.photo[-1].file_id
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE products SET photo_id = ? WHERE id = ?", (file_id, context.get('prod_id')))
                    conn.commit()
                    conn.close()
                    clear_user_state(user_id)
                    bot.send_message(message.chat.id, "✅ Tovar rasmi muvaffaqiyatli yangilandi!")
                else:
                    bot.send_message(message.chat.id, "❌ Iltimos, rasm formatida yuboring:")
                return
                
            elif state == "WAITING_FOR_EDIT_DESC":
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE products SET description = ? WHERE id = ?", (text, context.get('prod_id')))
                conn.commit()
                conn.close()
                clear_user_state(user_id)
                bot.send_message(message.chat.id, "✅ Tovar tavsifi muvaffaqiyatli o'zgartirildi!")
                return
                
            elif state == "WAITING_FOR_BROADCAST":
                conn = get_db_connection()
                users = conn.execute("SELECT user_id FROM users").fetchall()
                conn.close()
                bot.send_message(MASTER_ADMIN_ID, "⏳ **Xabar yuborilmoqda, kuting...**", parse_mode="Markdown")
                success = 0
                for u in users:
                    try:
                        if message.photo:
                            bot.send_photo(u['user_id'], message.photo[-1].file_id, caption=message.caption, parse_mode="Markdown")
                        else:
                            bot.send_message(u['user_id'], text, parse_mode="Markdown")
                        success += 1
                    except: pass
                clear_user_state(user_id)
                bot.send_message(MASTER_ADMIN_ID, f"✅ Xabar {success} ta foydalanuvchiga yetkazildi.", parse_mode="Markdown")
                return
                
            elif state == "WAITING_FOR_NEW_GROUP_NAME":
                g_name = text
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO groups (name, unit_type) VALUES (?, ?)", (g_name, context.get('unit')))
                g_id = cursor.lastrowid
                conn.commit()
                conn.close()
                set_user_state(user_id, "WAITING_FOR_PRODUCT_PHOTO", {"group_id": g_id})
                bot.send_message(message.chat.id, "✅ Guruh yaratildi!\n\n🖼 Endi tovar rasmini yuboring:")
                return
                
            elif state == "WAITING_FOR_PRODUCT_PHOTO":
                if not message.photo:
                    bot.send_message(MASTER_ADMIN_ID, "❌ Iltimos, rasm yuboring:")
                    return
                context["photo_id"] = message.photo[-1].file_id
                set_user_state(user_id, "WAITING_FOR_PRODUCT_NAME", context)
                bot.send_message(MASTER_ADMIN_ID, "📝 Tovar nomini kiriting:")
                return
                
            elif state == "WAITING_FOR_PRODUCT_NAME":
                context["name"] = text
                set_user_state(user_id, "WAITING_FOR_PRODUCT_PRICE", context)
                bot.send_message(MASTER_ADMIN_ID, "💰 Tovar narxini kiriting:")
                return
                
            elif state == "WAITING_FOR_PRODUCT_PRICE":
                try:
                    context["price"] = float(text)
                    set_user_state(user_id, "WAITING_FOR_PRODUCT_WEIGHT", context)
                    bot.send_message(MASTER_ADMIN_ID, "📦 Qop vaznini kiriting (Faqat kg da bo'lsa 00 deb yozing):")
                except:
                    bot.send_message(MASTER_ADMIN_ID, "❌ Narxni raqamda kiriting:")
                return
                
            elif state == "WAITING_FOR_PRODUCT_WEIGHT":
                try:
                    context["q_weight"] = 0.0 if text == "00" else float(text)
                    set_user_state(user_id, "WAITING_FOR_PRODUCT_DESC", context)
                    bot.send_message(MASTER_ADMIN_ID, "📝 Tovar haqida tavsif/sifat yozing:")
                except:
                    bot.send_message(MASTER_ADMIN_ID, "❌ Raqamda kiriting:")
                return
                
            elif state == "WAITING_FOR_PRODUCT_DESC":
                context["desc"] = text
                set_user_state(user_id, "WAITING_FOR_PRODUCT_DELIVERY", context)
                bot.send_message(MASTER_ADMIN_ID, "🚚 Dastavka narxini kiriting:")
                return
                
            elif state == "WAITING_FOR_PRODUCT_DELIVERY":
                try:
                    del_price = float(text)
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO products (group_id, photo_id, name, price, qop_weight, description, delivery_price) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (context["group_id"], context["photo_id"], context["name"], context["price"], context["q_weight"], context["desc"], del_price))
                    conn.commit()
                    conn.close()
                    clear_user_state(user_id)
                    bot.send_message(MASTER_ADMIN_ID, "✅ Yangi tovar muvaffaqiyatli bazaga qo'shildi!")
                except:
                    bot.send_message(MASTER_ADMIN_ID, "❌ Raqamda kiriting:")
                return
                
            elif state == "WAITING_FOR_PROMO_CODE":
                context["p_code"] = text.upper()
                set_user_state(user_id, "WAITING_FOR_PROMO_TEXT", context)
                bot.send_message(MASTER_ADMIN_ID, "🎁 Promokod mukofot matnini yozing:")
                return
                
            elif state == "WAITING_FOR_PROMO_TEXT":
                context["p_text"] = text
                set_user_state(user_id, "WAITING_FOR_PROMO_LIMIT", context)
                bot.send_message(MASTER_ADMIN_ID, "👥 Ishlatish limitini kiriting (Faqat raqam):")
                return
                
            elif state == "WAITING_FOR_PROMO_LIMIT":
                try:
                    limit = int(text)
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT OR REPLACE INTO promocodes (code, reward_text, usage_count, max_uses) VALUES (?, ?, 0, ?)", 
                                   (context["p_code"], context["p_text"], limit))
                    conn.commit()
                    conn.close()
                    clear_user_state(user_id)
                    bot.send_message(MASTER_ADMIN_ID, f"✅ Promokod yaratildi: `{context['p_code']}`")
                except:
                    bot.send_message(MASTER_ADMIN_ID, "❌ Limitni raqamda kiriting:")
                return

    if message.content_type != 'text': return

    if text == "TOVARLAR 🌐":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = CAST(value AS INTEGER) + 1 WHERE key = 'tovarlar_clicks'")
        conn.commit()
        groups = cursor.execute("SELECT * FROM groups").fetchall()
        conn.close()
        
        if not groups:
            bot.send_message(message.chat.id, "📭 Hozircha do'konimizda mahsulotlar kiritilmagan.")
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups: markup.add(types.InlineKeyboardButton(g['name'], callback_data=f"view_group_{g['id']}"))
        bot.send_message(message.chat.id, "📁 Kerakli mahsulot guruhini tanlang:", reply_markup=markup)

    elif text == "🛒 Savat":
        conn = get_db_connection()
        cursor = conn.cursor()
        items = cursor.execute("""
            SELECT c.quantity, c.unit, p.name, p.price, p.qop_weight, p.delivery_price 
            FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = ?
        """, (user_id,)).fetchall()
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
            cost = (item['price'] * qty) if unit == 'qop' else ((item['price'] / item['qop_weight'] if item['qop_weight'] > 0 else item['price']) * qty)
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
        active_orders = cursor.execute("SELECT items_json, total_price FROM orders WHERE user_id = ? AND status = 'accepted'", (user_id,)).fetchall()
        if active_orders:
            res_text = "🚚 **SIZNING FAOL BUYURTMALARingIZ:**\n\n"
            for idx, order in enumerate(active_orders, 1):
                items_data = json.loads(order['items_json'])
                res_text += f"📦 **{idx}-Buyurtmangiz:**\n"
                for item in items_data:
                     format_qty = int(item['qty']) if item['qty'] == int(item['qty']) else item['qty']
                     res_text += f"▪️ {item['name']} - {format_qty} {item['unit'].upper()} = {int(item['cost']):,} so'm\n"
                res_text += f"💰 **Jami:** {int(order['total_price']):,} so'm\n\n"
            res_text += "🏃‍♂️ **Holati:** Yetkazib berilyapti\n⏳ **Yaqin vaqt ichida yetkaziladi!**"
            bot.send_message(message.chat.id, res_text, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, cursor.execute("SELECT value FROM settings WHERE key = 'delivery_text'").fetchone()['value'], parse_mode="Markdown")
        conn.close()

    elif text == "ℹ️ Biz haqimizda":
        conn = get_db_connection()
        bot.send_message(message.chat.id, conn.execute("SELECT value FROM settings WHERE key = 'about_text'").fetchone()['value'], parse_mode="Markdown")
        conn.close()
        
    elif text == "📍 Do'kon lokatsiyasi":
        conn = get_db_connection()
        loc = conn.execute("SELECT latitude, longitude FROM shop_location").fetchone()
        conn.close()
        if loc:
            bot.send_message(message.chat.id, "📍 **Bizning do'konimiz xaritadagi joylashuvi:**", parse_mode="Markdown")
            bot.send_location(message.chat.id, loc['latitude'], loc['longitude'])
        else:
            bot.send_message(message.chat.id, "🚫 Do'kon lokatsiyasi hozircha kiritilmagan.")

    elif text == "📖 Botdan foydalanish":
        conn = get_db_connection()
        data = conn.execute("SELECT file_id, caption FROM manual").fetchone()
        conn.close()
        if data:
            bot.send_video(message.chat.id, data['file_id'], caption=data['caption'], parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "📖 Hozircha qo'llanma yuklanmagan.")

    elif text == "🛠 Admin Panel" and user_id == MASTER_ADMIN_ID:
        bot.send_message(message.chat.id, "🛠 **Admin Paneliga xush kelibsiz!**", reply_markup=get_admin_main_inline(), parse_mode="Markdown")

    else:
        # PROMOKOD YOKI NOTO'G'RI BUYRUQ TEKSHIRUVI (Har qanday ekranda ishlaydi)
        conn = get_db_connection()
        cursor = conn.cursor()
        promo = cursor.execute("SELECT reward_text, usage_count, max_uses FROM promocodes WHERE code = ?", (text.upper(),)).fetchone()
        if promo:
            if promo['usage_count'] >= promo['max_uses']:
                bot.send_message(message.chat.id, "❌ **Kechirasiz, bu promokod limiti tugagan yoki faol emas!**", parse_mode="Markdown")
            else:
                if cursor.execute("SELECT * FROM used_promocodes WHERE user_id = ? AND code = ?", (user_id, text.upper())).fetchone():
                    bot.send_message(message.chat.id, "❌ **Siz bu promokoddan avval foydalangansiz!**", parse_mode="Markdown")
                else:
                    cursor.execute("INSERT INTO used_promocodes (user_id, code) VALUES (?, ?)", (user_id, text.upper()))
                    cursor.execute("UPDATE promocodes SET usage_count = usage_count + 1 WHERE code = ?", (text.upper(),))
                    conn.commit()
                    bot.send_message(message.chat.id, f"🎁 **Tabriklaymiz! Promokod muvaffaqiyatli qabul qilindi!** 🎉\n\n{promo['reward_text']}", parse_mode="Markdown")
                    bot.send_message(MASTER_ADMIN_ID, f"🔔 **Promokod ishlatildi:** `{text.upper()}`\n👤 Kim: [{message.from_user.first_name}](tg://user?id={user_id})", parse_mode="Markdown")
        else:
            # Matn hech qaysi buyruqqa ham, promokodga ham mos kelmasa
            bot.send_message(message.chat.id, "❌ **Noto'g'ri buyruq yoki xato promokod.**\n👇 Iltimos, pastdagi menyu tugmalaridan birini tanlang.", reply_markup=get_main_menu_keyboard(user_id), parse_mode="Markdown")
        conn.close()

# =====================================================================
# 7. INLINE CALLBACK HANDLERS (TEZLASHTIRILGAN VA XATOSIZ REJIM)
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    bot.answer_callback_query(call.id)

    # ------------------ YANGI ADMIN PANEL FUNKSIYALARI ------------------
    if data == "adm_set_loc" and user_id == MASTER_ADMIN_ID:
        set_user_state(user_id, "WAITING_FOR_SHOP_LOCATION")
        bot.send_message(chat_id, "📍 Iltimos, do'kon joylashuvini (Location) Telegram xaritasi orqali yuboring:")
        return

    elif data == "adm_set_manual" and user_id == MASTER_ADMIN_ID:
        set_user_state(user_id, "WAITING_FOR_MANUAL_VIDEO")
        bot.send_message(chat_id, "📹 Video qo'llanmani yuboring va tagiga uning tavsifini yozib qoldiring:")
        return

    elif data == "adm_del_menu" and user_id == MASTER_ADMIN_ID:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🗑 Tovar O'chirish", callback_data="adm_del_product"),
            types.InlineKeyboardButton("🗂 Gurux O'chirish", callback_data="adm_del_group_list")
        )
        bot.edit_message_text("Nimani o'chirmoqchisiz? Tanlang:", chat_id, msg_id, reply_markup=markup)
        return

    elif data == "adm_del_group_list" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        cursor = conn.cursor()
        groups = cursor.execute("SELECT id, name FROM groups").fetchall()
        conn.close()
        
        if not groups:
            bot.send_message(chat_id, "O'chirish uchun guruxlar mavjud emas!")
            return
            
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups:
            markup.add(types.InlineKeyboardButton(f"📁 {g['name']}", callback_data=f"delg_{g['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="adm_del_menu"))
        bot.edit_message_text("O'chirmoqchi bo'lgan guruxni tanlang (DIQQAT: Gurux ichidagi tovarlar ham o'chadi!):", chat_id, msg_id, reply_markup=markup)
        return

    elif data.startswith("delg_") and user_id == MASTER_ADMIN_ID:
        g_id = int(data.split("_")[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM groups WHERE id = ?", (g_id,))
        cursor.execute("DELETE FROM products WHERE group_id = ?", (g_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text("✅ Gurux va uning ichidagi tovarlar muvaffaqiyatli o'chirildi!", chat_id, msg_id)
        return

    elif data == "adm_del_product" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        products = conn.execute("SELECT id, name FROM products").fetchall()
        conn.close()
        if not products:
            bot.send_message(chat_id, "O'chirish uchun tovar yo'q.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for prod in products: markup.add(types.InlineKeyboardButton(f"❌ {prod['name']}", callback_data=f"delp_{prod['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="adm_del_menu"))
        bot.edit_message_text("O'chiriladigan tovarni tanlang:", chat_id, msg_id, reply_markup=markup)
        return

    elif data.startswith("delp_") and user_id == MASTER_ADMIN_ID:
        p_id = int(data.split("_")[1])
        conn = get_db_connection()
        conn.execute("DELETE FROM products WHERE id = ?", (p_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text("✅ Tovar muvaffaqiyatli o'chirildi.", chat_id, msg_id)
        return

    elif data == "adm_edit_product_menu" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        products = conn.execute("SELECT id, name FROM products").fetchall()
        conn.close()
        if not products:
            bot.send_message(chat_id, "Bazada taxrirlash uchun mahsulot topilmadi!")
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        for prod in products: markup.add(types.InlineKeyboardButton(f"✏️ {prod['name']}", callback_data=f"p_edit_{prod['id']}"))
        bot.edit_message_text("Tahrirlanadigan tovarni tanlang:", chat_id, msg_id, reply_markup=markup)
        return

    elif data.startswith("p_edit_") and user_id == MASTER_ADMIN_ID:
        p_id = int(data.split("_")[2])
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("💰 Narxni o'zgartirish", callback_data=f"ch_price_{p_id}"),
                   types.InlineKeyboardButton("🖼 Rasmni o'zgartirish", callback_data=f"ch_photo_{p_id}"),
                   types.InlineKeyboardButton("📝 Tavsifni o'zgartirish", callback_data=f"ch_desc_{p_id}"))
        bot.edit_message_text("O'zgartiriladigan qismni tanlang:", chat_id, msg_id, reply_markup=markup)
        return

    elif data.startswith("ch_price_") and user_id == MASTER_ADMIN_ID:
        p_id = int(data.split("_")[2])
        set_user_state(user_id, "WAITING_FOR_EDIT_PRICE", {"prod_id": p_id})
        bot.send_message(chat_id, "💰 Yangi narxni faqat raqamda kiriting:")
        return

    elif data.startswith("ch_photo_") and user_id == MASTER_ADMIN_ID:
        p_id = int(data.split("_")[2])
        set_user_state(user_id, "WAITING_FOR_EDIT_PHOTO", {"prod_id": p_id})
        bot.send_message(chat_id, "🖼 Yangi rasm yuboring:")
        return

    elif data.startswith("ch_desc_") and user_id == MASTER_ADMIN_ID:
        p_id = int(data.split("_")[2])
        set_user_state(user_id, "WAITING_FOR_EDIT_DESC", {"prod_id": p_id})
        bot.send_message(chat_id, "📝 Yangi sifat/tavsif matnini yuboring:")
        return

    elif data == "adm_stats" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        clicks = conn.execute("SELECT value FROM settings WHERE key = 'tovarlar_clicks'").fetchone()[0]
        buyers = conn.execute("SELECT COUNT(DISTINCT user_id) FROM orders WHERE status = 'accepted' OR status = 'delivered'").fetchone()[0]
        conn.close()
        bot.send_message(chat_id, f"📊 **Statistika:**\n\nA'zolar: {total_users}\n'Tovarlar' bo'limi bosildi: {clicks}\nXaridorlar: {buyers}", parse_mode="Markdown")
        return

    elif data == "adm_broadcast" and user_id == MASTER_ADMIN_ID:
        set_user_state(user_id, "WAITING_FOR_BROADCAST")
        bot.send_message(chat_id, "📢 Reklama yoki xabar matnini (yoki rasmini) yuboring:")
        return

    elif data == "adm_add_promo" and user_id == MASTER_ADMIN_ID:
        set_user_state(user_id, "WAITING_FOR_PROMO_CODE")
        bot.send_message(chat_id, "🔑 Yangi promokod kalit so'zini kiriting:")
        return

    elif data == "adm_top_buyers" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        top_buyers = conn.execute("""
            SELECT u.first_name, SUM(o.total_price) as total FROM orders o JOIN users u ON o.user_id = u.user_id 
            WHERE o.status = 'accepted' OR o.status = 'delivered' GROUP BY o.user_id ORDER BY total DESC LIMIT 5
        """).fetchall()
        conn.close()
        res_top = "🏆 **Top 5 Xaridorlar:**\n\n"
        for idx, b in enumerate(top_buyers, 1): res_top += f"{idx}. {b['first_name']} - {int(b['total']):,} so'm\n"
        bot.send_message(chat_id, res_top, parse_mode="Markdown")
        return

    elif data == "adm_add_product" and user_id == MASTER_ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📁 Mavjud guruh ichiga", callback_data="adm_exist_g"),
                   types.InlineKeyboardButton("✨ Yangi guruh ochish", callback_data="adm_new_g"))
        bot.send_message(chat_id, "Qanday guruhga tovar qo'shmoqchisiz?", reply_markup=markup)
        return

    elif data == "adm_new_g" and user_id == MASTER_ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ KG orqali", callback_data="adm_ng_kg"),
                   types.InlineKeyboardButton("📦 QOP orqali", callback_data="adm_ng_qop"))
        bot.edit_message_text("Yangi guruh o'lchov turini tanlang:", chat_id, msg_id, reply_markup=markup)
        return

    elif data.startswith("adm_ng_") and user_id == MASTER_ADMIN_ID:
        unit = data.split("_")[2]
        set_user_state(user_id, "WAITING_FOR_NEW_GROUP_NAME", {"unit": unit})
        bot.send_message(chat_id, "📝 Yangi guruhga nom bering:")
        return

    elif data == "adm_exist_g" and user_id == MASTER_ADMIN_ID:
        conn = get_db_connection()
        groups = conn.execute("SELECT * FROM groups").fetchall()
        conn.close()
        if not groups:
            bot.send_message(chat_id, "Bazada guruh yo'q!")
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups: markup.add(types.InlineKeyboardButton(g['name'], callback_data=f"adm_selg_{g['id']}"))
        bot.edit_message_text("Mavjud guruhni tanlang:", chat_id, msg_id, reply_markup=markup)
        return

    elif data.startswith("adm_selg_") and user_id == MASTER_ADMIN_ID:
        g_id = int(data.split("_")[2])
        set_user_state(user_id, "WAITING_FOR_PRODUCT_PHOTO", {"group_id": g_id})
        bot.send_message(chat_id, "🖼 Tovar rasmini yuboring:")
        return

    # ---- FOYDALANUVCHILAR UCHUN CALLBACKLAR ----
    if data.startswith("view_group_"):
        g_id = int(data.split("_")[2])
        conn = get_db_connection()
        prods = conn.execute("SELECT id, name FROM products WHERE group_id = ?", (g_id,)).fetchall()
        conn.close()
        if not prods:
            bot.send_message(chat_id, "Bu guruh bo'sh.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in prods: markup.add(types.InlineKeyboardButton(f"📦 {p['name']}", callback_data=f"view_prod_{p['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_groups"))
        bot.edit_message_text("⬇️ Mahsulotni tanlang:", chat_id, msg_id, reply_markup=markup)
        return

    elif data == "back_to_groups":
        conn = get_db_connection()
        groups = conn.execute("SELECT * FROM groups").fetchall()
        conn.close()
        markup = types.InlineKeyboardMarkup(row_width=2)
        for g in groups: markup.add(types.InlineKeyboardButton(g['name'], callback_data=f"view_group_{g['id']}"))
        bot.edit_message_text("📁 Kerakli mahsulot guruhini tanlang:", chat_id, msg_id, reply_markup=markup)
        return

    elif data.startswith("view_prod_"):
        p_id = int(data.split("_")[2])
        conn = get_db_connection()
        p = conn.execute("SELECT * FROM products WHERE id = ?", (p_id,)).fetchone()
        conn.close()
        if not p:
            bot.send_message(chat_id, "Tovar topilmadi.")
            return
        bot.delete_message(chat_id, msg_id)
        
        caption = (
            f"📦 **{p['name']}**\nNarxi: {p['price']:,} so'm\n🚚 Dastavka: {p['delivery_price']:,} so'm\n\n"
            f"📝 **Tavsif:** {p['description']}\n\n"
            f"✍️ Miqdorini qop yoki kgda yozib yuboring (Masalan: `2` yoki `15kg`):"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_groups"))
        set_user_state(user_id, "WAITING_FOR_QUANTITY", {"prod_id": p_id})
        bot.send_photo(chat_id, p['photo_id'], caption=caption, parse_mode="Markdown", reply_markup=markup)
        return

    elif data.startswith("buy_"):
        parts = data.split("_")
        p_id, unit, qty = int(parts[1]), parts[2], float(parts[3])
        conn = get_db_connection()
        cursor = conn.cursor()
        row = cursor.execute("SELECT id, quantity FROM cart WHERE user_id = ? AND product_id = ? AND unit = ?", (user_id, p_id, unit)).fetchone()
        if row: cursor.execute("UPDATE cart SET quantity = ? WHERE id = ?", (row['quantity'] + qty, row['id']))
        else: cursor.execute("INSERT INTO cart (user_id, product_id, quantity, unit) VALUES (?, ?, ?, ?)", (user_id, p_id, qty, unit))
        conn.commit()
        conn.close()
        bot.edit_message_text("🛒 Tovar savatga joylandi. Xaridni davom ettirishingiz mumkin.", chat_id, msg_id)
        return

    elif data == "clear_cart":
        conn = get_db_connection()
        conn.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text("🗑 Savat tozalandi.", chat_id, msg_id)
        return

    elif data == "checkout_cart":
        conn = get_db_connection()
        cursor = conn.cursor()
        items = cursor.execute("SELECT c.quantity, c.unit, p.name, p.price, p.qop_weight, p.delivery_price FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = ?", (user_id,)).fetchall()
        if not items:
            conn.close()
            return
            
        # Admin xabari yasashda mijoz profiliga link (Lichka) biriktiramiz
        order_text = f"🔔 **Yangi Buyurtma!**\n👤 Xaridor: [{call.from_user.first_name}](tg://user?id={user_id})\n🆔 ID: `{user_id}`\n\n"
        total, total_delivery, items_data = 0, 0, []
        for i in items:
            cost = (i['price'] * i['quantity']) if i['unit'] == 'qop' else ((i['price']/i['qop_weight'] if i['qop_weight'] > 0 else i['price']) * i['quantity'])
            total += cost
            total_delivery += i['delivery_price']
            items_data.append({"name": i['name'], "qty": i['quantity'], "unit": i['unit'], "cost": cost})
            order_text += f"▪️ {i['name']} - {i['quantity']} {i['unit'].upper()} = {int(cost):,} so'm\n"
        
        final_total = total + total_delivery
        order_text += f"\n🚚 Yetkazib berish: {int(total_delivery):,} so'm\n💰 Jami: {int(final_total):,} so'm"
        
        cursor.execute("INSERT INTO orders (user_id, items_json, total_price, ordered_at, status) VALUES (?, ?, ?, ?, 'pending')",
                       (user_id, json.dumps(items_data), final_total, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        order_id = cursor.lastrowid
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(types.InlineKeyboardButton("✅ Qabul qilish", callback_data=f"accept_ord_{order_id}_{user_id}"),
                         types.InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_ord_{order_id}_{user_id}"))
        for ad_id in ORDER_ADMINS:
            try: bot.send_message(ad_id, order_text, reply_markup=admin_markup, parse_mode="Markdown")
            except: pass
        bot.delete_message(chat_id, msg_id)
        bot.send_message(chat_id, "✅ **Buyurtmangiz yuborildi. Operatorlar tez orada bog'lanishadi.**", reply_markup=get_admin_contacts_markup(), parse_mode="Markdown")
        return

    # BUYURTMANI QABUL QILISH VA LOKATSIYA SO'RASH
    elif data.startswith("accept_ord_") or data.startswith("reject_ord_"):
        parts = data.split("_")
        action, order_id, client_id = parts[0], int(parts[2]), int(parts[3])
        conn = get_db_connection()
        cursor = conn.cursor()
        order = cursor.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if order and order['status'] != 'pending':
            conn.close()
            return
        new_status = 'accepted' if action == 'accept' else 'rejected'
        cursor.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        conn.commit()
        conn.close()
        
        if action == "accept":
            # Mijozdan manzil so'rash uchun maxsus tugma
            loc_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            loc_btn = types.KeyboardButton("📍 Lokatsiya yuborish", request_location=True)
            cancel_btn = types.KeyboardButton("🏠 Bosh menyu")
            loc_markup.add(loc_btn, cancel_btn)
            
            set_user_state(client_id, "WAITING_FOR_LOCATION_OR_ADDRESS", {"order_id": order_id})
            
            try:
                bot.send_message(client_id, "✅ **Buyurtmangiz ma'muriyat tomonidan qabul qilindi!** 🎉\n\n📍 Iltimos, pastdagi tugma orqali joylashuvingizni (Live Location) yuboring yoki manzilni to'liq matn qilib tushuntirib yozing:", reply_markup=loc_markup, parse_mode="Markdown")
            except: pass
            
            # Admindagi xabarni o'zgartirish (Yozish tugmasi va Yetkazib berildi qo'shiladi)
            admin_delivered_markup = types.InlineKeyboardMarkup()
            admin_delivered_markup.add(types.InlineKeyboardButton("✅ Yetkazib berildi", callback_data=f"delivered_ord_{order_id}_{client_id}"))
            bot.edit_message_text(f"{call.message.text}\n\n**HOLATI: 🏃‍♂️ YETKAZIB BERILYAPTI (QABUL QILINDI)**\n💬 Mijoz profili: [Lichkaga yozish](tg://user?id={client_id})", chat_id, msg_id, reply_markup=admin_delivered_markup, parse_mode="Markdown")
        else:
            try: bot.send_message(client_id, "❌ Buyurtmangiz rad etildi.", reply_markup=get_admin_contacts_markup())
            except: pass
            bot.edit_message_text(f"{call.message.text}\n\n**HOLATI: ❌ RAD ETILDI**", chat_id, msg_id)
        return

    # YANGI: YETKAZIB BERILDI TUGMASI BOSILGANDA
    elif data.startswith("delivered_ord_"):
        parts = data.split("_")
        order_id, client_id = int(parts[2]), int(parts[3])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'delivered' WHERE order_id = ?", (order_id,))
        conn.commit()
        conn.close()
        
        updated_text = call.message.text.replace("🏃‍♂️ YETKAZIB BERILYAPTI (QABUL QILINDI)", "🏁 YETKAZIB BERILDI (YAKUNLANDI)")
        bot.edit_message_text(updated_text, chat_id, msg_id, parse_mode="Markdown")
        
        try:
            bot.send_message(client_id, "🎉 **Sizning buyurtmangiz muvaffaqiyatli yetkazib berildi!**\n\nTulpor savdo markazini tanlaganingiz uchun tashakkur! 😊 Boshqa xaridlar orqali yana kutib qolamiz.", parse_mode="Markdown")
        except: pass
        return

# =====================================================================
# 8. TOVAR HAJMINI TO'G'RIDAN-TO'G'RI MATNDAN HISOBLASH
# =====================================================================
def process_direct_quantity_input(message, p_id):
    text = message.text.lower().replace(" ", "").replace(",", ".")
    try:
        qty = float(text.replace("kg", "")) if "kg" in text else float(text)
        unit = "kg" if "kg" in text else "qop"
        if qty <= 0: raise ValueError
        
        conn = get_db_connection()
        p = conn.execute("SELECT price, qop_weight FROM products WHERE id = ?", (p_id,)).fetchone()
        conn.close()
        if not p: return

        total_p = (p['price'] * qty) if unit == 'qop' else ((p['price'] / p['qop_weight'] if p['qop_weight'] > 0 else p['price']) * qty)
        format_qty = int(qty) if qty == int(qty) else qty
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton(f"🛒 {format_qty} {unit.upper()} = {int(total_p):,} so'm (Savatga qo'shish)", callback_data=f"buy_{p_id}_{unit}_{qty}"),
                   types.InlineKeyboardButton("❌ Bekor qilish", callback_data="back_to_groups"))
        
        clear_user_state(message.from_user.id)
        bot.send_message(message.chat.id, f"Siz **{format_qty} {unit.upper()}** tanladingiz. Tasdiqlang:", parse_mode="Markdown", reply_markup=markup)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Noto'g'ri qiymat! Iltimos faqat raqam kiriting (Masalan: `3` yoki `25kg`):")

# =====================================================================
# 9. INFINITY POLLING (BOTNI ISHGA TUSHIRISH)
# =====================================================================
if __name__ == "__main__":
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=15)
        except Exception as e:
            logger.error(f"Polling xatolik: {e}")
            time.sleep(5)
