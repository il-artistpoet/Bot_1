# Пленэрный Клуб Бот - ФИНАЛЬНАЯ ВЕРСИЯ с PostgreSQL
# Работает на Render и Pydroid 3

import os
import telebot
import logging
from datetime import datetime
from flask import Flask, request
import time
import sys
import asyncpg
import asyncio

# ========== РЕЖИМ ТЕСТИРОВАНИЯ ==========
# На телефоне: TEST_MODE = True
# На Render: TEST_MODE = False
TEST_MODE = False

if TEST_MODE:
    print("📱 РЕЖИМ ТЕСТИРОВАНИЯ: Используем временную базу данных")
    # Создаем временную базу в памяти
    import sqlite3
    from sqlite3 import Row
    
    # Заглушка для подключения к БД
    def get_db_connection():
        conn = sqlite3.connect(':memory:', check_same_thread=False)
        conn.row_factory = Row
        
        # Создаем таблицу если её нет
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                tariff TEXT,
                amount INTEGER DEFAULT 0,
                paid INTEGER DEFAULT 0,
                screenshot_date TEXT,
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        return conn
    
    # Переопределяем асинхронные функции на синхронные
    def run_async(func):
        return func
    
    def get_user_sync(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    def save_user_sync(user_id, username=None, first_name=None, last_name=None, 
                      tariff=None, amount=0, paid=0):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, tariff, amount, paid, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (user_id, username, first_name, last_name, tariff, amount, paid))
        
        conn.commit()
        conn.close()
        return True
    
    def update_payment_status_sync(user_id, paid=1):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users 
            SET paid = ?, screenshot_date = datetime('now'), updated_at = datetime('now')
            WHERE user_id = ?
        """, (paid, user_id))
        
        conn.commit()
        conn.close()
        return True
    
    # Функции статистики для тестирования
    def get_user_count_sync():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        result = cursor.fetchone()[0]
        conn.close()
        return result or 0
    
    def get_paid_users_count_sync():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE paid = 1")
        result = cursor.fetchone()[0]
        conn.close()
        return result or 0
    
    def get_total_income_sync():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(amount) FROM users WHERE paid = 1")
        result = cursor.fetchone()[0]
        conn.close()
        return result or 0
    
    def get_tariff_stats_sync():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT tariff, COUNT(*) as count FROM users WHERE paid = 1 GROUP BY tariff")
        rows = cursor.fetchall()
        
        stats = {"читатель": 0, "участник": 0}
        for row in rows:
            if row[0] in stats:
                stats[row[0]] = row[1]
        
        conn.close()
        return stats
    
    # Инициализация БД для тестирования
    def init_db():
        # Уже создали таблицу в get_db_connection()
        print("✅ База данных SQLite инициализирована")
    
else:
    # Реальный код для Render с PostgreSQL
    import asyncpg
    import asyncio
    
    # ... ваш существующий код с asyncpg ...
    
# Фикс для Render PostgreSQL URL
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    os.environ['DATABASE_URL'] = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN', '8432420548:AAGX_EqsarA7q_Jx4iNL2zV8j3c_JWd_POU')
CHANNEL_ID = "-1003227241488"
ADMIN_ID = 644037215
TILDA_LINK = "https://pleinairclub.tilda.ws/"

# Реквизиты
SBER_PHONE = "+79043323607"
SBER_CARD = "2202208262152375"

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ PostgreSQL с asyncpg ==========
import asyncpg
import asyncio

async def get_db_connection():
    """Подключение к PostgreSQL через asyncpg"""
    try:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.warning("⚠️ DATABASE_URL не найден")
            return None
            
        # Исправляем URL для asyncpg
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
            
        conn = await asyncpg.connect(database_url)
        logger.info("✅ Подключение к PostgreSQL установлено")
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
        return None

async def init_db():
    """Создание таблиц при старте"""
    conn = await get_db_connection()
    if not conn:
        logger.error("❌ Не удалось подключиться к БД для инициализации")
        return
    
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(100),
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                tariff VARCHAR(50),
                amount INTEGER DEFAULT 0,
                paid INTEGER DEFAULT 0,
                screenshot_date TIMESTAMP,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создаем индексы если их нет
        try:
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_paid ON users(paid)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_tariff ON users(tariff)")
        except:
            pass  # Индексы уже существуют
        
        logger.info("✅ Таблицы PostgreSQL успешно созданы/проверены")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
    finally:
        await conn.close()

async def get_user(user_id):
    """Получить пользователя по ID"""
    conn = await get_db_connection()
    if not conn:
        logger.warning(f"⚠️ Нет подключения к БД при запросе пользователя {user_id}")
        return None
    
    try:
        row = await conn.fetchrow("""
            SELECT user_id, username, first_name, last_name, 
                   tariff, amount, paid, screenshot_date, 
                   registered_at, updated_at 
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        if row:
            # Преобразуем Record в словарь
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка получения пользователя {user_id}: {e}")
        return None
    finally:
        await conn.close()

