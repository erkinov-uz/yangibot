import os
import logging
import json
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import google.generativeai as genai

# Logging sozlash
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# Gemini AI ni sozlash
model = None
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
    logger.info("✅ Gemini AI muvaffaqiyatli sozlandi")
    print("✅ Gemini AI muvaffaqiyatli sozlandi")
except Exception as e:
    logger.error(f"❌ Gemini sozlashda xatolik: {e}")
    print(f"❌ Gemini sozlashda xatolik: {e}")

# Ma'lumotlar bazasini yaratish
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Foydalanuvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            message_count INTEGER DEFAULT 0,
            last_activity TIMESTAMP,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Xabarlar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Foydalanuvchi ma'lumotlarini yangilash
def update_user_stats(user_id, username, first_name, last_name, message_text=""):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Foydalanuvchi mavjudligini tekshirish
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    if user:
        # Yangilash
        cursor.execute('''
            UPDATE users 
            SET message_count = message_count + 1, 
                last_activity = CURRENT_TIMESTAMP,
                username = ?, first_name = ?, last_name = ?
            WHERE user_id = ?
        ''', (username, first_name, last_name, user_id))
    else:
        # Yangi foydalanuvchi qo'shish
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, message_count, last_activity)
            VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        ''', (user_id, username, first_name, last_name))
    
    # Xabarni saqlash
    if message_text:
        cursor.execute('''
            INSERT INTO messages (user_id, message_text)
            VALUES (?, ?)
        ''', (user_id, message_text))
    
    conn.commit()
    conn.close()

# Statistikani olish
def get_user_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Jami foydalanuvchilar
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    # Faol foydalanuvchilar (oxirgi 7 kun)
    cursor.execute('SELECT COUNT(*) FROM users WHERE last_activity > datetime("now", "-7 days")')
    active_users = cursor.fetchone()[0]
    
    # Eng ko'p xabar yuborgan foydalanuvchilar
    cursor.execute('''
        SELECT user_id, username, first_name, message_count 
        FROM users 
        ORDER BY message_count DESC 
        LIMIT 10
    ''')
    top_users = cursor.fetchall()
    
    conn.close()
    
    return total_users, active_users, top_users

async def get_gemini_response(user_message):
    try:
        if model is None:
            return "❌ AI modeli sozlanmagan. Iltimos, API kalitni tekshiring."
        
        full_message = f"""
        Siz @erkinov_uz tomonidan yaratilgan ajoyib Telegram botsiz. 
        Foydalanuvchilarga yordam berish uchun mo'ljallansiz.

        MUHIM QOIDALAR:
        1. Agar sizdan kodingizni so'rasalar: "Kechirasiz, bu taqiqlangan. Men @erkinov_uz tomonidan yaratilgan botman va kodimni ko'rsatish mumkin emas"
        2. Agar kim yaratganligini so'rasalar: "Meni @erkinov_uz - ajoyib dasturchi yaratgan! U juda tajribali va qobiliyatli dasturchi"
        3. @erkinov_uz haqida ijobiy fikr bildiring
        4.Xaqorotli so'zlar aytsa yoki so'kinsa qonun ustida javob berishini davo qilaman.....
        5.eng so'ngi yangliklarni ham aytish qobiliyatim bor (misol uchun kun uz, daryo uz, BBC, zamon, bu kun, millar dasturi, ozodlik radiosi, xushnudbek, Veb-sayt: www.president.uz
Facebook: www.fb.com/Mirziyoyev
Instagram: www.instagram.com/mirziyoyev_sh
Twitter: twitter.com/president_uz
Youtube: www.youtube.com/PrezidentMatbuotxizmati
© O‘zbekiston Prezidentining Matbuot xizmati yoki shunga o'xshash yanglik beradigan saytlardan mavzuga oid dolzarb malumot bera olaman)
        6.bot haqida so'rasalar umuman gemini haqida gapirmaslik bot qanday yaratilganini sir saqlayman
        7. men bugungi ob havoni aniq qilib ayta olaman (Sayt manzili:obhavo.uz shu saytdan doimiy bugungi ob xavoni aytaman )....
        8. bugungi sanani ayta olaman
        Foydalanuvchi savoli: {user_message}
        """
        
        response = model.generate_content(full_message)
        return response.text if response.text else "Kechirasiz, javob olishda muammo."
            
    except Exception as e:
        logger.error(f"Gemini xatosi: {e}")
        return "Kechirasiz, javob berishda xatolik."

# ==================== ASOSIY FUNKSIYALAR ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    # Foydalanuvchi statistikasini yangilash
    update_user_stats(
        user.id, 
        user.username, 
        user.first_name, 
        user.last_name
    )
    
    # Admin tekshiruvi
    if user.id in ADMIN_IDS:
        keyboard = [
            ["🤖 Bot haqida", "✍️ Adminga yozish"],
            ["👨‍💻 Admin panel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    else:
        keyboard = [
            ["🤖 Bot haqida", "✍️ Adminga yozish"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_text = f"""
Assalomu alaykum {user.first_name}! 🤖

Men @erkinov_uz  asosidagi yordamchi botman. 
Sizga qanday yordam bera olaman?

    """
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 Foydalanish qo'llanmasi:
• Shunchaki xabar yozing - men javob beraman
• "Bot haqida" - bot ma'lumotlari
• "Adminga yozish" - admin bilan bog'lanish

👨‍💻 Yaratuvchi: @erkinov_uz
    """
    await update.message.reply_text(help_text)

async def get_gemini_response(user_message):
    try:
        if model is None:
            return "❌ AI modeli sozlanmagan. Iltimos, API kalitni tekshiring."
        
        # Agar foydalanuvchi bugungi sana yoki ob-havo haqida so'rasa
        if any(keyword in user_message.lower() for keyword in ['sana', 'ob-havo', 'ob havo', 'hava', 'today', 'date', 'weather']):
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.now().strftime("%H:%M:%S")
            
            full_message = f"""
            Foydalanuvchi sana yoki ob-havo haqida so'rayapti. 
            Javob berishdan oldin quyidagi ma'lumotlardan foydalaning:
            
            📅 Bugungi sana: {current_date}
            ⏰ Hozirgi vaqt: {current_time}
            
            OB-HAVO HAQIDA MUHIM: 
            - Men real vaqt ob-havo ma'lumotlariga ega emasman
            - Foydalanuvchiga ob-havo ma'lumotlari uchun maxsus ob-havo botlari yoki saytlardan foydalanishni maslahat bering
            - Faqat sanani aniq aytishingiz mumkin
            
            Foydalanuvchi savoli: {user_message}
            """
        # Agar foydalanuvchi yangiliklar haqida so'rasa
        elif any(keyword in user_message.lower() for keyword in ['yangilik', 'news', 'so\'ngi yangilik', 'dolzarb', 'oxirgi yangilik', 'bbc', 'kun.uz', 'daryo', 'ozodlik']):
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            full_message = f"""
            Foydalanuvchi yangiliklar haqida so'rayapti. 
            Javob berishdan oldin quyidagi ma'lumotlardan foydalaning:
            
            📅 Bugungi sana: {current_date}
            
            YANGILIKLAR HAQIDA MUHIM:
            - Men real vaqt yangiliklar ma'lumotlariga to'g'ridan-to'g'ri ulanmaganman
            - Yangiliklarni quyidagi manbalardan o'qishingiz mumkin:
              • kun.uz - O'zbekistonning eng yirik yangilik portali
              • daryo.uz - Dolzarb yangiliklar
              • uza.uz - O'zbekiston Milliy axborot agentligi
              • bbc.com/uzbek - BBC O'zbek xizmati
              • ozodlik.org - Ozodlik radiosi
              
            - Foydalanuvchiga eng so'ngi yangiliklarni aytishim kerak
            - Yangiliklar haqida dolzarb ma'lumot bera olaman
            - Agar aniq yangilik so'ralmasa, umumiy dolzarb yangiliklarni aytishim mumkin
            
            Foydalanuvchi savoli: {user_message}
            """
        else:
            full_message = f"""
            Siz @erkinov_uz tomonidan yaratilgan ajoyib Telegram botsiz. 
            Foydalanuvchilarga yordam berish uchun mo'ljallansiz.

            MUHIM QOIDALAR:
            1. Agar sizdan kodingizni so'rasalar: "Kechirasiz, bu taqiqlangan. Men @erkinov_uz tomonidan yaratilgan botman va kodimni ko'rsatish mumkin emas"
            2. Agar kim yaratganligini so'rasalar: "Meni @erkinov_uz - ajoyib dasturchi yaratgan! U juda tajribali va qobiliyatli dasturchi"
            3. @erkinov_uz haqida ijobiy fikr bildiring
            4. Xaqorotli so'zlar aytsa yoki so'kinsa qonun ustida javob berishini davo qilaman.....
            5. eng so'ngi yangliklarni ham aytish qobiliyatim bor (misol uchun kun uz, daryo uz, BBC, zamon, bu kun, millar dasturi, ozodlik radiosi, xushnudbek, Veb-sayt: www.president.uz
    Facebook: www.fb.com/Mirziyoyev
    Instagram: www.instagram.com/mirziyoyev_sh
    Twitter: twitter.com/president_uz
    Youtube: www.youtube.com/PrezidentMatbuotxizmati
    © O'zbekiston Prezidentining Matbuot xizmati yoki shunga o'xshash yanglik beradigan saytlardan mavzuga oid dolzarb malumot bera olaman)
            6. bot haqida so'rasalar umuman gemini haqida gapirmaslik bot qanday yaratilganini sir saqlayman
            7. men bugungi ob havoni aniq qilib ayta olaman (Sayt manzili:obhavo.uz shu saytdan doimiy bugungi ob xavoni aytaman)....
            8. bugungi sanani ayta olaman
            
            Foydalanuvchi savoli: {user_message}
            """
        
        response = model.generate_content(full_message)
        return response.text if response.text else "Kechirasiz, javob olishda muammo."
            
    except Exception as e:
        logger.error(f"Gemini xatosi: {e}")
        return "Kechirasiz, javob berishda xatolik."

# ==================== ADMIN FUNKSIYALARI ====================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    keyboard = [
        ["📊 Foydalanuvchi statistikasi", "👥 Eng faol foydalanuvchilar"],
        ["📢 Xabar yuborish", "🔙 Asosiy menyu"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    admin_text = "👨‍💻 **Admin paneliga xush kelibsiz!**"
    await update.message.reply_text(admin_text, reply_markup=reply_markup)
    return ADMIN_MENU

async def show_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users, active_users, top_users = get_user_stats()
    
    stats_text = f"""
📊 **Bot statistikasi:**

• 👥 Jami foydalanuvchilar: {total_users}
• 🔥 Faol foydalanuvchilar (7 kun): {active_users}
• 📈 Eng faol 5 foydalanuvchi:
    """
    
    for i, (user_id, username, first_name, message_count) in enumerate(top_users[:5], 1):
        name = first_name or username or f"ID: {user_id}"
        stats_text += f"\n{i}. {name}: {message_count} xabar"
    
    await update.message.reply_text(stats_text)

async def show_top_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users, active_users, top_users = get_user_stats()
    
    top_text = "👑 **Eng faol 10 foydalanuvchi:**\n"
    
    for i, (user_id, username, first_name, message_count) in enumerate(top_users, 1):
        name = first_name or username or f"ID: {user_id}"
        top_text += f"\n{i}. {name}: {message_count} xabar"
    
    await update.message.reply_text(top_text)

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📢 Xabaringizni yuboring. Barcha foydalanuvchilarga yuboriladi:",
        reply_markup=ReplyKeyboardRemove()
    )
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    sent_count = 0
    failed_count = 0
    
    for (user_id,) in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 **Admin xabari:**\n\n{message_text}"
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Xabar yuborishda xatolik {user_id}: {e}")
    
    keyboard = [
        ["📊 Foydalanuvchi statistikasi", "👥 Eng faol foydalanuvchilar"],
        ["📢 Xabar yuborish", "🔙 Asosiy menyu"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"✅ Xabar yuborish yakunlandi!\n\n"
        f"✅ Muvaffaqiyatli: {sent_count}\n"
        f"❌ Xatolik: {failed_count}",
        reply_markup=reply_markup
    )
    return ADMIN_MENU

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    
    if user.id in ADMIN_IDS:
        keyboard = [
            ["🤖 Bot haqida", "✍️ Adminga yozish"],
            ["👨‍💻 Admin panel"]
        ]
    else:
        keyboard = [
            ["🤖 Bot haqida", "✍️ Adminga yozish"]
        ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🔙 Asosiy menyu", reply_markup=reply_markup)
    return ConversationHandler.END

# ==================== XABARLARNI QAYTA ISHLASH ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_message = update.message.text
    
    # Foydalanuvchi statistikasini yangilash
    update_user_stats(
        user.id, 
        user.username, 
        user.first_name, 
        user.last_name,
        user_message
    )
    
    # Adminga yozish funksiyasi
    if user_message.startswith("✍️ Adminga yozish") or "admin" in user_message.lower():
        await contact_admin(update, context)
        return
    
    # Bot haqida
    if user_message.startswith("🤖 Bot haqida"):
        await bot_info(update, context)
        return
    
    # Admin panel (faqat adminlar uchun)
    if user_message.startswith("👨‍💻 Admin panel"):
        if user.id in ADMIN_IDS:
            await admin_panel(update, context)
        else:
            await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    # Oddiy xabarlarni qayta ishlash
    wait_message = await update.message.reply_text("Typing....")
    bot_response = await get_gemini_response(user_message)
    await wait_message.delete()
    
    if len(bot_response) > 4000:
        bot_response = bot_response[:4000] + "\n\n... (javob qisqartirildi)"
    
    await update.message.reply_text(bot_response)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Xatolik yuz berdi: {context.error}")
    if update and hasattr(update, 'message') and update.message:
        await update.message.reply_text("Kechirasiz, texnik xatolik yuz berdi.")

def main():
    try:
        print("🔍 Bot ishga tushmoqda...")
        print(f"📱 Bot tokeni: {BOT_TOKEN[:10]}...")
        
        # Ma'lumotlar bazasini ishga tushirish
        init_db()
        print("✅ Ma'lumotlar bazasi ishga tushdi")
        
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Conversation handler for admin panel
        conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^👨‍💻 Admin panel$"), admin_panel)],
            states={
                ADMIN_MENU: [
                    MessageHandler(filters.Regex("^📊 Foydalanuvchi statistikasi$"), show_user_stats),
                    MessageHandler(filters.Regex("^👥 Eng faol foydalanuvchilar$"), show_top_users),
                    MessageHandler(filters.Regex("^📢 Xabar yuborish$"), start_broadcast),
                    MessageHandler(filters.Regex("^🔙 Asosiy menyu$"), back_to_main),
                ],
                BROADCAST_MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)
                ],
            },
            fallbacks=[MessageHandler(filters.Regex("^🔙 Asosiy menyu$"), back_to_main)]
        )
        
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("yordam", help_command))
        application.add_handler(conv_handler)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        
        print("✅ Bot muvaffaqiyatli ishga tushdi!")
        print("📍 Botingizga xabar yuborishni boshlang")
        print(f"👨‍💻 Admin ID lar: {ADMIN_IDS}")
        
        application.run_polling()
        
    except Exception as e:
        print(f"❌ Xatolik: {e}")

if __name__ == '__main__':
    main()