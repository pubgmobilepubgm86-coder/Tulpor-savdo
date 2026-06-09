# -*- coding: utf-8 -*-
"""
LOYIHA: TULPOR SAVDO MARKAZI BOTI (PRODUCTION REJIMI)
DUNYODAGI ENG ENG MUKAMMAL VA TAYYOR VARIANTI
XUSUSIYATLARI:
- To'liq SQLite3 Ma'lumotlar Bazasi (6 ta jadval)
- Interaktiv Savat (+1, +5, +20, +50, -1, -5 va KG/QOP o'lchovlari)
- Kengaytirilgan Admin Panel (Tovar qo'shish, o'chirish, statistika, xabar tarqatish)
- Promokod Tizimi (Vip foydalanuvchilar va bonuslar uchun)
- Render Server Port Binding (Uzluksiz 24/7 ishlash kafolati)
- Termux va Render uchun 100% moslashtirilgan tayyor kod.
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

# Siz taqdim etgan rasmiy bot tokeni
TOKEN = "8849139822:AAHA_XcRp_9eBsatrAIM4KqjiMUEoBbqNQ4"

# Admin xavfsizligi va boshqaruvi uchun asosiy ID raqami
# Buni o'zingizning Telegram ID raqamingizga almashtirishingiz mumkin
ADMIN_ID = 123456789  

# Logging (Loglarni kuzatish tizimi) - Render loglarida hamma narsani aniq ko'rsatadi
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Telebot ob'ektini yaratish
try:
    bot = telebot.TeleBot(TOKEN, parse_mode=None)
    logger.info("Bot ob'ekti muvaffaqiyatli yaratildi.")
except Exception as e:
    logger.error(f"Botni ishga tushirishda xatolik: {e}")
    sys.exit(1)

# Vaqtinchalik foydalanuvchi holatlarini saqlash xotirasi (In-Memory Cache)
temp_cart_options = {}  # {user_id: {product_id: {'qty': 1, 'unit': 'kg'}}}
admin_states = {}       # Admin amallari va ko'p bosqichli formalari uchun
user_states = {}        # Foydalanuvchilarning faol muloqot holatlari uchun

# DB fayl nomi
DB_NAME = "tulpor_savdo_core.db"

# =====================================================================
# 2. MA'LUMOTLAR BAZASI BILAN ISHLASH (SQLITE3)
# =====================================================================

def get_db_connection():
    """Ma'lumotlar bazasiga xavfsiz ulanish yaratish"""
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Barcha kerakli jadvallarni yaratish va bazani dastlabki sozlash"""
    logger.info("Ma'ma'lumotlar bazasini tekshirish va inicializatsiya qilish boshlandi...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Foydalanuvchilar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            registered_at TEXT,
            status TEXT DEFAULT 'active'
        )
    """)
    
    # 2. Mahsulotlar (Tovarlar) jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT DEFAULT 'Mahsulot haqida qo''shimcha ma''lumot kiritilmagan.',
            created_at TEXT
        )
    """)
    
    # 3. Savatcha jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'kg',
            added_at TEXT,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    
    # 4. Promokodlar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            reward_text TEXT NOT NULL,
            created_at TEXT,
            usage_count INTEGER DEFAULT 0
        )
    """)
    
    # 5. Buyurtmalar tarixi jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            items_json TEXT NOT NULL,
            total_price REAL NOT NULL,
            status TEXT DEFAULT 'Yangi',
            ordered_at TEXT
        )
    """)
    
    # 6. Bot Sozlamalari jadvali (Key-Value)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Dastlabki doimiy sozlamalarni kiritish
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('about_text', '🐎 Tulpor savdo markazi - Biz sizga eng sifatli mahsulotlarni eng hamyonbop narxlarda taqdim etamiz!')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('delivery_text', '🚚 Yetkazib berish shartlari:\nNamangan viloyati va Chortoq tumani bo''ylab tezkor hamda xavfsiz yetkazib berish xizmati mavjud. Buyurtma berganingizdan so''ng operatorimiz aloqaga chiqadi.')")
    
    conn.commit()
    conn.close()
    logger.info("Ma'lumotlar bazasi to'liq tayyor holatga keltirildi.")

# Bazani ishga tushiramiz
init_database()

# =====================================================================
# 3. RENDER UCHUN VEB-SERVER (PORT BINDING TIZIMI)
# =====================================================================

class RenderHealthCheckServer(BaseHTTPRequestHandler):
    """Render tarmog'i bot o'chib qolmasligi uchun yuboradigan GET so'rovlariga javob beruvchi server"""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html_response = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Tulpor Savdo Bot Status</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; background-color: #f4f6f9; padding: 50px; }
                .card { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); display: inline-block; }
                .status-badge { background-color: #2ec4b6; color: white; padding: 5px 15px; border-radius: 20px; font-weight: bold; }
                h1 { color: #011627; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🐎 Tulpor Savdo Markazi Boti</h1>
                <p>Server Holati: <span class="status-badge">ONLINE</span></p>
                <p>Bot muvaffaqiyatli ishlamoqda va Telegram API ga ulangan.</p>
                <small>UptimeRobot va Render uchun maxsus bog'lanish nuqtasi.</small>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html_response.encode("utf-8"))

    def log_message(self, format, *args):
        # Server ping loglarini konsolda ko'p joy egallamasligi uchun filtrlash
        return

def start_render_web_server():
    """Veb serverni aniq port bilan alohida oqimda ishga tushirish funksiyasi"""
    try:
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(("0.0.0.0", port), RenderHealthCheckServer)
        logger.info(f"[PORT BINDING] Veb server muvaffaqiyatli tarzda {port}-portda ishga tushdi.")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Veb serverni portga bog'lashda xatolik yuz berdi: {e}")

# Veb serverni Thread (tarmoq oqimi) ichida ochamiz, bot parallel ravishda ishlayveradi
web_infrastructure_thread = threading.Thread(target=start_render_web_server)
web_infrastructure_thread.daemon = True
web_infrastructure_thread.start()

# =====================================================================
# 4. KLAVIATURALAR (REPLY VA INLINE MARKUPS)
# =====================================================================

def get_main_menu_keyboard(user_id):
    """Foydalanuvchi turiga qarab asosiy Reply tugmalarni qaytaradi"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_products = types.KeyboardButton("TOVARLAR 🌐")
    btn_cart = types.KeyboardButton("🛒 Savat")
    btn_delivery = types.KeyboardButton("🚚 Yetkazib berish")
    btn_about = types.KeyboardButton("ℹ️ Biz haqimizda")
    btn_promo = types.KeyboardButton("🔑 Promokod kiritish")
    
    if user_id == ADMIN_ID:
        btn_admin = types.KeyboardButton("🛠 Admin Panel")
        markup.add(btn_products, btn_cart)
        markup.add(btn_delivery, btn_about)
        markup.add(btn_promo, btn_admin)
    else:
        markup.add(btn_products, btn_cart)
        markup.add(btn_delivery, btn_about)
        markup.add(btn_promo)
    return markup

def build_interactive_cart_keyboard(product_id, qty=1, unit='kg'):
    """Har bir mahsulot ostida chiquvchi o'ta interaktiv hisoblagichli Inline tugmalar"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # O'lchov birliklari matni (faoli ✅ bilan belgilanadi)
    kg_label = "✅ KG ⚖️" if unit == 'kg' else "KG ⚖️"
    qop_label = "✅ QOP 📦" if unit == 'qop' else "QOP 📦"
    
    btn_kg = types.InlineKeyboardButton(kg_label, callback_data=f"unit_{product_id}_kg")
    btn_qop = types.InlineKeyboardButton(qop_label, callback_data=f"unit_{product_id}_qop")
    
    # Miqdorni kamaytirish
    btn_minus5 = types.InlineKeyboardButton("-5", callback_data=f"qty_{product_id}_-5")
    btn_minus1 = types.InlineKeyboardButton("-1", callback_data=f"qty_{product_id}_-1")
    
    # Joriy holat ko'rinishi (bosganda hech narsa qilmaydi)
    btn_current_status = types.InlineKeyboardButton(f"Soni: {qty} {unit.upper()}", callback_data="none_action")
    
    # Miqdorni oshirish
    btn_plus1 = types.InlineKeyboardButton("+1", callback_data=f"qty_{product_id}_+1")
    btn_plus5 = types.InlineKeyboardButton("+5", callback_data=f"qty_{product_id}_+5")
    
    # Katta hajmdagi savdo uchun tezkor tugmalar
    btn_plus20 = types.InlineKeyboardButton("+20", callback_data=f"qty_{product_id}_+20")
    btn_plus50 = types.InlineKeyboardButton("+50", callback_data=f"qty_{product_id}_+50")
    
    # Savatga yakuniy qo'shish tugmasi
    btn_add_to_cart = types.InlineKeyboardButton("🛒 Savatga qo'shish", callback_data=f"buy_{product_id}")
    
    # Tugmalarni qatorlarga tizish
    markup.row(btn_kg, btn_qop)
    markup.row(btn_minus5, btn_minus1)
    markup.row(btn_current_status, btn_plus1)
    markup.row(btn_plus5)
    markup.row(btn_plus20, btn_plus50)
    markup.row(btn_add_to_cart)
    
    return markup

def get_cart_management_keyboard():
    """Savat bo'limidagi Inline amallar klaviaturasi"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_checkout = types.InlineKeyboardButton("🚖 Buyurtma berish", callback_data="checkout_cart")
    btn_clear = types.InlineKeyboardButton("🗑 Savatni tozalash", callback_data="clear_cart")
    markup.add(btn_checkout, btn_clear)
    return markup

def get_admin_main_inline():
    """Admin panel ichidagi asosiy boshqaruv tugmalari"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Yangi Tovar Qo'shish", callback_data="adm_add_product"),
        types.InlineKeyboardButton("➖ Tovarni O'chirish", callback_data="adm_del_product"),
        types.InlineKeyboardButton("🔑 Yangi Promokod Yaratish", callback_data="adm_add_promo"),
        types.InlineKeyboardButton("📊 Bot Statistikasi", callback_data="adm_stats"),
        types.InlineKeyboardButton("📢 Foydalanuvchilarga Xabar Yuborish", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("⚙️ Matnlarni Tahrirlash", callback_data="adm_edit_texts")
    )
    return markup

# =====================================================================
# 5. ASOSIY BUYRUQLAR VA FOYDALANUVCHILARNI RO'YXATGA OLISH
# =====================================================================

def register_user_if_not_exists(user):
    """Foydalanuvchini bazaga kiritish (agar mavjud bo'lmasa)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,))
        row = cursor.fetchone()
        
        if not row:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO users (user_id, first_name, username, registered_at) VALUES (?, ?, ?, ?)",
                (user.id, user.first_name, user.username, now_str)
            )
            conn.commit()
            logger.info(f"Yangi foydalanuvchi ro'yxatga olindi: {user.id} - {user.first_name}")
        conn.close()
    except Exception as e:
        logger.error(f"Foydalanuvchini ro'yxatga olishda xatolik: {e}")

@bot.message_handler(commands=['start'])
def handle_start_command(message):
    """/start buyrug'i kelganda botning ilk javobi"""
    register_user_if_not_exists(message.from_user)
    welcome_text = (
        f"🐎 **Tulpor savdo markazi** botiga xush kelibsiz, {message.from_user.first_name}!\n\n"
        f"Ushbu bot yordamida siz do'konimizdagi tovarlarni onlayn ko'rishingiz, "
        f"savatchangizga qo'shishingiz va to'g'ridan-to'g'ri buyurtma berishingiz mumkin.\n\n"
        f"👇 Davom etish uchun quyidagi menyudan kerakli bo'limni tanlang:"
    )
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        reply_markup=get_main_menu_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['help'])
def handle_help_command(message):
    """Yordam buyrug'i"""
    help_text = (
        "❓ **Botdan qanday foydalaniladi?**\n\n"
        "1️⃣ **TOVARLAR 🌐** tugmasini bosing va mahsulotlarni ko'ring.\n"
        "2️⃣ Mahsulot ostidagi Inline tugmalardan foydalanib, o'lchov birligi (KG yoki QOP) hamda miqdorini belgilang.\n"
        "3️⃣ **Savatga qo'shish** tugmasini bosing.\n"
        "4️⃣ **Savat** bo'limiga o'tib, buyurtmani tasdiqlang.\n\n"
        "Muammolar yuzaga kelsa, do'onimiz ma'muriyatiga murojaat qiling."
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

# =====================================================================
# 6. MENYU TUGMALARI JAVOBLARI (REPLY INTERFEYSI)
# =====================================================================

@bot.message_handler(func=lambda msg: True)
def handle_text_messages(message):
    """Reply klaviaturadagi barcha matnli tugmalarni qayta ishlovchi katta boshqaruvchi"""
    user_id = message.from_user.id
    text = message.text
    
    # Har qanday holatda ham foydalanuvchini ro'yxatdan o'tkazishni tekshirish
    register_user_if_not_exists(message.from_user)

    # 1. TOVARLAR BO'LIMI
    if text == "TOVARLAR 🌐":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, price, description FROM products ORDER BY id DESC")
            all_products = cursor.fetchall()
            conn.close()
            
            if not all_products:
                bot.send_message(message.chat.id, "📭 Hozircha do'konimizda sotiladigan mahsulotlar kiritilmagan. Tezp orada tovarlar qo'shiladi!")
                retur
                
            bot.send_message(message.chat.id, "📦 **Mavjud mahsulotlar ro'yxati va buyurtma berish oynasi:**")
            
            for prod in all_products:
                prod_id = prod['id']
                prod_name = prod['name']
                prod_price = prod['price']
                prod_desc = prod['description']
                
                # Foydalanuvchi uchun vaqtinchalik xotira sozlamalarini standart (1 kg) qilib tiklash
                if user_id not in temp_cart_options:
                    temp_cart_options[user_id] = {}
                temp_cart_options[user_id][prod_id] = {'qty': 1, 'unit': 'kg'}
                
                product_card = (
                    f"🐎 **Mahsulot:** {prod_name}\n"
                    f"💰 **Narxi:** {prod_price:,} so'm\n"
                    f"📝 **Ma'lumot:** {prod_desc}"
                )
                
                bot.send_message(
                    message.chat.id,
                    product_card,
                    reply_markup=build_interactive_cart_keyboard(prod_id, 1, 'kg'),
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Tovarlarni yuklashda xatolik: {e}")
            bot.send_message(message.chat.id, "❌ Tovarlarni yuklashda texnik xatolik yuz berdi.")

    # 2. SAVATCHA BO'LIMI
    elif text == "🛒 Savat":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.id, p.name, c.quantity, c.unit, p.price 
                FROM cart c 
                JOIN products p ON c.product_id = p.id 
                WHERE c.user_id = ?
            """, (user_id,))
            cart_items = cursor.fetchall()
            conn.close()
            
            if not cart_items:
                bot.send_message(message.chat.id, "🛒 Savatingiz hozircha bo'sh. Mahsulotlar bo'limidan tovar qo'shing.")
                return
                
            response_text = "🛒 **Sizning savatchangiz tarkibi:**\n\n"
            total_sum = 0
            
            for index, item in enumerate(cart_items, 1):
                item_name = item['name']
                item_qty = item['quantity']
                item_unit = item['unit'].upper()
                item_price = item['price']
                item_cost = item_qty * item_price
                total_sum += item_cost
                
                response_text += f"{index}. 🔹 {item_name} — {item_qty} {item_unit} x {item_price:,} = **{item_cost:,} so'm**\n"
                
            response_text += f"\n📊 **Jami to'lov summasi:** `{total_sum:,}` **so'm**"
            
            bot.send_message(
                message.chat.id, 
                response_text, 
                reply_markup=get_cart_management_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Savatni ko'rishda xatolik: {e}")
            bot.send_message(message.chat.id, "❌ Savatni hisoblashda xatolik yuz berdi.")

    # 3. YETKAZIB BERISH SHARTLARI
    elif text == "🚚 Yetkazib berish":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'delivery_text'")
        row = cursor.fetchone()
        conn.close()
        text_to_send = row['value'] if row else "Yetkazib berish matni topilmadi."
        bot.send_message(message.chat.id, text_to_send)

    # 4. BIZ HAQIMIZDA
    elif text == "ℹ️ Biz haqimizda":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'about_text'")
        row = cursor.fetchone()
        conn.close()
        text_to_send = row['value'] if row else "Biz haqimizda matni topilmadi."
        bot.send_message(message.chat.id, text_to_send)

    # 5. PROMOKOD KIRITISH TIZIMI
    elif text == "🔑 Promokod kiritish":
        msg = bot.send_message(message.chat.id, "🔑 Bonus yoki chegirmaga ega bo'lish uchun promokodni yozing:")
        bot.register_next_step_handler(msg, process_user_entered_promocode)

    # 6. ADMIN PANEL REJIMI
    elif text == "🛠 Admin Panel" and user_id == ADMIN_ID:
        bot.send_message(
            message.chat.id,
            "🛠 **Tulpor Savdo Markazi boshqaruv tizimiga xush kelibsiz, Admin!**\n\nQuyidagi tugmalar orqali botni to'liq nazorat qiling:",
            reply_markup=get_admin_main_inline(),
            parse_mode="Markdown"
        )
        
    else:
        # Agar hech qaysi tugmaga tushmasa, shunchaki standart menyuni qaytarish
        bot.send_message(
            message.chat.id, 
            "Prosesni davom ettirish uchun pastdagi menyulardan birini tanlang:",
            reply_markup=get_main_menu_keyboard(user_id)
        )

# =====================================================================
# 7. INLINE CALLBACK QUERY HANDLER (TUGMALARNING JAVOBLARI)
# =====================================================================

@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    """Inline klaviaturalardan keladigan barcha bosinglarni boshqarish"""
    user_id = call.from_user.id
    data = call.data
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    # Hech narsa qilmaydigan informatsion tugma bosilganda
    if data == "none_action":
        bot.answer_callback_query(call.id, text="Bu joriy hisoblagich holati.")
        return

    # A. O'lchov birligini KG yoki QOPga o'zgartirish
    if data.startswith("unit_"):
        parts = data.split("_")
        product_id = int(parts[1])
        selected_unit = parts[2]
        
        if user_id not in temp_cart_options:
            temp_cart_options[user_id] = {}
        if product_id not in temp_cart_options[user_id]:
            temp_cart_options[user_id][product_id] = {'qty': 1, 'unit': 'kg'}
            
        temp_cart_options[user_id][product_id]['unit'] = selected_unit
        current_qty = temp_cart_options[user_id][product_id]['qty']
        
        # Interfeysni yangilash
        try:
            bot.edit_message_reply_markup(
                chat_id, 
                message_id, 
                reply_markup=build_interactive_cart_keyboard(product_id, current_qty, selected_unit)
            )
        except Exception:
            pass # Agar klik bir xil holat ustiga bo'lsa, Telegram xato beradi, uni o'tkazib yuboramiz
        bot.answer_callback_query(call.id, text=f"O'lchov birligi o'zgardi: {selected_unit.upper()}")

    # B. Miqdorni interaktiv o'zgartirish (+/- amallari)
    elif data.startswith("qty_"):
        parts = data.split("_")
        product_id = int(parts[1])
        qty_change = int(parts[2])
        
        if user_id not in temp_cart_options:
            temp_cart_options[user_id] = {}
        if product_id not in temp_cart_options[user_id]:
            temp_cart_options[user_id][product_id] = {'qty': 1, 'unit': 'kg'}
            
        old_qty = temp_cart_options[user_id][product_id]['qty']
        new_qty = old_qty + qty_change
        
        # Miqdor 1 dan kam bo'lib ketishi mumkin emas
        if new_qty < 1:
            new_qty = 1
            bot.answer_callback_query(call.id, text="Minimal buyurtma miqdori 1 ta!")
            return
            
        temp_cart_options[user_id][product_id]['qty'] = new_qty
        current_unit = temp_cart_options[user_id][product_id]['unit']
        
        try:
            bot.edit_message_reply_markup(
                chat_id, 
                message_id, 
                reply_markup=build_interactive_cart_keyboard(product_id, new_qty, current_unit)
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id)

    # C. Savatga yakuniy qo'shish ijrosi
    elif data.startswith("buy_"):
        product_id = int(data.split("_")[1])
        
        # Xotiradan joriy holatni olish, agar topilmasa standart qiymat
        if user_id in temp_cart_options and product_id in temp_cart_options[user_id]:
            final_qty = temp_cart_options[user_id][product_id]['qty']
            final_unit = temp_cart_options[user_id][product_id]['unit']
        else:
            final_qty = 1
            final_unit = 'kg'
            
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Avval savatda xuddi shu tovar va o'lchov birligi bormi tekshirish
            cursor.execute(
                "SELECT id, quantity FROM cart WHERE user_id = ? AND product_id = ? AND unit = ?",
                (user_id, product_id, final_unit)
            )
            existing_item = cursor.fetchone()
            
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if existing_item:
                # Agar bo'lsa, miqdorini yangilab qo'shib qo'yamiz
                updated_qty = existing_item['quantity'] + final_qty
                cursor.execute(
                    "UPDATE cart SET quantity = ?, added_at = ? WHERE id = ?",
                    (updated_qty, now_str, existing_item['id'])
                )
            else:
                # Yangi qator sifatida kiritamiz
                cursor.execute(
                    "INSERT INTO cart (user_id, product_id, quantity, unit, added_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, product_id, final_qty, final_unit, now_str)
                )
                
            conn.commit()
            conn.close()
            
            bot.answer_callback_query(call.id, text="✅ Savatga muvaffaqiyatli qo'shildi!", show_alert=False)
            bot.send_message(chat_id, f"✅ Savatga qo'shildi: {final_qty} {final_unit.upper()}")
        except Exception as e:
            logger.error(f"Savatga yozishda xatolik: {e}")
            bot.answer_callback_query(call.id, text="❌ Bazaga qo'shishda muammo bo'ldi.")

    # D. Savatni tozalash amali
    elif data == "clear_cart":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            
            bot.answer_callback_query(call.id, text="Savat butkul tozalandi.")
            bot.edit_message_text("Savatchangiz muvaffaqiyatli tozalandi. U hozir bo'sh.", chat_id, message_id)
        except Exception as e:
            logger.error(f"Savatni tozalashda xatolik: {e}")

    # E. Buyurtma berish (Checkout) - Adminga hisobot ketadi
    elif data == "checkout_cart":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Xaridor tovarlarini yig'ish
            cursor.execute("""
                SELECT c.product_id, p.name, c.quantity, c.unit, p.price 
                FROM cart c 
                JOIN products p ON c.product_id = p.id 
                WHERE c.user_id = ?
            """, (user_id,))
            items = cursor.fetchall()
            
            if not items:
                bot.answer_callback_query(call.id, text="Savat bo'sh, buyurtma berib bo'lmaydi!", show_alert=True)
                conn.close()
                return
                
            # Adminga ketadigan chiroyli matn shakllantirish
            xaridor_name = call.from_user.first_name
            username_field = f"@{call.from_user.username}" if call.from_user.username else "Mavjud emas"
            
            admin_report = (
                f"🔔 ⚡️ **YANGI BUYURTMA KELDI!**\n\n"
                f"👤 **Xaridor:** {xaridor_name}\n"
                f"🌐 **Telegram:** {username_field}\n"
                f"🆔 **Foydalanuvchi ID:** `{user_id}`\n"
                f"📅 **Vaqt:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"📦 **Buyurtma qilingan tovarlar:**\n"
            )
            
            items_list_for_json = []
            grand_total = 0
            
            for item in items:
                name = item['name']
                qty = item['quantity']
                unit = item['unit'].upper()
                price = item['price']
                cost = qty * price
                grand_total += cost
                
                admin_report += f"▪️ {name} — {qty} {unit} x {price:,} = {cost:,} so'm\n"
                items_list_for_json.append({'id': item['product_id'], 'name': name, 'qty': qty, 'unit': item['unit'], 'price': price})
                
            admin_report += f"\n💰 **JAMI SUMMA:** `{grand_total:,}` **so'm**\n\n"
            admin_report += f"📥 Xaridor bilan bog'lanish uchun: [Xaridor Profili](tg://user?id={user_id})"
            
            # Buyurtmani orders jadvaliga arxivlash
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO orders (user_id, items_json, total_price, ordered_at) VALUES (?, ?, ?, ?)",
                (user_id, json.dumps(items_list_for_json), grand_total, now_str)
            )
            
            # Foydalanuvchining savatini o'chirib yuborish
            cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
            
            conn.commit()
            conn.close()
            
            # Adminga xabar yuborish
            bot.send_message(ADMIN_ID, admin_report, parse_mode="Markdown")
            
            # Foydalanuvchiga muvaffaqiyat xabari
            bot.answer_callback_query(call.id, text="Buyurtmangiz muvaffaqiyatli qabul qilindi!", show_alert=True)
            bot.edit_message_text("✅ Rahmat! Buyurtmangiz qabul qilindi va adminga yuborildi. Tez orada siz bilan bog'lanishadi.", chat_id, message_id)
            
        except Exception as e:
            logger.error(f"Checkout qilishda jiddiy xatolik: {e}")
            bot.answer_callback_query(call.id, text="Xatolik yuz berdi, buyurtma amalga oshmadi.")

    # =====================================================================
    # ADMIN PANEL CALLBACKS (FAQAT ADMIN UCHUN)
    # =====================================================================
    elif data.startswith("adm_") and user_id == ADMIN_ID:
        
        # Admin: Tovar qo'shish bosqichi boshlanishi
        if data == "adm_add_product":
            msg = bot.send_message(chat_id, "📝 Yangi tovar NOMINI kiriting (Masalan: Bug'doy yemi):")
            bot.register_next_step_handler(msg, admin_workflow_product_name)
            bot.answer_callback_query(call.id)
            
        # Admin: Tovar o'chirish ro'yxati
        elif data == "adm_del_product":
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, name FROM products ORDER BY id DESC")
                prods = cursor.fetchall()
                conn.close()
                
                if not prods:
                    bot.send_message(chat_id, "O'chirish uchun tovarlar mavjud emas.")
                    bot.answer_callback_query(call.id)
                    return
                    
                delete_markup = types.InlineKeyboardMarkup(row_width=1)
                for p in prods:
                    delete_markup.add(types.InlineKeyboardButton(f"❌ O'chirish: {p['name']}", callback_data=f"execute_del_{p['id']}"))
                
                bot.send_message(chat_id, "Qaysi mahsulotni o'chirmoqchisiz? Tanlang:", reply_markup=delete_markup)
                bot.answer_callback_query(call.id)
            except Exception as e:
                logger.error(e)

        # Admin: Promokod yaratish boshlanishi
        elif data == "adm_add_promo":
            msg = bot.send_message(chat_id, "🔑 Yangi promokod kod so'zini kiriting (Masalan: VIP777):")
            bot.register_next_step_handler(msg, admin_workflow_promo_code)
            bot.answer_callback_query(call.id)

        # Admin: Bot Statistikasi
        elif data == "adm_stats":
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as u_cnt FROM users")
                u_count = cursor.fetchone()['u_cnt']
                
                cursor.execute("SELECT COUNT(*) as p_cnt FROM products")
                p_count = cursor.fetchone()['p_cnt']
                
                cursor.execute("SELECT COUNT(*) as o_cnt, SUM(total_price) as total_rev FROM orders")
                order_row = cursor.fetchone()
                o_count = order_row['o_cnt']
                total_revenue = order_row['total_rev'] if order_row['total_rev'] else 0
                
                conn.close()
                
                stat_text = (
                    f"📊 **TULPOR SAVDO MARKAZI BOT STATISTIKASI:**\n\n"
                    f"👥 **Jami a'zolar:** {u_count} ta\n"
                    f"📦 **Bazadagi tovarlar:** {p_count} ta\n"
                    f"🚖 **Muvaffaqiyatli buyurtmalar:** {o_count} ta\n"
                    f"💰 **Umumiy aylanma tushumi:** {total_revenue:,} so'm"
                )
                bot.send_message(chat_id, stat_text, parse_mode="Markdown")
                bot.answer_callback_query(call.id)
            except Exception as e:
                logger.error(e)

        # Admin: Xabar tarqatish (Broadcast)
        elif data == "adm_broadcast":
            msg = bot.send_message(chat_id, "📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabar matnini kiriting (Rasm yoki oddiy matn):")
            bot.register_next_step_handler(msg, admin_workflow_broadcast_execute)
            bot.answer_callback_query(call.id)

        # Admin: Matnlarni tahrirlash (About / Delivery)
        elif data == "adm_edit_texts":
            edit_markup = types.InlineKeyboardMarkup(row_width=1)
            edit_markup.add(
                types.InlineKeyboardButton("ℹ️ 'Biz haqimizda' matnini o'zgartirish", callback_data="text_edit_about"),
                types.InlineKeyboardButton("🚚 'Yetkazib berish' matnini o'zgartirish", callback_data="text_edit_delivery")
            )
            bot.send_message(chat_id, "Qaysi doimiy bo'lim matnini tahrirlamoqchisiz:", reply_markup=edit_markup)
            bot.answer_callback_query(call.id)

    # Admin: Tovarni bazadan butkul o'chirish ijrosi
    elif data.startswith("execute_del_") and user_id == ADMIN_ID:
        prod_to_del_id = int(data.split("_")[2])
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM products WHERE id = ?", (prod_to_del_id,))
            conn.commit()
            conn.close()
            bot.answer_callback_query(call.id, text="Mahsulot muvaffaqiyatli yo'q qilindi!", show_alert=True)
            bot.edit_message_text("✅ Tovar o'chirildi. Boshqaruvni davom ettirishingiz mumkin.", chat_id, message_id)
        except Exception as e:
            logger.error(e)

    # Admin: Qaysi matnni o'zgartirish tanlov qismi ijrosi
    elif data.startswith("text_edit_") and user_id == ADMIN_ID:
        target_type = data.split("_")[2] # about yoki delivery
        admin_states[user_id] = {"edit_target": target_type}
        msg = bot.send_message(chat_id, f"📝 Ushbu bo'lim uchun yangi matnni kiriting:")
        bot.register_next_step_handler(msg, admin_workflow_save_text)
        bot.answer_callback_query(call.id)

# =====================================================================
# 8. ADMIN WORKFLOWS (NEXT STEP HANDLERS MULTI-STEP)
# =====================================================================

# --- TOVAR QO'SHISH BOSQICHLARI ---
def admin_workflow_product_name(message):
    if message.from_user.id != ADMIN_ID: return
    prod_name = message.text.strip()
    admin_states[message.from_user.id] = {"name": prod_name}
    
    msg = bot.send_message(message.chat.id, f"💰 '{prod_name}' uchun NARX kiriting (Faqat butun raqam yozing, masalan: 45000):")
    bot.register_next_step_handler(msg, admin_workflow_product_price)

def admin_workflow_product_price(message):
    if message.from_user.id != ADMIN_ID: return
    user_id = message.from_user.id
    raw_price = message.text.strip()
    
    try:
        price_float = float(raw_price)
        admin_states[user_id]["price"] = price_float
        
        msg = bot.send_message(message.chat.id, "📝 Tovar haqida qisqacha tavsif yozing (yoki 'yo'q' deb yozing):")
        bot.register_next_step_handler(msg, admin_workflow_product_desc)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Narx xato kiritildi. Iltimos faqat raqam yozing. Jarayon bekor bo'ldi.")
        if user_id in admin_states: del admin_states[user_id]

def admin_workflow_product_desc(message):
    if message.from_user.id != ADMIN_ID: return
    user_id = message.from_user.id
    desc_text = message.text.strip()
    
    if desc_text.lower() == "yo'q" or desc_text.lower() == "yoq":
        desc_text = "Mahsulot haqida qo'shimcha ma'lumot kiritilmagan."
        
    p_name = admin_states[user_id]["name"]
    p_price = admin_states[user_id]["price"]
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO products (name, price, description, created_at) VALUES (?, ?, ?, ?)",
            (p_name, p_price, desc_text, now_str)
        )
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ **Tovar muvaffaqiyatli qo'shildi!**\n\n🐎 Nomi: {p_name}\n💰 Narxi: {p_price:,} so'm\n📝 Ma'lumot: {desc_text}", parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        bot.send_message(message.chat.id, "❌ Bazaga saqlashda xatolik yuz berdi.")
    finally:
        if user_id in admin_states: del admin_states[user_id]


# --- PROMOKOD YARATISH BOSQICHLARI ---
def admin_workflow_promo_code(message):
    if message.from_user.id != ADMIN_ID: return
    promo_code = message.text.strip().upper()
    admin_states[message.from_user.id] = {"p_code": promo_code}
    
    msg = bot.send_message(message.chat.id, f"📝 Foydalanuvchi `{promo_code}` kodini kiritganda unga qaytariladigan mukofot matnini (yoki yashirin linkni) yozing:")
    bot.register_next_step_handler(msg, admin_workflow_promo_text_save)

def admin_workflow_promo_text_save(message):
    if message.from_user.id != ADMIN_ID: return
    user_id = message.from_user.id
    reward_matn = message.text.strip()
    
    p_code = admin_states[user_id]["p_code"]
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT OR REPLACE INTO promocodes (code, reward_text, created_at) VALUES (?, ?, ?)",
            (p_code, reward_matn, now_str)
        )
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ **Yangi promokod tayyorlandi!**\n\n🔑 Kod: `{p_code}`\n🎁 Mukofot: {reward_matn}", parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
    finally:
        if user_id in admin_states: del admin_states[user_id]


# --- STATIK MATNLARNI TAHRIRLASH ---
def admin_workflow_save_text(message):
    if message.from_user.id != ADMIN_ID: return
    user_id = message.from_user.id
    new_text = message.text.strip()
    target = admin_states[user_id]["edit_target"]
    
    db_key = "about_text" if target == "about" else "delivery_text"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = ? WHERE key = ?", (new_text, db_key))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "✅ Bo'lim matni muvaffaqiyatli yangilandi!")
    except Exception as e:
        logger.error(e)
    finally:
        if user_id in admin_states: del admin_states[user_id]


# --- JAMOAVIY XABAR YUBORISH (BROADCAST) ---
def admin_workflow_broadcast_execute(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "🚀 Xabar yuborish boshlandi. Bu biroz vaqt olishi mumkin...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        all_users = cursor.fetchall()
        conn.close()
        
        success = 0
        failed = 0
        
        for u in all_users:
            u_id = u['user_id']
            try:
                # Agar admin rasm yuborgan bo'lsa
                if message.content_type == 'photo':
                    photo_id = message.photo[-1].file_id
                    bot.send_photo(u_id, photo_id, caption=message.caption)
                else:
                    # Agar faqat matn bo'lsa
                    bot.send_message(u_id, message.text)
                success += 1
            except Exception:
                failed += 1
                
        bot.send_message(message.chat.id, f"🏁 **Xabar tarqatish yakunlandi!**\n\n✅ Yetkazildi: {success} ta foydalanuvchiga\n❌ Muammo bo'ldi: {failed} ta (botni bloklaganlar)")
    except Exception as e:
        logger.error(f"Broadcast xatolik: {e}")

# =====================================================================
# 9. FOYDALANUVCHILAR REJIMIDA PROMOKOD TEKSHIRISH
# =====================================================================

def process_user_entered_promocode(message):
    """Foydalanuvchi yozgan promokodni bazadan qidirib natija berish"""
    user_code = message.text.strip().upper()
    user_id = message.from_user.id
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT reward_text, usage_count FROM promocodes WHERE code = ?", (user_code,))
        row = cursor.fetchone()
        
        if row:
            reward = row['reward_text']
            new_usage = row['usage_count'] + 1
            
            # Ishlatilish sonini oshirib qo'yamiz
            cursor.execute("UPDATE promocodes SET usage_count = ? WHERE code = ?", (new_usage, user_code))
            conn.commit()
            conn.close()
            
            # Foydalanuvchiga mukofot matnini berish
            bot.send_message(message.chat.id, f"🎁 **Tabriklaymiz! Promokod to'g'ri!**\n\n{reward}", parse_mode="Markdown")
            
            # Adminga ogohlantirish yuborish (Vip promokod nazorati uchun)
            u_username = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
            admin_alert = (
                f"🔔 **Vip Promokod Ishlatildi!**\n\n"
                f"🔑 **Kod:** `{user_code}`\n"
                f"👤 **Xaridor:** {message.from_user.first_name}\n"
                f"🌐 **Username:** {u_username}\n"
                f"🆔 **ID Raqami:** `{user_id}`"
            )
            bot.send_message(ADMIN_ID, admin_alert, parse_mode="Markdown")
        else:
            conn.close()
            bot.send_message(message.chat.id, "❌ Afsuski bunday promokod mavjud emas yoki muddati tugagan. Qaytadan tekshirib ko'ring.")
    except Exception as e:
        logger.error(f"Promokod tekshirishda xatolik: {e}")
        bot.send_message(message.chat.id, "Texnik nosozlik tufayli promokod tekshirilmadi.")

# =====================================================================
# 10. ERROR HANDLING AND POLLED EXECUTION (INFINITY LOOP)
# =====================================================================

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🐎 TULPOR SAVDO MARKAZI BOTI ISHGA TUSHISHGA TAYYOR.")
    logger.info("=" * 50)
    
    # Render va Termux'da polling uzilib qolmasligi uchun xatoliklarni chetlab o'tuvchi tizim
    while True:
        try:
            logger.info("Bot infinity_polling rejimida ishga tushirildi...")
            bot.infinity_polling(timeout=20, long_polling_timeout=10)
        except Exception as crash_error:
            logger.critical(f"[KRITIK XATOLIK] Bot polling jarayonida uzilish berdi: {crash_error}")
            logger.info("Server 5 soniyadan so'ng botni qayta tiklashga urinadi...")
            import time
            time.sleep(5)