async def save_user(user_id, username=None, first_name=None, last_name=None, 
                   tariff=None, amount=0, paid=0):
    """Сохранить или обновить пользователя"""
    conn = await get_db_connection()
    if not conn:
        logger.warning(f"⚠️ Нет подключения к БД при сохранении пользователя {user_id}")
        return False
    
    try:
        await conn.execute("""
            INSERT INTO users 
            (user_id, username, first_name, last_name, tariff, amount, paid, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                tariff = EXCLUDED.tariff,
                amount = EXCLUDED.amount,
                paid = EXCLUDED.paid,
                updated_at = CURRENT_TIMESTAMP
        """, user_id, username, first_name, last_name, tariff, amount, paid)
        
        logger.info(f"✅ Пользователь {user_id} сохранен/обновлен в PostgreSQL")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения пользователя {user_id}: {e}")
        return False
    finally:
        await conn.close()

async def update_payment_status(user_id, paid=1):
    """Обновить статус оплаты"""
    conn = await get_db_connection()
    if not conn:
        logger.warning(f"⚠️ Нет подключения к БД при обновлении оплаты {user_id}")
        return False
    
    try:
        await conn.execute("""
            UPDATE users 
            SET paid = $1, 
                screenshot_date = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $2
        """, paid, user_id)
        
        logger.info(f"✅ Статус оплаты обновлен для {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления оплаты {user_id}: {e}")
        return False
    finally:
        await conn.close()

async def get_user_count():
    """Получить общее количество пользователей"""
    conn = await get_db_connection()
    if not conn:
        return 0
    
    try:
        result = await conn.fetchval("SELECT COUNT(*) FROM users")
        return result or 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества пользователей: {e}")
        return 0
    finally:
        await conn.close()

async def get_paid_users_count():
    """Получить количество оплативших пользователей"""
    conn = await get_db_connection()
    if not conn:
        return 0
    
    try:
        result = await conn.fetchval("SELECT COUNT(*) FROM users WHERE paid = 1")
        return result or 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества оплативших: {e}")
        return 0
    finally:
        await conn.close()

async def get_total_income():
    """Получить общий доход"""
    conn = await get_db_connection()
    if not conn:
        return 0
    
    try:
        result = await conn.fetchval("SELECT SUM(amount) FROM users WHERE paid = 1")
        return result or 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения общего дохода: {e}")
        return 0
    finally:
        await conn.close()

async def get_tariff_stats():
    """Получить статистику по тарифам"""
    conn = await get_db_connection()
    if not conn:
        return {"читатель": 0, "участник": 0}
    
    try:
        rows = await conn.fetch("""
            SELECT tariff, COUNT(*) as count 
            FROM users 
            WHERE paid = 1 AND tariff IS NOT NULL
            GROUP BY tariff
        """)
        
        stats = {"читатель": 0, "участник": 0}
        for row in rows:
            tariff = row['tariff']
            count = row['count']
            if tariff in stats:
                stats[tariff] = count
        
        return stats
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики по тарифам: {e}")
        return {"читатель": 0, "участник": 0}
    finally:
        await conn.close()

