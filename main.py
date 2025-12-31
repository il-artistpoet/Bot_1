# Пленэрный Клуб Бот - РАБОЧАЯ ВЕРСИЯ
import os
import telebot
import logging
from datetime import datetime
from flask import Flask, request
import time
import psycopg2
from psycopg2.extras import RealDictCursor

print("🚀 Бот запускается...")

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
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.warning("⚠️ DATABASE_URL не найден")
            return None
        
        # Фикс URL для psycopg2
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        conn = psycopg2.connect(
            database_url,
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка подключения: {e}")
        return None

def init_db():
    """Создание таблиц"""
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Не удалось подключиться для инициализации")
        return
    
    try:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(100),
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    tariff VARCHAR(50),
                    amount INTEGER DEFAULT 0,
                    paid INTEGER DEFAULT 0,
                    screenshot_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            logger.info("✅ Таблица users создана/проверена")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблицы: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_user(user_id):
    """Получить пользователя"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()
    except Exception as e:
        logger.error(f"❌ Ошибка get_user: {e}")
        return None
    finally:
        conn.close()

def save_user(user_id, username=None, first_name=None, last_name=None, 
              tariff=None, amount=0, paid=0):
    """Сохранить пользователя"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            # Простой UPSERT
            cur.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, tariff, amount, paid)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    tariff = EXCLUDED.tariff,
                    amount = EXCLUDED.amount,
                    paid = EXCLUDED.paid,
                    created_at = CURRENT_TIMESTAMP
            """, (user_id, username, first_name, last_name, tariff, amount, paid))
            
            conn.commit()
            logger.info(f"✅ Пользователь {user_id} сохранен")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка save_user: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_payment(user_id):
    """Обновить оплату"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET paid = 1, screenshot_date = CURRENT_TIMESTAMP 
                WHERE user_id = %s
            """, (user_id,))
            conn.commit()
            logger.info(f"✅ Оплата обновлена для {user_id}")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка update_payment: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_stats():
    """Получить статистику"""
    conn = get_db_connection()
    if not conn:
        return {"total": 0, "paid": 0, "income": 0, "readers": 0, "members": 0}
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM users")
            total = cur.fetchone()['count']
            
            cur.execute("SELECT COUNT(*) as count FROM users WHERE paid = 1")
            paid = cur.fetchone()['count']
            
            cur.execute("SELECT SUM(amount) as total FROM users WHERE paid = 1")
            income = cur.fetchone()['total'] or 0
            
            cur.execute("SELECT COUNT(*) as count FROM users WHERE tariff = 'читатель' AND paid = 1")
            readers = cur.fetchone()['count']
            
            cur.execute("SELECT COUNT(*) as count FROM users WHERE tariff = 'участник' AND paid = 1")
            members = cur.fetchone()['count']
            
            return {
                "total": total,
                "paid": paid,
                "income": income,
                "readers": readers,
                "members": members
            }
    except Exception as e:
        logger.error(f"❌ Ошибка get_stats: {e}")
        return {"total": 0, "paid": 0, "income": 0, "readers": 0, "members": 0}
    finally:
        conn.close()

# Инициализация БД
init_db()

# ========== ВЕБХУК ДЛЯ RENDER ==========
@app.route('/')
def home():
    return "🎨 Пленэрный Клуб Бот работает!"

@app.route('/health')
def health():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
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
    
    logger.info(f"🚀 /start от {user_id}")
    
    # Сохраняем пользователя
    save_user(user_id, username, first_name, last_name)
    
    # Пытаемся отправить фото
    try:
        with open('photo.png', 'rb') as photo:
            bot.send_photo(user_id, photo)
    except:
        pass
    
    # Кнопки
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn_more = telebot.types.InlineKeyboardButton("Узнать больше", url=TILDA_LINK)
    btn_club = telebot.types.InlineKeyboardButton("Хочу в клуб!", callback_data="join_club")
    markup.add(btn_more, btn_club)
    
    welcome_text = (
        "🎨Приветствую Вас! Оставайтесь на волне созерцания и пленэра.\n\n"
        "Здесь можно купить подписку и получить доступ в \"Пленэрный Клуб\"!\n\n"
        "Это закрытый телеграм-канал, где все участники могут делиться своим творчеством "
        "и получать от меня обратную связь."
    )
    
    bot.send_message(user_id, welcome_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "join_club")
def show_tariffs(call):
    user_id = call.from_user.id
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    btn_reader = telebot.types.InlineKeyboardButton("🔥 ЧИТАТЕЛЬ — 100₽/месяц", callback_data="tariff_reader")
    btn_member = telebot.types.InlineKeyboardButton("💎 УЧАСТНИК — 500₽/месяц", callback_data="tariff_member")
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
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data in ["tariff_reader", "tariff_member"])
def handle_tariff(call):
    user_id = call.from_user.id
    
    if call.data == "tariff_reader":
        selected_tariff, selected_amount = "читатель", 100
    else:
        selected_tariff, selected_amount = "участник", 500
    
    # Проверяем пользователя
    user = get_user(user_id)
    
    if user and user['paid'] == 1:
        if user['tariff'] == "читатель" and selected_tariff == "участник":
            # Предлагаем апгрейд
            to_pay = 400
            markup = telebot.types.InlineKeyboardMarkup()
            btn_upgrade = telebot.types.InlineKeyboardButton(f"💎 ПЕРЕЙТИ (+{to_pay}₽)", callback_data="upgrade_member")
            markup.add(btn_upgrade)
            
            bot.send_message(
                user_id,
                f"✅ Вы уже оплатили тариф 'ЧИТАТЕЛЬ'!\n\n"
                f"Хотите перейти на тариф 'УЧАСТНИК'?\n"
                f"• Ваш тариф: читатель (100₽)\n"
                f"• Новый тариф: участник (500₽)\n"
                f"• К доплате: {to_pay}₽\n\n"
                f"Вы получите обратную связь и поддержку!",
                reply_markup=markup
            )
            bot.answer_callback_query(call.id, "Предлагаем апгрейд")
            return
        else:
            bot.answer_callback_query(call.id, f"✅ Вы уже на тарифе {user['tariff']}")
            bot.send_message(user_id, f"Вы уже на тарифе '{user['tariff'].upper()}'!")
            return
    
    # Сохраняем выбор
    save_user(user_id, tariff=selected_tariff, amount=selected_amount, paid=0)
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
    user_id = call.from_user.id
    user = get_user(user_id)
    
    if not user or user['tariff'] != "читатель":
        bot.answer_callback_query(call.id, "❌ Нельзя выполнить апгрейд")
        return
    
    # Обновляем тариф
    save_user(user_id, tariff="участник", amount=500, paid=1)
    bot.answer_callback_query(call.id, "✅ Тариф изменен!")
    
    bot.send_message(
        user_id,
        f"🎉 ВЫ ПЕРЕХОДИТЕ НА 'УЧАСТНИКА'!\n\n"
        f"✅ Новый тариф: УЧАСТНИК\n"
        f"💰 К доплате: 400₽\n\n"
        f"Доплатите 400₽ на Сбер:\n"
        f"📱 {SBER_PHONE}\n\n"
        f"И отправьте скриншот!"
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        bot.reply_to(message, "❌ Сначала выберите тариф!")
        return
    
    if user['paid'] == 1:
        if user['tariff'] == "читатель":
            markup = telebot.types.InlineKeyboardMarkup()
            btn_upgrade = telebot.types.InlineKeyboardButton("💎 ПЕРЕЙТИ НА УЧАСТНИКА (+400₽)", callback_data="upgrade_member")
            markup.add(btn_upgrade)
            bot.send_message(user_id, "✅ Вы уже оплатили 'ЧИТАТЕЛЬ'! Хотите апгрейд?", reply_markup=markup)
        else:
            bot.reply_to(message, "🎉 Вы на максимальном тарифе!")
        return
    
    # Обновляем оплату
    update_payment(user_id)
    
    try:
        invite = bot.create_chat_invite_link(chat_id=CHANNEL_ID, member_limit=1)
        bot.send_message(
            user_id,
            f"🎉 ОПЛАТА ПРИНЯТА! ДОБРО ПОЖАЛОВАТЬ!\n\n"
            f"Тариф: {user['tariff'].upper()}\n"
            f"Сумма: {user['amount']}₽\n\n"
            f"Ссылка в канал: {invite.invite_link}\n\n"
            f"Доступ на 30 дней",
            disable_web_page_preview=True
        )
        bot.send_message(user_id, "ℹ️ Проверить тариф: /mytariff")
        
        # Уведомление админу
        bot.send_message(
            ADMIN_ID,
            f"💰 НОВАЯ ОПЛАТА\nПользователь: {message.from_user.first_name}\nID: {user_id}\nТариф: {user['tariff']}\nСумма: {user['amount']}₽"
        )
    except:
        bot.send_message(user_id, "✅ Оплата принята! Ссылка будет скоро.")

@bot.message_handler(commands=['mytariff'])
def my_tariff(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        bot.reply_to(message, "❌ Вы еще не выбирали тариф")
        return
    
    status = "✅ ОПЛАЧЕНО" if user['paid'] == 1 else "⏳ ОЖИДАЕТ ОПЛАТЫ"
    response = f"📋 ВАШ ТАРИФ:\n\n🎯 Тариф: {user['tariff'].upper()}\n💰 Сумма: {user['amount']}₽\n📊 Статус: {status}"
    
    if user['paid'] == 1 and user['screenshot_date']:
        response += f"\n🕒 Оплачено: {user['screenshot_date'].strftime('%d.%m.%Y')}"
    
    if user['paid'] == 1 and user['tariff'] == "читатель":
        markup = telebot.types.InlineKeyboardMarkup()
        btn_upgrade = telebot.types.InlineKeyboardButton("💎 ПЕРЕЙТИ НА УЧАСТНИКА (+400₽)", callback_data="upgrade_member")
        markup.add(btn_upgrade)
        response += "\n\n⚠️ На вашем тарифе нет обратной связи"
        bot.send_message(user_id, response, reply_markup=markup)
    else:
        bot.reply_to(message, response)

@bot.message_handler(commands=['remind'])
def remind_all(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = get_db_connection()
    if not conn:
        bot.reply_to(message, "❌ Ошибка подключения к БД")
        return
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, first_name, tariff 
                FROM users 
                WHERE paid = 1 AND screenshot_date IS NOT NULL
                AND screenshot_date < CURRENT_TIMESTAMP - INTERVAL '25 days'
            """)
            users = cur.fetchall()
            
            if not users:
                bot.reply_to(message, "✅ Все подписки активны!")
                return
            
            count = 0
            for user in users:
                try:
                    bot.send_message(
                        user['user_id'],
                        f"🔔 Здравствуйте, {user['first_name'] or 'Пользователь'}!\n\n"
                        f"Ваша подписка на тарифе \"{user['tariff'].upper()}\" скоро закончится!\n"
                        f"Для продления напишите /start"
                    )
                    count += 1
                    time.sleep(0.5)
                except:
                    pass
            
            bot.reply_to(message, f"📨 Отправлено напоминаний: {count}")
    except Exception as e:
        logger.error(f"Ошибка /remind: {e}")
        bot.reply_to(message, f"❌ Ошибка: {e}")
    finally:
        conn.close()

