import telebot
from telebot import types
import sqlite3

# =========================================================
# BOT SOZLAMALARI (TOKEN VA ADMIN ID'NGIZNI YOZING)
# =========================================================
TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 123456789  # Bu yerga o'zingizning Telegram ID raqamingizni kiriting

bot = telebot.TeleBot(TOKEN)

# =========================================================
# MA'LUMOTLAR BAZASINI INICIALIZATSIYA QILISH
# =========================================================
def init_db():
    conn = sqlite3.connect("tulpor_savdo.db")
    cursor = conn.cursor()
    # Tovar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)
    # Savat jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit TEXT NOT NULL
        )
    """)
    # Promokodlar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            reward_text TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Vaqtinchalik interaktiv holatlarni saqlash xotirasi
temp_cart_options = {}  # {user_id: {product_id: {'qty': 1, 'unit': 'kg'}}}
admin_states = {}       # Admin promokod qo'shish holati uchun

# =========================================================
# ASSOSIY INTERFEYS: REPLY KLAVIATURA
# =========================================================
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("TOVARLAR 🌐")
    btn2 = types.KeyboardButton("🛒 Savat")
    btn3 = types.KeyboardButton("🚚 Yetkazib berish")
    btn4 = types.KeyboardButton("ℹ️ Biz haqimizda")
    btn5 = types.KeyboardButton("🔑 Promokod kiritish")
    
    if user_id == ADMIN_ID:
        btn6 = types.KeyboardButton("🛠 Admin Panel")
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    else:
        markup.add(btn1, btn2, btn3, btn4, btn5)
    return markup

# INTERAKTIV SAVAT TUGMALARI (Skrinshotdagi kabi 100% aniqlikda)
def make_purchase_keyboard(product_id, qty=1, unit='kg'):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    kg_text = "✅ KG ⚖️" if unit == 'kg' else "KG ⚖️"
    qop_text = "✅ QOP 📦" if unit == 'qop' else "QOP 📦"
    
    btn_kg = types.InlineKeyboardButton(kg_text, callback_data=f"set_unit_{product_id}_kg")
    btn_qop = types.InlineKeyboardButton(qop_text, callback_data=f"set_unit_{product_id}_qop")
    
    btn_m5 = types.InlineKeyboardButton("-5", callback_data=f"ch_qty_{product_id}_-5")
    btn_m1 = types.InlineKeyboardButton("-1", callback_data=f"ch_qty_{product_id}_-1")
    
    btn_status = types.InlineKeyboardButton(f"Soni: {qty} {unit}", callback_data="nil")
    btn_p1 = types.InlineKeyboardButton("+1", callback_data=f"ch_qty_{product_id}_+1")
    
    btn_p5 = types.InlineKeyboardButton("+5", callback_data=f"ch_qty_{product_id}_+5")
    
    btn_p20 = types.InlineKeyboardButton("+20", callback_data=f"ch_qty_{product_id}_+20")
    btn_p50 = types.InlineKeyboardButton("+50", callback_data=f"ch_qty_{product_id}_+50")
    
    btn_add = types.InlineKeyboardButton("🛒 Savatga qo'shish", callback_data=f"add_to_cart_{product_id}")
    
    markup.row(btn_kg, btn_qop)
    markup.row(btn_m5, btn_m1)
    markup.row(btn_status, btn_p1)
    markup.row(btn_p5)
    markup.row(btn_p20, btn_p50)
    markup.row(btn_add)
    return markup

# =========================================================
# BOT BUYRUQLARI VA FINFSIYALARI
# =========================================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id,
        "🐎 Tulpor savdo markazi botiga xush kelibsiz!\nQuyidagi menyudan kerakli bo'limni tanlang:",
        reply_markup=main_menu(message.from_user.id)
    )

# ADMIN PANEL (Inline tugmalar orqali boshqarish)
@bot.message_handler(func=lambda msg: msg.text == "🛠 Admin Panel" and msg.from_user.id == ADMIN_ID)
def admin_panel(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_add = types.InlineKeyboardButton("➕ Tovar qo'shish", callback_data="admin_add_product")
    btn_del = types.InlineKeyboardButton("➖ Tovar ayirish (O'chirish)", callback_data="admin_delete_product")
    btn_promo = types.InlineKeyboardButton("🔑 Promokod qo'shish", callback_data="admin_add_promo")
    markup.add(btn_add, btn_del, btn_promo)
    
    bot.send_message(message.chat.id, "🛠 Admin panel bo'limiga xush kelibsiz. Kerakli amalni tanlang:", reply_markup=markup)

# =========================================================
# CALLBACK ISHLOVCHI (INLINE TUGMALAR JAVOBI)
# =========================================================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    if data == "nil":
        bot.answer_callback_query(call.id)
        return

    # 1. O'lchov birligini almashtirish (KG / QOP)
    if data.startswith("set_unit_"):
        parts = data.split("_")
        prod_id = int(parts[2])
        unit = parts[3]
        
        if user_id not in temp_cart_options:
            temp_cart_options[user_id] = {}
        if prod_id not in temp_cart_options[user_id]:
            temp_cart_options[user_id][prod_id] = {'qty': 1, 'unit': 'kg'}
            
        temp_cart_options[user_id][prod_id]['unit'] = unit
        qty = temp_cart_options[user_id][prod_id]['qty']
        
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=make_purchase_keyboard(prod_id, qty, unit))
        bot.answer_callback_query(call.id)

    # 2. Miqdorni o'zgartirish (-5, -1, +1, +5, +20, +50)
    elif data.startswith("ch_qty_"):
        parts = data.split("_")
        prod_id = int(parts[2])
        change = int(parts[3])
        
        if user_id not in temp_cart_options:
            temp_cart_options[user_id] = {}
        if prod_id not in temp_cart_options[user_id]:
            temp_cart_options[user_id][prod_id] = {'qty': 1, 'unit': 'kg'}
            
        current_qty = temp_cart_options[user_id][prod_id]['qty']
        new_qty = current_qty + change
        if new_qty < 1:
            new_qty = 1
            
        temp_cart_options[user_id][prod_id]['qty'] = new_qty
        unit = temp_cart_options[user_id][prod_id]['unit']
        
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=make_purchase_keyboard(prod_id, new_qty, unit))
        bot.answer_callback_query(call.id)

    # 3. Savatga qo'shish ijrosi
    elif data.startswith("add_to_cart_"):
        prod_id = int(data.split("_")[3])
        
        if user_id not in temp_cart_options or prod_id not in temp_cart_options[user_id]:
            qty = 1
            unit = 'kg'
        else:
            qty = temp_cart_options[user_id][prod_id]['qty']
            unit = temp_cart_options[user_id][prod_id]['unit']
            
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO cart (user_id, product_id, quantity, unit) VALUES (?, ?, ?, ?)", (user_id, prod_id, qty, unit))
        conn.commit()
        conn.close()
        
        bot.send_message(call.message.chat.id, f"✅ Tovar savatga muvaffaqiyatli tushdi!\nMiqdori: {qty} {unit}")
        bot.answer_callback_query(call.id)

    # 4. Admin: Tovar qo'shish tugmasi
    elif data == "admin_add_product":
        if user_id != ADMIN_ID: return
        msg = bot.send_message(call.message.chat.id, "Yangi tovar nomini kiriting:")
        bot.register_next_step_handler(msg, process_product_name)
        bot.answer_callback_query(call.id)

    # 5. Admin: Tovar Ayirish (O'chirish) tugmasi
    elif data == "admin_delete_product":
        if user_id != ADMIN_ID: return
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM products")
        products = cursor.fetchall()
        conn.close()
        
        if not products:
            bot.send_message(call.message.chat.id, "Xozirda bazada o'chirish uchun hech qanday tovar yo'q.")
            bot.answer_callback_query(call.id)
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for prod in products:
            markup.add(types.InlineKeyboardButton(f"❌ {prod[1]}", callback_data=f"del_{prod[0]}"))
        bot.send_message(call.message.chat.id, "O'chirmoqchi bo'lgan tovaringiz ustiga bosing:", reply_markup=markup)
        bot.answer_callback_query(call.id)

    # 6. Admin: Tovarni bazadan o'chirish ijrosi
    elif data.startswith("del_"):
        if user_id != ADMIN_ID: return
        prod_id = int(data.split("_")[1])
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (prod_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Tovar muvaffaqiyatli ayirildi (o'chirildi)!")
        bot.edit_message_text("Tovar o'chirildi. Admin panel orqali ishlashda davom etishingiz mumkin.", call.message.chat.id, call.message.message_id)

    # 7. Admin: Promokod yaratish tugmasi
    elif data == "admin_add_promo":
        if user_id != ADMIN_ID: return
        msg = bot.send_message(call.message.chat.id, "Yangi promokod kalit so'zini kiriting (Masalan: 12881):")
        bot.register_next_step_handler(msg, process_promo_code)
        bot.answer_callback_query(call.id)

    # 8. Savatni tozalash ijrosi
    elif data == "clear_cart":
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Savat tozalandi!")
        bot.edit_message_text("Savatchangiz hozircha bo'sh.", call.message.chat.id, call.message.message_id)

    # 9. Buyurtma berish (Adminga yuborish)
    elif data == "checkout_cart":
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.name, c.quantity, c.unit, p.price 
            FROM cart c JOIN products p ON c.product_id = p.id 
            WHERE c.user_id = ?
        """, (user_id,))
        items = cursor.fetchall()
        conn.close()
        
        if not items:
            bot.answer_callback_query(call.id, "Savat bo'sh!")
            return
            
        order_text = f"🔔 **Yangi Buyurtma Keldi!**\n\n👤 Xaridor: {call.from_user.first_name}\n"
        if call.from_user.username:
            order_text += f"🌐 Username: @{call.from_user.username}\n"
        order_text += f"🆔 ID: `{user_id}`\n\n📦 **Mahsulotlar:**\n"
        
        total = 0
        for name, qty, unit, price in items:
            cost = qty * price
            total += cost
            order_text += f"🔹 {name} - {qty} {unit} x {price} = {cost} so'm\n"
        order_text += f"\n💰 **Jami summa:** {total} so'm"
        
        bot.send_message(ADMIN_ID, order_text, parse_mode="Markdown")
        
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        bot.send_message(call.message.chat.id, "✅ Buyurtmangiz adminga muvaffaqiyatli yuborildi! Tez orada aloqaga chiqamiz.")
        bot.answer_callback_query(call.id)