# ========== СИНХРОННЫЕ ОБЕРТКИ ДЛЯ TELEGRAM БОТА ==========
def run_async(coro):
    """Запуск асинхронной функции в синхронном контексте"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def get_user_sync(user_id):
    return run_async(get_user(user_id))

def save_user_sync(user_id, **kwargs):
    return run_async(save_user(user_id, **kwargs))

def update_payment_status_sync(user_id, paid=1):
    return run_async(update_payment_status(user_id, paid))

def get_user_count_sync():
    return run_async(get_user_count())

def get_paid_users_count_sync():
    return run_async(get_paid_users_count())

def get_total_income_sync():
    return run_async(get_total_income())

def get_tariff_stats_sync():
    return run_async(get_tariff_stats())

# ========== ВЕБХУК ДЛЯ RENDER ==========
@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>🎨 Пленэрный Клуб Бот</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 50px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .container {
                    background: rgba(255, 255, 255, 0.1);
                    padding: 30px;
                    border-radius: 15px;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                }
                h1 {
                    font-size: 2.5em;
                    margin-bottom: 20px;
                }
                .status {
                    font-size: 1.2em;
                    margin: 20px 0;
                    padding: 10px;
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 10px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎨 Пленэрный Клуб Бот</h1>
                <div class="status">✅ Бот работает!</div>
                <p>Telegram бот для управления подписками на закрытый канал</p>
                <p><a href="/health" style="color: #fff; text-decoration: underline;">Проверить статус</a></p>
            </div>
        </body>
    </html>
    """

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    try:
        # Просто проверяем подключение
        conn = run_async(get_db_connection())
        if conn:
            # Не закрываем соединение здесь
            return {
                "status": "healthy",
                "database": "connected",
                "timestamp": datetime.now().isoformat()
            }, 200
        else:
            return {
                "status": "degraded",
                "database": "disconnected",
                "timestamp": datetime.now().isoformat()
            }, 200
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, 500

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка вебхуков от Telegram"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Bad Request', 400

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    logger.info(f"🚀 /start от {user_id} (@{username})")
    
    # Сохраняем пользователя в БД
    save_user_sync(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name
    )
    
    # 1. Сначала отправляем фото (если есть)
    try:
        with open('photo.png', 'rb') as photo:
            bot.send_photo(user_id, photo)
            logger.info(f"📸 Фото отправлено пользователю {user_id}")
    except FileNotFoundError:
        logger.warning(f"⚠️ Файл photo.png не найден!")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке фото: {e}")
    
    # 2. Отправляем сообщение с текстом и кнопками
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    btn_more = telebot.types.InlineKeyboardButton(
        text="Узнать больше",
        url=TILDA_LINK
    )
    
    btn_club = telebot.types.InlineKeyboardButton(
        text="Хочу в клуб!",
        callback_data="join_club"
    )
    
    markup.add(btn_more, btn_club)
    
    welcome_text = (
        "🎨Приветствую Вас! Оставайтесь на волне созерцания и пленэра.\n\n"
        "Здесь можно купить подписку и получить доступ в \"Пленэрный Клуб\"!\n\n"
        "Это закрытый телеграм-канал, где все участники могут делиться своим творчеством "
        "и получать от меня обратную связь."
    )
    
    bot.send_message(
        user_id,
        welcome_text,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "join_club")