@bot.message_handler(commands=['stats'])
def stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    stats_data = get_stats()
    stats_text = f"""
📊 СТАТИСТИКА:

👥 Всего пользователей: {stats_data['total']}
💰 Оплатили: {stats_data['paid']}
💵 Доход: {stats_data['income']}₽
📖 Читатели: {stats_data['readers']}
💎 Участники: {stats_data['members']}

🔔 Для напоминаний: /remind
"""
    bot.reply_to(message, stats_text)

@bot.message_handler(commands=['test'])
def test(message):
    bot.reply_to(message, f"✅ Бот работает! Ваш ID: {message.from_user.id}")

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """🆘 ПОМОЩЬ:

/start - Начать работу
/mytariff - Мой тариф
/help - Помощь

Для администратора:
/stats - Статистика
/remind - Напомнить об оплате
"""
    bot.reply_to(message, help_text)

# ========== ОБРАБОТКА СЛУЧАЙНЫХ СООБЩЕНИЙ ==========
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
    is_render = os.getenv('RENDER', False)
    
    if is_render:
        logger.info("🚀 Запуск на Render")
        render_url = os.getenv('RENDER_EXTERNAL_URL', '')
        if render_url:
            bot.remove_webhook()
            time.sleep(1)
            webhook_url = f"{render_url}/webhook"
            bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Вебхук установлен: {webhook_url}")
        
        port = int(os.getenv('PORT', 8080))
        app.run(host='0.0.0.0', port=port)
    else:
        logger.info("📱 Запуск локально")
        bot.remove_webhook()
        time.sleep(1)
        bot.polling(none_stop=True)