# =========================================================
# NEXT STEP HANDLERS (ADMIN TOVAR VA PROMOKOD QO'SHISH)
# =========================================================
def process_product_name(message):
    name = message.text
    msg = bot.send_message(message.chat.id, f"'{name}' mahsuloti uchun narx kiriting (Faqat raqam yozing):")
    bot.register_next_step_handler(msg, process_product_price, name)

def process_product_price(message, name):
    try:
        price = float(message.text)
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (name, price) VALUES (?, ?)", (name, price))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ Tovar bazaga muvaffaqiyatli qo'shildi!\n🐎 Nomi: {name}\n💰 Narxi: {price} so'm")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Narx noto'g'ri kiritildi. Faqat raqam yozing. Amaliyot bekor bo'ldi.")

def process_promo_code(message):
    code = message.text.strip()
    admin_states[message.chat.id] = {"promo_code": code}
    msg = bot.send_message(message.chat.id, f"'{code}' promokodi kiritilganda foydalanuvchiga chiqadigan matnni o'zingiz yozing:")
    bot.register_next_step_handler(msg, process_promo_text)

def process_promo_text(message):
    admin_data = admin_states.get(message.chat.id)
    if not admin_data:
        bot.send_message(message.chat.id, "❌ Xatolik. Jarayon boshqatdan boshlang.")
        return
        
    code = admin_data["promo_code"]
    reward_text = message.text
    
    conn = sqlite3.connect("tulpor_savdo.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO promocodes (code, reward_text) VALUES (?, ?)", (code, reward_text))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Yangi Promokod Tayyor!\n🔑 Kod: {code}\n📝 Siz yozgan matn: {reward_text}")
    if message.chat.id in admin_states:
        del admin_states[message.chat.id]