def show_tariffs(call):
    """Показ тарифов"""
    user_id = call.from_user.id
    logger.info(f"📋 Показ тарифов для {user_id}")
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn_reader = telebot.types.InlineKeyboardButton(
        "🔥 ЧИТАТЕЛЬ — 100₽/месяц", 
        callback_data="tariff_reader"
    )
    btn_member = telebot.types.InlineKeyboardButton(
        "💎 УЧАСТНИК — 500₽/месяц", 
        callback_data="tariff_member"
    )
    markup.add(btn_reader, btn_member)
    
    bot.send_message(
        user_id,
        "🎯 ВЫБЕРИТЕ ТАРИФ ДОСТУПА К ПЛЕНЭРНОМУ КЛУБУ:\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 ЧИТАТЕЛЬ — 100₽\n"
        "• Просмотр всех материалов канала\n"
        "• Доступ к архиву постов\n"
        "• Без обратной связи\n\n"
        "💎 УЧАСТНИК — 500₽\n"  
        "• Всё из тарифа Читатель\n"
        "• Разбор Ваших работ\n"
        "• Помощь по всем творческим вопросам\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 ВЫБЕРИТЕ ТАРИФ И НАЖМИТЕ КНОПКУ",
        reply_markup=markup,
        parse_mode=None
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data in ["tariff_reader", "tariff_member"])
def handle_tariff(call):
    """Обработка выбора тарифа с возможностью апгрейда"""
    user_id = call.from_user.id
    
    if call.data == "tariff_reader":
        selected_tariff, selected_amount = "читатель", 100
    else:
        selected_tariff, selected_amount = "участник", 500
    
    logger.info(f"🎯 Выбор тарифа: {selected_tariff} ({selected_amount}₽) для {user_id}")
    
    # Получаем текущие данные пользователя
    user = get_user_sync(user_id)
    
    if user:
        current_tariff = user['tariff']
        current_amount = user['amount']
        paid = user['paid']
        
        # Если уже оплатил
        if paid == 1:
            # Пользователь уже в клубе - проверяем апгрейд
            if current_tariff == "читатель" and selected_tariff == "участник":
                # ПРЕДЛАГАЕМ АПГРЕЙД
                to_pay = selected_amount - current_amount  # 400₽
                
                markup = telebot.types.InlineKeyboardMarkup()
                btn_upgrade = telebot.types.InlineKeyboardButton(
                    f"💎 ПЕРЕЙТИ (+{to_pay}₽)",
                    callback_data="upgrade_member"
                )
                markup.add(btn_upgrade)
                
                bot.send_message(
                    user_id,
                    f"✅ Вы уже оплатили тариф '{current_tariff.upper()}'!\n\n"
                    f"Хотите перейти на тариф 'УЧАСТНИК'?\n"
                    f"• Ваш тариф: {current_tariff} ({current_amount}₽)\n"
                    f"• Новый тариф: участник ({selected_amount}₽)\n"
                    f"• К доплате: {to_pay}₽\n\n"
                    f"Вы получите:\n"
                    f"• Обратную связь по работам\n"
                    f"• Ответы на вопросы\n"
                    f"• Поддержку от меня",
                    reply_markup=markup
                )
                
                bot.answer_callback_query(call.id, "Предлагаем апгрейд")
                return
            else:
                # Уже на этом или высшем тарифе
                bot.answer_callback_query(call.id, f"✅ Вы уже на тарифе {current_tariff}")
                bot.send_message(
                    user_id,
                    f"Вы уже на тарифе '{current_tariff.upper()}'!\n\n"
                    f"Для смены тарифа напишите @artistilja"
                )
                return
    
    # Если пользователя нет ИЛИ не оплатил - сохраняем выбор
    save_user_sync(
        user_id=user_id,
        tariff=selected_tariff,
        amount=selected_amount,
        paid=0
    )
    
    bot.answer_callback_query(call.id, f"Выбрали {selected_tariff}")
    
    # Инструкция по оплате
    message_text = f"""Вы выбрали: {selected_tariff.upper()}

Сумма: {selected_amount}₽

Для оплаты:
1. Переведите {selected_amount}₽ на Сбер по номеру {SBER_PHONE}"""
    
    if SBER_CARD:
        message_text += f"\n\nИли на карту: {SBER_CARD}"
    
    message_text += "\n\n2. Отправьте скриншот сюда"
    
    bot.send_message(user_id, message_text)

