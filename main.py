# Пленэрный Клуб Бот - ФИНАЛЬНАЯ ВЕРСИЯ с PostgreSQL
# Работает на Render и Pydroid 3

import os
import telebot
import logging
from datetime import datetime
from flask import Flask, request
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import sys

# Принудительно проверяем версию Python
if sys.version_info >= (3, 13):
    print("❌ Python 3.13 не поддерживается! Требуется Python 3.11")
    print("На Render укажите Python 3.11 в runtime.txt и render.yaml")
    sys.exit(1)

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

# ========== БАЗА ДАННЫХ PostgreSQL ==========
def get_db_connection():
    """Подключение к PostgreSQL"""
    try:
        # На Render используйте DATABASE_URL из настроек
        # Для локального тестирования можно временно использовать SQLite
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url:
            logger.error("❌ DATABASE_URL не найден в переменных окружения")
            # Для тестирования на телефоне можно временно вернуть None
            return None
            
        conn = psycopg2.connect(
            database_url,
            cursor_factory=RealDictCursor,
            sslmode='require'  # Для Render требуется SSL
        )
        logger.info("✅ Успешное подключение к PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
        return None

def init_db():
    """Создание таблиц при старте"""
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Не удалось подключиться к БД для инициализации")
        # Создаем таблицы при следующем успешном подключении
        return
    
    try:
        with conn.cursor() as cursor:
            # Основная таблица пользователей
            cursor.execute('''
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
            
            # Создаем индекс для быстрого поиска
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_paid ON users(paid)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_tariff ON users(tariff)")
            
            conn.commit()
            logger.info("✅ Таблицы PostgreSQL успешно созданы/проверены")
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        conn.rollback()
    finally:
        if conn:
            conn.close()

# ========== ФУНКЦИИ РАБОТЫ С БАЗОЙ ==========
def get_user(user_id):
    """Получить пользователя по ID"""
    conn = get_db_connection()
    if not conn:
        logger.warning(f"⚠️ Нет подключения к БД при запросе пользователя {user_id}")
        return None
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT user_id, username, first_name, last_name, 
                       tariff, amount, paid, screenshot_date, 
                       registered_at, updated_at 
                FROM users 
                WHERE user_id = %s
            """, (user_id,))
            result = cursor.fetchone()
            return result
    except Exception as e:
        logger.error(f"❌ Ошибка получения пользователя {user_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def save_user(user_id, username=None, first_name=None, last_name=None, 
              tariff=None, amount=0, paid=0):
    """Сохранить или обновить пользователя"""
    conn = get_db_connection()
    if not conn:
        logger.warning(f"⚠️ Нет подключения к БД при сохранении пользователя {user_id}")
        return False
    
    try:
        with conn.cursor() as cursor:
            # Используем UPSERT (INSERT ... ON CONFLICT)
            cursor.execute("""
                INSERT INTO users 
                (user_id, username, first_name, last_name, tariff, amount, paid, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    tariff = EXCLUDED.tariff,
                    amount = EXCLUDED.amount,
                    paid = EXCLUDED.paid,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, username, first_name, last_name, tariff, amount, paid))
            
            conn.commit()
            logger.info(f"✅ Пользователь {user_id} сохранен/обновлен в PostgreSQL")
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения пользователя {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def update_payment_status(user_id, paid=1):
    """Обновить статус оплаты"""
    conn = get_db_connection()
    if not conn:
        logger.warning(f"⚠️ Нет подключения к БД при обновлении оплаты {user_id}")
        return False
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE users 
                SET paid = %s, 
                    screenshot_date = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            """, (paid, user_id))
            
            affected_rows = cursor.rowcount
            conn.commit()
            
            if affected_rows > 0:
                logger.info(f"✅ Статус оплаты обновлен для {user_id}")
                return True
            else:
                logger.warning(f"⚠️ Пользователь {user_id} не найден при обновлении оплаты")
                return False
                
    except Exception as e:
        logger.error(f"❌ Ошибка обновления оплаты {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_user_count():
    """Получить общее количество пользователей"""
    conn = get_db_connection()
    if not conn:
        return 0
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM users")
            result = cursor.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества пользователей: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def get_paid_users_count():
    """Получить количество оплативших пользователей"""
    conn = get_db_connection()
    if not conn:
        return 0
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE paid = 1")
            result = cursor.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества оплативших: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def get_total_income():
    """Получить общий доход"""
    conn = get_db_connection()
    if not conn:
        return 0
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT SUM(amount) as total FROM users WHERE paid = 1")
            result = cursor.fetchone()
            return result['total'] if result and result['total'] else 0
    except Exception as e:
        logger.error(f"❌ Ошибка получения общего дохода: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def get_tariff_stats():
    """Получить статистику по тарифам"""
    conn = get_db_connection()
    if not conn:
        return {"читатель": 0, "участник": 0}
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT tariff, COUNT(*) as count 
                FROM users 
                WHERE paid = 1 AND tariff IS NOT NULL
                GROUP BY tariff
            """)
            results = cursor.fetchall()
            
            stats = {"читатель": 0, "участник": 0}
            for row in results:
                tariff = row['tariff']
                count = row['count']
                if tariff in stats:
                    stats[tariff] = count
            
            return stats
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики по тарифам: {e}")
        return {"читатель": 0, "участник": 0}
    finally:
        if conn:
            conn.close()

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
        # Проверяем подключение к БД
        conn = get_db_connection()
        if conn:
            conn.close()
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
    save_user(
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
    user = get_user(user_id)
    
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
    save_user(
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
    user = get_user(user_id)
    
    if not user or user['tariff'] != "читатель":
        bot.answer_callback_query(call.id, "❌ Нельзя выполнить апгрейд")
        return
    
    current_tariff, current_amount = user['tariff'], user['amount']
    new_tariff, new_amount = "участник", 500
    to_pay = new_amount - current_amount  # 400₽
    
    # Обновляем тариф в базе (paid остаётся 1)
    save_user(
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
    user = get_user(user_id)
    
    if not user:
        bot.reply_to(message, "❌ Сначала выберите тариф командой /start")
        return
    
    tariff, amount, paid = user['tariff'], user['amount'], user['paid']
    
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
    success = update_payment_status(user_id, 1)
    
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
    
    user = get_user(user_id)
    
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
    
    conn = get_db_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к БД")
        return
    
    try:
        with conn.cursor() as cursor:
            # Находим всех, кто оплатил больше 25 дней назад
            # (даем 5 дней на оплату после напоминания)
            cursor.execute("""
                SELECT user_id, first_name, tariff, screenshot_date 
                FROM users 
                WHERE paid = 1 
                AND screenshot_date IS NOT NULL
                AND screenshot_date <= CURRENT_DATE - INTERVAL '25 days'
            """)
            
            users = cursor.fetchall()
            
            if not users:
                bot.reply_to(message, "✅ Все подписки активны! Нет пользователей для напоминания.")
                return
            
            count = 0
            errors = 0
            
            for user in users:
                try:
                    user_id = user['user_id']
                    first_name = user['first_name'] or "Пользователь"
                    tariff = user['tariff'] or "неизвестный"
                    
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

Всего найдено: {len(users)}
Успешно отправлено: {count}
Ошибок: {errors}

Следующую рассылку можно сделать через 3 дня."""
            
            bot.reply_to(message, report)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /remind: {e}")
        bot.reply_to(message, f"❌ Ошибка при рассылке: {str(e)[:100]}")
    finally:
        if conn:
            conn.close()

@bot.message_handler(commands=['stats'])
def stats(message):
    """Статистика"""
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ Эта команда только для администратора")
        return
    
    logger.info("📊 Запрос статистики от админа")
    
    # Получаем все статистики
    total_users = get_user_count()
    paid_users = get_paid_users_count()
    total_income = get_total_income()
    tariff_stats = get_tariff_stats()
    
    stats_text = f"""
📊 СТАТИСТИКА ПЛЕНЭРНОГО КЛУБА

👥 Всего пользователей: {total_users}
💰 Оплатили подписку: {paid_users}
💵 Общий доход: {total_income}₽

📈 ПО ТАРИФАМ:
📖 Читатели: {tariff_stats.get('читатель', 0)}
💎 Участники: {tariff_stats.get('участник', 0)}

🔔 Управление:
/remind - напомнить об оплате
/stats - обновить статистику

⏰ Последнее обновление: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
    
    bot.reply_to(message, stats_text)

@bot.message_handler(commands=['test'])
def test(message):
    """Тестовая команда"""
    user_id = message.from_user.id
    logger.info(f"🧪 Тестовая команда от {user_id}")
    
    # Проверяем подключение к БД
    conn = get_db_connection()
    db_status = "✅ Подключено" if conn else "❌ Не подключено"
    
    if conn:
        conn.close()
    
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
/remind - Напомнить об оплате

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
        user = get_user(user_id)
        
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
    init_db()
    
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