# Foydalanuvchi promokod kiritish jarayoni
def user_check_promo(message):
    user_code = message.text.strip()
    
    conn = sqlite3.connect("tulpor_savdo.db")
    cursor = conn.cursor()
    cursor.execute("SELECT reward_text FROM promocodes WHERE code = ?", (user_code,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        reward_text = result[0]
        # 1. Foydalanuvchining o'ziga admin yaratgan matn boradi
        bot.send_message(message.chat.id, reward_text)
        
        # 2. Adminga foydalanuvchining barcha ma'lumotlari va kliklanadigan lichka havolasi boradi
        user_username = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
        user_link = f"tg://user?id={message.from_user.id}"
        
        admin_alert = (
            f"🔔 **Vip Promokod Ishlatildi!**\n\n"
            f"🔑 **Ishlatilgan Kod:** `{user_code}`\n"
            f"👤 **Ismi:** {message.from_user.first_name}\n"
            f"🌐 **Username:** {user_username}\n"
            f"🆔 **ID:** `{message.from_user.id}`\n\n"
            f"📥 **Lichka havolasi:** [Foydalanuvchiga yozish]({user_link})"
        )
        bot.send_message(ADMIN_ID, admin_alert, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Noto'g'ri promokod kiritdingiz yoki bu kod muddati tugagan.")

# =========================================================
# ASOSIY MATNLI KLAVIATURA KODLARI
# =========================================================
@bot.message_handler(func=lambda msg: True)
def echo_all(message):
    # TOVARLAR MENU BOSILGANDA (Interaktiv xarid paneli bilan birga chiqarish)
    if message.text == "TOVARLAR 🌐":
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price FROM products")
        products = cursor.fetchall()
        conn.close()
        
        if not products:
            bot.send_message(message.chat.id, "Hozircha sotuvda hech qanday mahsulot yo'q.")
            return
            
        bot.send_message(message.chat.id, "📦 Mavjud mahsulotlar va buyurtma paneli:")
        for prod_id, name, price in products:
            text = f"🐎 **Mahsulot nomi:** {name}\n💰 **Narxi:** {price} so'm"
            
            # Har bir mahsulot uchun foydalanuvchining boshlang'ich tanlovini o'rnatish
            if message.from_user.id not in temp_cart_options:
                temp_cart_options[message.from_user.id] = {}
            temp_cart_options[message.from_user.id][prod_id] = {'qty': 1, 'unit': 'kg'}
            
            bot.send_message(
                message.chat.id, 
                text, 
                reply_markup=make_purchase_keyboard(prod_id, 1, 'kg'),
                parse_mode="Markdown"
            )
        
    elif message.text == "🛒 Savat":
        conn = sqlite3.connect("tulpor_savdo.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.name, c.quantity, c.unit, p.price 
            FROM cart c JOIN products p ON c.product_id = p.id 
            WHERE c.user_id = ?
        """, (message.from_user.id,))
        items = cursor.fetchall()
        conn.close()
        
        if not items:
            bot.send_message(message.chat.id, "Savatchangiz hozircha bo'sh.")
            return
            
        text = "🛒 **Sizning savatchangiz:**\n\n"
        total = 0
        for name, qty, unit, price in items:
            cost = qty * price
            total += cost
            text += f"🔹 {name} - {qty} {unit} x {price} = {cost} so'm\n"
        text += f"\n💰 **Jami summa:** {total} so'm"
        
        markup = types.InlineKeyboardMarkup()
        btn_clear = types.InlineKeyboardButton("🗑 Savatni tozalash", callback_data="clear_cart")
        btn_order = types.InlineKeyboardButton("🚖 Buyurtma berish", callback_data="checkout_cart")
        markup.add(btn_order, btn_clear)
        
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
        
    elif message.text == "🔑 Promokod kiritish":
        msg = bot.send_message(message.chat.id, "Sizda mavjud bo'lgan promokodni yozing:")
        bot.register_next_step_handler(msg, user_check_promo)
        
    elif message.text == "🚚 Yetkazib berish":
        bot.send_message(message.chat.id, "🚚 Yetkazib berish shartlari:\nNamangan viloyati va Chortoq tumani bo'ylab tezkor yetkazib berish xizmati mavjud.")
        
    elif message.text == "ℹ️ Biz haqimizda":
        bot.send_message(message.chat.id, "🐎 Tulpor savdo markazi botiga xush kelibsiz!\nBiz sizga eng sifatli mahsulotlarni eng hamyonbop narxlarda taqdim etamiz.")

# Botni cheksiz va uzluksiz ishga tushirish
bot.infinity_polling()
        