@bot.callback_query_handler(func=lambda call: call.data == "upgrade_member")
def handle_upgrade(call):
    """Обработка апгрейда с читателя на участника"""
    user_id = call.from_user.id
    logger.info(f"🔄 Апгрейд тарифа для {user_id}")
    
    # Получаем текущие данные
    user = get_user_sync(user_id)
    
    if not user or user['tariff'] != "читатель":
        bot.answer_callback_query(call.id, "❌ Нельзя выполнить апгрейд")
        return
    
    current_tariff, current_amount = user['tariff'], user['amount']
    new_tariff, new_amount = "участник", 500
    to_pay = new_amount - current_amount  # 400₽
    
    # Обновляем тариф в базе (paid остаётся 1)
    save_user_sync(
        user_id=user_id,
        tariff=new_tariff,
        amount=new_amount,
        paid=1  # Пользователь уже оплатил читателя, остается в статусе оплачено
    )
    
    bot.answer_callback_query(call.id, "✅ Тариф изменен!")
    
    # Инструкция по доплате
    bot.send_message(
        user_id,
        f"🎉 ВЫ ПЕРЕХОДИТЕ НА 'УЧАСТНИКА'!\n\n"
        f"✅ Новый тариф: {new_tariff.upper()}\n"
        f"💰 К доплате: {to_pay}₽\n\n"
        f"Доплатите {to_pay}₽ на Сбер по номеру:\n"
        f"📱 {SBER_PHONE}\n\n"
        f"И отправьте скриншот в этот чат!\n\n"
        f"После доплаты вы получите:\n"
        f"• Обратную связь по работам\n"
        f"• Ответы на вопросы\n"
        f"• Поддержку от меня"
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """Обработка скриншотов оплаты"""
    user_id = message.from_user.id
    logger.info(f"📸 Получен скриншот от {user_id}")
    
    # Получаем данные пользователя
    user = get_user_sync(user_id)
    
    if not user:
        bot.reply_to(message, "❌ Сначала выберите тариф командой /start")
        return
    
    tariff = user['tariff']
    amount = user['amount']
    paid = user['paid']
    
    # Если уже оплатил - проверяем апгрейд
    if paid == 1:
        if tariff == "читатель":
            # Предлагаем апгрейд
            markup = telebot.types.InlineKeyboardMarkup()
            btn_upgrade = telebot.types.InlineKeyboardButton(
                "💎 ПЕРЕЙТИ НА УЧАСТНИКА (+400₽)",
                callback_data="upgrade_member"
            )
            markup.add(btn_upgrade)
            
            bot.send_message(
                user_id,
                f"✅ Вы уже в клубе на тарифе 'ЧИТАТЕЛЬ'!\n\n"
                f"Хотите перейти на 'УЧАСТНИКА'?\n"
                f"• Доплата: 400₽\n"
                f"• Новый тариф: участник (500₽)\n\n"
                f"Получите обратную связь и поддержку:",
                reply_markup=markup
            )
        else:
            bot.reply_to(message, "🎉 Вы на максимальном тарифе - 'УЧАСТНИК'!")
        return
    
    # Если НЕ оплачивал - обновляем статус
    success = update_payment_status_sync(user_id, 1)
    
    if not success:
        bot.reply_to(message, "❌ Ошибка обновления статуса оплаты. Попробуйте еще раз.")
        return
    
    # Создаем ссылку в канал
    try:
        invite = bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int(time.time()) + 2592000  # 30 дней
        )
        
        welcome_message = f"""🎉 ОПЛАТА ПРИНЯТА! ДОБРО ПОЖАЛОВАТЬ!

Тариф: {tariff.upper() if tariff else 'Не указан'}
Сумма: {amount}₽

Ссылка в канал: {invite.invite_link}

Доступ на 30 дней

ℹ️ Вы можете проверить свой тариф в любой момент командой /mytariff

Если возникнут вопросы - пишите @artistilja"""
        
        bot.send_message(
            user_id,
            welcome_message,
            disable_web_page_preview=True
        )
        
        # Уведомление админу
        admin_message = f"""💰 НОВАЯ ОПЛАТА
Пользователь: {message.from_user.first_name} {message.from_user.last_name or ''}
Username: @{message.from_user.username or 'нет'}
ID: {user_id}
Тариф: {tariff or 'не указан'}
Сумма: {amount}₽
Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        bot.send_message(ADMIN_ID, admin_message)
        logger.info(f"💰 Новая оплата от {user_id} ({tariff}, {amount}₽)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания ссылки: {e}")
        bot.send_message(
            user_id,
            f"✅ Оплата принята! Тариф: {tariff.upper()}\n\n"
            f"Ссылка в канал будет отправлена в ближайшее время.\n"
            f"Если возникнут задержки, напишите @artistilja"
        )

@bot.message_handler(commands=['mytariff'])
def my_tariff(message):
    """Показать свой тариф"""
    user_id = message.from_user.id
    logger.info(f"📊 Запрос тарифа от {user_id}")
    
    user = get_user_sync(user_id)
    
    if not user:
        bot.reply_to(message, "❌ Вы еще не выбирали тариф. Используйте /start")
        return
    
    tariff = user['tariff']
    amount = user['amount']
    paid = user['paid']
    screenshot_date = user['screenshot_date']
    
    status = "✅ ОПЛАЧЕНО" if paid == 1 else "⏳ ОЖИДАЕТ ОПЛАТЫ"
    
    response = f"📋 ВАШ ТАРИФ:\n\n"
    response += f"🎯 Тариф: {tariff.upper() if tariff else 'не выбран'}\n"
    response += f"💰 Сумма: {amount}₽\n"
    response += f"📊 Статус: {status}\n"
    
    if paid == 1 and screenshot_date:
        # Форматируем дату
        if isinstance(screenshot_date, str):
            date_str = screenshot_date
        else:
            date_str = screenshot_date.strftime('%d.%m.%Y %H:%M')
        response += f"🕒 Оплачено: {date_str}\n"
    
    # Если читатель и оплатил - предлагаем апгрейд
    if paid == 1 and tariff == "читатель":
        markup = telebot.types.InlineKeyboardMarkup()
        btn_upgrade = telebot.types.InlineKeyboardButton(
            "💎 ПЕРЕЙТИ НА УЧАСТНИКА (+400₽)",
            callback_data="upgrade_member"
        )
        markup.add(btn_upgrade)
        
        response += f"\n⚠️ На вашем тарифе нет обратной связи\n"
        response += f"Хотите получить разборы работ и ответы на вопросы?"
        
        bot.send_message(user_id, response, reply_markup=markup)
    else:
        bot.reply_to(message, response)

# ========== КОМАНДЫ АДМИНА ==========
@bot.message_handler(commands=['remind'])
def remind_all(message):
    """РУЧНАЯ команда - напомнить всем об оплате"""
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ Эта команда только для администратора")
        return
    
    logger.info("🔔 Админ запустил рассылку напоминаний")
    
    # Получаем пользователей, которым нужно напомнить
    try:
        # Создаем новое подключение для напоминаний
        async def get_users_to_remind():
            conn = await get_db_connection()
            if not conn:
                return []
            
            try:
                # Находим всех, кто оплатил больше 25 дней назад
                rows = await conn.fetch("""
                    SELECT user_id, first_name, tariff, screenshot_date 
                    FROM users 
                    WHERE paid = 1 
                    AND screenshot_date IS NOT NULL
                    AND screenshot_date < CURRENT_TIMESTAMP - INTERVAL '25 days'
                """)
                
                users = []
                for row in rows:
                    users.append({
                        'user_id': row['user_id'],
                        'first_name': row['first_name'] or "Пользователь",
                        'tariff': row['tariff'] or "неизвестный",
                        'screenshot_date': row['screenshot_date']
                    })
                
                return users
            finally:
                await conn.close()
        
        # Получаем список пользователей
        users_to_remind = run_async(get_users_to_remind())
        
        if not users_to_remind:
            bot.reply_to(message, "✅ Все подписки активны! Нет пользователей для напоминания.")
            return
        
        count = 0
        errors = 0
        
        # Отправляем напоминания
        for user in users_to_remind:
            try:
                user_id = user['user_id']
                first_name = user['first_name']
                tariff = user['tariff']
                
                reminder_text = f"""🔔 Здравствуйте, {first_name}!

Ваша подписка на тарифе "{tariff.upper()}" скоро закончится!

Прошло более 25 дней с момента последней оплаты.
Для продления подписки напишите команду /start

Если у вас есть вопросы, пишите @artistilja"""
                
                bot.send_message(user_id, reminder_text)
                count += 1
                
                # Небольшая пауза, чтобы не спамить
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки напоминания {user['user_id']}: {e}")
                errors += 1
        
        report = f"""📨 РЕЗУЛЬТАТ РАССЫЛКИ:

Всего найдено: {len(users_to_remind)}
Успешно отправлено: {count}
Ошибок: {errors}

Следующую рассылку можно сделать через 3 дня."""
        
        bot.reply_to(message, report)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /remind: {e}")
        bot.reply_to(message, f"❌ Ошибка при рассылке: {str(e)[:100]}")

@bot.message_handler(commands=['stats'])
def stats(message):
    """Статистика для администратора"""
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ Эта команда только для администратора")
        return
    
    logger.info("📊 Запрос статистики от админа")
    
    try:
        # Получаем статистику через асинхронные функции
        async def get_all_stats():
            conn = await get_db_connection()
            if not conn:
                return None
            
            try:
                # Общее количество пользователей
                total_users = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
                
                # Количество оплативших
                paid_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE paid = 1") or 0
                
                # Общий доход
                total_income = await conn.fetchval("SELECT SUM(amount) FROM users WHERE paid = 1") or 0
                
                # Статистика по тарифам
                readers = await conn.fetchval("SELECT COUNT(*) FROM users WHERE tariff = 'читатель' AND paid = 1") or 0
                members = await conn.fetchval("SELECT COUNT(*) FROM users WHERE tariff = 'участник' AND paid = 1") or 0
                
                return {
                    'total': total_users,
                    'paid': paid_users,
                    'income': total_income,
                    'readers': readers,
                    'members': members
                }
            finally:
                await conn.close()
        
        stats_data = run_async(get_all_stats())
        
        if stats_data is None:
            bot.reply_to(message, "❌ Не удалось получить статистику. Проверьте подключение к БД.")
            return
        
        stats_text = f"""
📊 СТАТИСТИКА ПЛЕНЭРНОГО КЛУБА

👥 Всего пользователей: {stats_data['total']}
💰 Оплатили подписку: {stats_data['paid']}
💵 Общий доход: {stats_data['income']}₽

📈 ПО ТАРИФАМ:
📖 Читатели: {stats_data['readers']}
💎 Участники: {stats_data['members']}

🔔 Для напоминаний: /remind
⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
        
        bot.reply_to(message, stats_text)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /stats: {e}")
        bot.reply_to(message, f"❌ Ошибка получения статистики: {str(e)[:100]}")

@bot.message_handler(commands=['test'])
def test(message):
    """Тестовая команда"""
    user_id = message.from_user.id
    logger.info(f"🧪 Тестовая команда от {user_id}")
    
    # Проверяем подключение к БД
    conn = run_async(get_db_connection())
    db_status = "✅ Подключено" if conn else "❌ Не подключено"
    
    if conn:
        run_async(conn.close())
    
    test_message = f"""🧪 ТЕСТ СИСТЕМЫ

ID пользователя: {user_id}
База данных: {db_status}
Время сервера: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Команды:
/start - начать работу
/mytariff - мой тариф
/stats - статистика (админ)

Бот работает корректно! ✅"""
    
    bot.reply_to(message, test_message)

@bot.message_handler(commands=['help'])
def help_command(message):
    """Команда помощи"""
    help_text = """🆘 ПОМОЩЬ ПО КОМАНДАМ:

/start - Начать работу с ботом
/mytariff - Узнать свой текущий тариф
/help - Показать это сообщение

Для администратора:
/stats - Статистика
/remind - Напомнить об оплате (временно не работает)

Если у вас возникли проблемы:
1. Проверьте, выбрали ли вы тариф
2. Отправьте скриншот оплаты
3. Напишите @artistilja

Приятного использования! 🎨"""
    
    bot.reply_to(message, help_text)

# ========== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ==========
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    """Обработка всех текстовых сообщений"""
    user_id = message.from_user.id
    text = message.text
    
    logger.info(f"💬 Текст от {user_id}: {text[:50]}...")
    
    # Если сообщение похоже на вопрос об оплате
    if any(word in text.lower() for word in ['оплат', 'платёж', 'сбер', 'перевод', 'скриншот']):
        # Проверяем статус пользователя
        user = get_user_sync(user_id)
        
        if not user:
            bot.reply_to(message, "❌ Сначала выберите тариф через /start")
            return
        
        if user['paid'] == 1:
            bot.reply_to(
                message,
                f"✅ Вы уже оплатили тариф '{user['tariff']}'!\n\n"
                f"Проверить статус: /mytariff"
            )
        else:
            bot.reply_to(
                message,
                f"💰 Для оплаты переведите {user['amount']}₽ на:\n"
                f"📱 {SBER_PHONE}\n\n"
                f"И отправьте скриншот оплаты в этот чат."
            )
    
    # Если сообщение похоже на приветствие
    elif any(word in text.lower() for word in ['привет', 'здравствуй', 'hello', 'hi', 'start']):
        bot.reply_to(
            message,
            "👋 Привет! Для начала работы используйте команду /start"
        )
    
    else:
        # Стандартный ответ на неизвестные сообщения
        bot.reply_to(
            message,
            "🤔 Я не совсем понимаю ваш вопрос.\n\n"
            "Используйте команды:\n"
            "/start - начать работу\n"
            "/mytariff - проверить тариф\n"
            "/help - помощь\n\n"
            "Или напишите @artistilja для связи с администратором."
        )

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    # Инициализация базы данных
    logger.info("🤖 Инициализация бота...")
    run_async(init_db())
    
    # Проверяем, запущены ли на Render
    is_render = os.getenv('RENDER', False)
    
    if is_render:
        # НА RENDER: используем вебхуки
        logger.info("🚀 Запуск на Render (режим вебхуков)")
        
        # Получаем URL Render
        render_url = os.getenv('RENDER_EXTERNAL_URL', '')
        if not render_url:
            logger.error("❌ RENDER_EXTERNAL_URL не найден!")
            render_url = "https://your-app-name.onrender.com"
        
        # Устанавливаем вебхук
        try:
            bot.remove_webhook()
            time.sleep(1)
            
            webhook_url = f"{render_url}/webhook"
            logger.info(f"🔄 Установка вебхука: {webhook_url}")
            
            bot.set_webhook(
                url=webhook_url,
                max_connections=50,
                timeout=60
            )
            
            logger.info("✅ Вебхук успешно установлен")
            
            # Запускаем Flask сервер
            port = int(os.getenv('PORT', 10000))
            logger.info(f"🌐 Запуск Flask на порту {port}")
            
            app.run(
                host='0.0.0.0',
                port=port,
                debug=False
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске на Render: {e}")
    
    else:
        # ЛОКАЛЬНО ИЛИ НА ТЕЛЕФОНЕ: используем polling
        logger.info("📱 Запуск в локальном режиме (polling)")
        
        # Удаляем вебхук если был
        try:
            bot.remove_webhook()
            time.sleep(1)
            logger.info("✅ Вебхук удален, переходим в polling режим")
        except:
            pass
        
        # Запускаем polling
        logger.info("🔄 Запуск polling...")
        
        try:
            while True:
                try:
                    bot.polling(
                        none_stop=True,
                        interval=1,
                        timeout=60
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка polling: {e}")
                    logger.info("🔄 Перезапуск polling через 5 секунд...")
                    time.sleep(5)
                    
        except KeyboardInterrupt:
            logger.info("⏹️ Бот остановлен пользователем")
