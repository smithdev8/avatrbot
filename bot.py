import os
import asyncio
import logging
import json
import time
import sqlite3
import hashlib
import hmac
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from io import BytesIO
import base64
from decimal import Decimal

# Telegram imports
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# External imports
import replicate
import aiohttp
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(
    MAIN_MENU,
    CHOOSING_MODE,
    UPLOADING_INSTANT,
    UPLOADING_LORA,
    SELECTING_STYLE,
    GENERATING,
    WAITING_LORA,
    ADMIN_PANEL,
    ADMIN_USER_SEARCH,
    ADMIN_ADD_CREDITS,
    PAYMENT_AMOUNT,
    PAYMENT_CRYPTO
) = range(12)

# Расширенные стили
STYLES = {
    "cyberpunk": {
        "name": "🤖 Киберпанк",
        "prompt": "cyberpunk style, neon lights, futuristic city, holographic, blade runner aesthetic",
        "negative": "boring, plain",
        "credits": 1
    },
    "anime": {
        "name": "🎌 Аниме",
        "prompt": "anime style, manga art, studio ghibli quality, expressive eyes",
        "negative": "realistic, western",
        "credits": 1
    },
    "fantasy": {
        "name": "🧙 Фэнтези", 
        "prompt": "fantasy art, magical, lord of the rings style, epic lighting",
        "negative": "modern, mundane",
        "credits": 1
    },
    "superhero": {
        "name": "🦸 Супергерой",
        "prompt": "marvel superhero style, dramatic pose, cinematic lighting",
        "negative": "weak, ordinary",
        "credits": 1
    },
    "portrait": {
        "name": "🎨 Профессиональный портрет",
        "prompt": "professional headshot, studio lighting, LinkedIn profile photo, clean background",
        "negative": "amateur, messy",
        "credits": 1
    },
    "business": {
        "name": "💼 Бизнес хедшот",
        "prompt": "corporate headshot, business professional, confident, suit, office background",
        "negative": "casual, unprofessional",
        "credits": 1
    },
    "creative": {
        "name": "🎭 Креативный портрет",
        "prompt": "creative portrait, artistic lighting, unique angle, fashion photography",
        "negative": "boring, standard",
        "credits": 2
    },
    "vintage": {
        "name": "📷 Винтаж",
        "prompt": "vintage photography, 1950s style, retro colors, film grain, nostalgic",
        "negative": "modern, digital",
        "credits": 1
    },
    "neon": {
        "name": "💜 Неоновый портрет",
        "prompt": "neon portrait, synthwave, vaporwave aesthetic, pink and blue lights",
        "negative": "dull colors",
        "credits": 1
    },
    "oil_painting": {
        "name": "🖼️ Масляная живопись",
        "prompt": "oil painting style, renaissance portrait, rembrandt lighting, classical art",
        "negative": "digital, modern",
        "credits": 2
    },
    "watercolor": {
        "name": "🎨 Акварель",
        "prompt": "watercolor portrait, soft colors, artistic brush strokes, delicate",
        "negative": "harsh, digital",
        "credits": 1
    },
    "comic": {
        "name": "💥 Комикс",
        "prompt": "comic book style, marvel comics, bold lines, halftone dots, action hero",
        "negative": "realistic, soft",
        "credits": 1
    },
    "pixar": {
        "name": "🎬 Pixar 3D",
        "prompt": "pixar 3d animation style, disney character, cute, colorful, high quality render",
        "negative": "2d, realistic",
        "credits": 2
    },
    "gta": {
        "name": "🎮 GTA стиль",
        "prompt": "grand theft auto loading screen art style, gta 5, rockstar games artwork",
        "negative": "realistic photo",
        "credits": 1
    },
    "avatar": {
        "name": "🌍 Avatar (Джеймс Кэмерон)",
        "prompt": "avatar movie style, na'vi character, pandora, bioluminescent, james cameron",
        "negative": "human, earth",
        "credits": 2
    },
    "steampunk": {
        "name": "⚙️ Стимпанк",
        "prompt": "steampunk portrait, victorian era, brass goggles, gears, mechanical",
        "negative": "modern, digital",
        "credits": 1
    },
    "linkedin": {
        "name": "👔 LinkedIn фото",
        "prompt": "professional linkedin headshot, friendly smile, business casual, white background",
        "negative": "unprofessional",
        "credits": 1
    },
    "tinder": {
        "name": "❤️ Tinder/Dating",
        "prompt": "attractive dating profile photo, natural smile, casual but stylish, good lighting",
        "negative": "formal, stiff",
        "credits": 1
    },
    "magazine": {
        "name": "📸 Обложка журнала",
        "prompt": "vogue magazine cover photo, high fashion, editorial photography, dramatic",
        "negative": "amateur, simple",
        "credits": 2
    },
    "movie_poster": {
        "name": "🎬 Постер фильма",
        "prompt": "movie poster style, cinematic, hollywood blockbuster, epic composition",
        "negative": "amateur, simple",
        "credits": 2
    }
}

# База данных
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        self.create_tables()
        
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                credits INTEGER DEFAULT 3,
                total_spent REAL DEFAULT 0,
                lora_model TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица транзакций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                credits INTEGER,
                crypto TEXT,
                tx_hash TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица генераций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                mode TEXT,
                style TEXT,
                credits_used INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.conn.commit()
    
    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> dict:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, credits)
                VALUES (?, ?, ?, 3)
            ''', (user_id, username, first_name))
            self.conn.commit()
            return self.get_or_create_user(user_id)
        
        # Обновляем last_active
        cursor.execute('''
            UPDATE users SET last_active = CURRENT_TIMESTAMP 
            WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()
        
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'credits': user[3],
            'total_spent': user[4],
            'lora_model': user[5]
        }
    
    def update_credits(self, user_id: int, credits: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users SET credits = credits + ? WHERE user_id = ?
        ''', (credits, user_id))
        self.conn.commit()
    
    def use_credits(self, user_id: int, credits: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('SELECT credits FROM users WHERE user_id = ?', (user_id,))
        current = cursor.fetchone()[0]
        
        if current >= credits:
            cursor.execute('''
                UPDATE users SET credits = credits - ? WHERE user_id = ?
            ''', (credits, user_id))
            self.conn.commit()
            return True
        return False
    
    def save_lora_model(self, user_id: int, model_url: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users SET lora_model = ? WHERE user_id = ?
        ''', (model_url, user_id))
        self.conn.commit()
    
    def add_transaction(self, user_id: int, tx_type: str, amount: float, credits: int, 
                       crypto: str = None, tx_hash: str = None, status: str = 'pending'):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, type, amount, credits, crypto, tx_hash, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, tx_type, amount, credits, crypto, tx_hash, status))
        self.conn.commit()
        return cursor.lastrowid
    
    def log_generation(self, user_id: int, mode: str, style: str, credits_used: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO generations (user_id, mode, style, credits_used)
            VALUES (?, ?, ?, ?)
        ''', (user_id, mode, style, credits_used))
        self.conn.commit()
    
    def get_stats(self) -> dict:
        cursor = self.conn.cursor()
        
        # Общая статистика
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(last_active) = DATE("now")')
        daily_active = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM generations WHERE DATE(created_at) = DATE("now")')
        daily_generations = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE status = "completed"')
        total_revenue = cursor.fetchone()[0] or 0
        
        # Топ пользователи
        cursor.execute('''
            SELECT user_id, username, COUNT(*) as gen_count 
            FROM generations 
            GROUP BY user_id 
            ORDER BY gen_count DESC 
            LIMIT 5
        ''')
        top_users = cursor.fetchall()
        
        return {
            'total_users': total_users,
            'daily_active': daily_active,
            'daily_generations': daily_generations,
            'total_revenue': total_revenue,
            'top_users': top_users
        }

# Криптовалютные платежи
class CryptoPayments:
    def __init__(self):
        # Здесь должны быть ваши крипто-адреса
        self.addresses = {
            'USDT_TRC20': 'TYourTronAddressHere',
            'USDT_ERC20': '0xYourEthAddressHere',
            'BTC': 'bc1qYourBtcAddressHere',
            'ETH': '0xYourEthAddressHere',
            'TON': 'UQYourTonAddressHere'
        }
        
        self.prices = {
            10: 5.0,    # 10 кредитов за $5
            25: 10.0,   # 25 кредитов за $10
            60: 20.0,   # 60 кредитов за $20
            150: 40.0,  # 150 кредитов за $40
        }
    
    def get_payment_address(self, crypto: str) -> str:
        return self.addresses.get(crypto, '')
    
    def generate_payment_message(self, crypto: str, amount: float, credits: int) -> str:
        address = self.get_payment_address(crypto)
        
        message = f"""
💳 **Оплата {credits} кредитов**

Сумма: **${amount}**
Криптовалюта: **{crypto}**

Адрес для оплаты:
`{address}`

📋 Инструкция:
1. Отправьте точную сумму на адрес выше
2. Скопируйте хеш транзакции
3. Нажмите кнопку "Я оплатил" и отправьте хеш
4. Кредиты будут начислены после проверки

⚠️ Важно: отправляйте точную сумму!
        """
        return message

# Основной класс бота
class AvatarBot:
    def __init__(self, telegram_token: str, replicate_token: str, admin_ids: List[int]):
        self.telegram_token = telegram_token.strip()
        replicate_token = replicate_token.strip()
        os.environ["REPLICATE_API_TOKEN"] = replicate_token
        self.admin_ids = admin_ids
        self.db = Database()
        self.crypto = CryptoPayments()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню"""
        user = update.effective_user
        
        # Регистрация пользователя в БД
        user_data = self.db.get_or_create_user(
            user.id, 
            user.username, 
            user.first_name
        )
        
        # Сброс состояния
        context.user_data.clear()
        context.user_data['db_user'] = user_data
        
        keyboard = [
            [InlineKeyboardButton(f"💰 Баланс: {user_data['credits']} кредитов", callback_data="balance")],
            [InlineKeyboardButton("⚡ Быстрая генерация (1 кредит)", callback_data="mode_instant")],
            [InlineKeyboardButton("🎯 Pro LoRA (20 кредитов)", callback_data="mode_lora")],
            [InlineKeyboardButton("💳 Купить кредиты", callback_data="buy_credits")],
            [InlineKeyboardButton("📊 Мои генерации", callback_data="my_stats")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        
        # Админ кнопка
        if user.id in self.admin_ids:
            keyboard.append([InlineKeyboardButton("👨‍💼 Админ панель", callback_data="admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"Привет, {user.first_name}! 👋\n\n"
            "🎨 **AI Avatar Generator Bot**\n\n"
            f"💰 У вас: **{user_data['credits']} кредитов**\n\n"
            "Выберите действие:"
        )
        
        if update.message:
            await update.message.reply_text(
                welcome_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.edit_message_text(
                welcome_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        
        return MAIN_MENU
    
    async def mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор режима генерации"""
        query = update.callback_query
        await query.answer()
        
        user_data = context.user_data['db_user']
        
        if query.data == "mode_instant":
            if user_data['credits'] < 1:
                await query.answer("❌ Недостаточно кредитов! Минимум 1 кредит.", show_alert=True)
                return MAIN_MENU
            
            context.user_data['mode'] = 'instant'
            context.user_data['photos'] = []
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
            
            await query.edit_message_text(
                "⚡ **Быстрый режим**\n\n"
                "📸 Отправьте одно четкое фото лица:\n\n"
                "Требования:\n"
                "• Фронтальный ракурс\n"
                "• Хорошее освещение\n"
                "• Четкое лицо\n\n"
                "Стоимость: 1 кредит за генерацию",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return UPLOADING_INSTANT
            
        elif query.data == "mode_lora":
            if user_data['credits'] < 20:
                await query.answer(f"❌ Недостаточно кредитов! Нужно 20, у вас {user_data['credits']}", show_alert=True)
                return MAIN_MENU
            
            context.user_data['mode'] = 'lora'
            context.user_data['photos'] = []
            context.user_data['photos_base64'] = []
            context.user_data['photo_count'] = 0
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
            
            await query.edit_message_text(
                "🎯 **Pro режим (LoRA)**\n\n"
                "📸 Отправьте 5-10 фотографий:\n\n"
                "• Разные ракурсы\n"
                "• Разные выражения\n"
                "• Четкие фото\n\n"
                "Стоимость: 20 кредитов\n"
                "Отправлено: 0/10",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return UPLOADING_LORA
    
    async def handle_instant_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка фото для быстрого режима"""
        try:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            
            photo_bytes = BytesIO()
            await file.download_to_memory(photo_bytes)
            photo_bytes.seek(0)
            
            context.user_data['photos'] = [photo_bytes]
            
            # Показываем стили
            keyboard = []
            row = []
            for i, (style_id, style_info) in enumerate(STYLES.items()):
                btn = InlineKeyboardButton(
                    f"{style_info['name']} ({style_info['credits']}💰)",
                    callback_data=f"style_{style_id}"
                )
                row.append(btn)
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
            
            await update.message.reply_text(
                "✅ Фото получено!\n\nВыберите стиль генерации:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return SELECTING_STYLE
            
        except Exception as e:
            logger.error(f"Error handling photo: {e}")
            await update.message.reply_text("❌ Ошибка при обработке фото. /start")
            return ConversationHandler.END
    
    async def handle_lora_photos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка фото для LoRA"""
        try:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            
            photo_bytes = BytesIO()
            await file.download_to_memory(photo_bytes)
            photo_bytes.seek(0)
            
            # Конвертируем в base64
            photo_base64 = base64.b64encode(photo_bytes.read()).decode('utf-8')
            photo_bytes.seek(0)
            
            context.user_data['photos'].append(photo_bytes)
            context.user_data['photos_base64'].append(f"data:image/jpeg;base64,{photo_base64}")
            context.user_data['photo_count'] = len(context.user_data['photos'])
            
            count = context.user_data['photo_count']
            
            if count < 5:
                await update.message.reply_text(
                    f"📸 Получено: {count}/10\n"
                    f"Минимум еще: {5 - count}"
                )
                return UPLOADING_LORA
            elif count < 10:
                keyboard = [
                    [InlineKeyboardButton(f"✅ Начать обучение ({count} фото)", callback_data="lora_ready")],
                    [InlineKeyboardButton("➕ Добавить еще", callback_data="lora_more")]
                ]
                await update.message.reply_text(
                    f"📸 Получено {count} фото.\nНачать обучение или добавить еще?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return UPLOADING_LORA
            else:
                # Проверяем кредиты и начинаем обучение
                user_id = update.effective_user.id
                if self.db.use_credits(user_id, 20):
                    await update.message.reply_text(
                        "✅ 10 фото получено!\n"
                        "💰 Списано 20 кредитов\n"
                        "🚀 Начинаю обучение модели...\n"
                        "⏳ Это займет 15-20 минут"
                    )
                    return await self._start_lora_training(update, context)
                else:
                    await update.message.reply_text("❌ Недостаточно кредитов!")
                    return ConversationHandler.END
                    
        except Exception as e:
            logger.error(f"Error: {e}")
            return UPLOADING_LORA
    

    async def handle_lora_decision(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка решения о количестве фото для LoRA"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "lora_ready":
            user_id = update.effective_user.id
            if self.db.use_credits(user_id, 20):
                await query.edit_message_text(
                    "💰 Списано 20 кредитов\n"
                    "🚀 Начинаю обучение модели...\n"
                    "⏳ Это займет 15-20 минут"
                )
                return await self._start_lora_training(update, context)
            else:
                await query.answer("❌ Недостаточно кредитов!", show_alert=True)
                return ConversationHandler.END
                
        elif query.data == "lora_more":
            count = context.user_data.get('photo_count', 0)
            await query.edit_message_text(
                f"📸 Отправьте еще фото (сейчас {count}/10):"
            )
            return UPLOADING_LORA
    async def handle_style_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор стиля и генерация"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "back_to_menu":
            return await self.start(update, context)
        
        style_id = query.data.replace("style_", "")
        if style_id not in STYLES:
            return SELECTING_STYLE
            
        style_info = STYLES[style_id]
        user_id = update.effective_user.id
        
        # Проверяем кредиты
        required_credits = style_info['credits']
        user_data = self.db.get_or_create_user(user_id)
        
        if user_data['credits'] < required_credits:
            await query.answer(
                f"❌ Недостаточно кредитов! Нужно {required_credits}, у вас {user_data['credits']}", 
                show_alert=True
            )
            return SELECTING_STYLE
        
        # Списываем кредиты
        if not self.db.use_credits(user_id, required_credits):
            await query.answer("❌ Ошибка списания кредитов", show_alert=True)
            return SELECTING_STYLE
        
        context.user_data['selected_style'] = style_id
        
        await query.edit_message_text(
            f"Стиль: {style_info['name']}\n"
            f"💰 Списано: {required_credits} кредитов\n\n"
            "🎨 Генерирую...\n"
            "⏳ Подождите 30-60 секунд..."
        )
        
        # Логируем генерацию
        self.db.log_generation(user_id, context.user_data['mode'], style_id, required_credits)
        
        # Запускаем генерацию
        if context.user_data.get('mode') == 'instant':
            return await self._generate_instant_id(update, context)
        else:
            return await self._generate_with_lora(update, context)
    
    async def _generate_instant_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация через Instant ID"""
        try:
            style_id = context.user_data['selected_style']
            style_info = STYLES[style_id]
            photo = context.user_data['photos'][0]
            photo.seek(0)
            
            logger.info(f"Generating with grandlineai/instant-id for style: {style_id}")
            
            # Используем grandlineai/instant-id-photorealistic
            output = replicate.run(
                "grandlineai/instant-id-photorealistic:b808e61d0bb13d0ef066e295f0bae72a2e87b57c64e4e9a00cf58c6a40bb893b",
                input={
                    "image": photo,
                    "prompt": f"professional photo, {style_info['prompt']}, high quality, detailed, 8k",
                    "negative_prompt": f"{style_info['negative']}, ugly, deformed, blurry",
                    "scheduler": "DPMSolverMultistep",
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                    "seed": -1,
                    "width": 1024,
                    "height": 1024,
                    "num_outputs": 2
                }
            )
            
            if output and len(output) > 0:
                # Отправляем результаты
                for i, img_url in enumerate(output[:2], 1):
                    caption = f"✨ Вариант {i} - {style_info['name']}" if i > 1 else f"✨ {style_info['name']}"
                    await update.callback_query.message.reply_photo(
                        photo=img_url,
                        caption=caption
                    )
                
                # Меню после генерации
                keyboard = [
                    [InlineKeyboardButton("🎨 Другой стиль", callback_data="another_style")],
                    [InlineKeyboardButton("📸 Новое фото", callback_data="new_photo")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ]
                
                user_data = self.db.get_or_create_user(update.effective_user.id)
                await update.callback_query.message.reply_text(
                    f"Готово! Осталось кредитов: {user_data['credits']}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info("Generation completed")
            else:
                raise Exception("No output from model")
                
        except Exception as e:
            logger.error(f"Generation error: {e}")
            await update.callback_query.message.reply_text(
                f"❌ Ошибка генерации. Кредиты возвращены.\n/start"
            )
            # Возвращаем кредиты при ошибке
            self.db.update_credits(update.effective_user.id, STYLES[style_id]['credits'])
        
        return MAIN_MENU
    
    async def _start_lora_training(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обучение LoRA через Flux"""
        try:
            photos_base64 = context.user_data.get('photos_base64', [])
            
            message = await update.callback_query.message.reply_text(
                "🔄 Обучение Flux LoRA модели...\n"
                "📊 Прогресс: 0%\n"
                "⏱ Время: ~15-20 минут"
            )
            
            # Запускаем обучение Flux LoRA
            training = replicate.trainings.create(
                version="ostris/flux-dev-lora-trainer:4ffd32160efd92e956d39c5338a9b8fbafca58e03f791f6d8011a3e17e1f6c70",
                input={
                    "input_images": photos_base64,
                    "trigger_word": "MYFACE",
                    "steps": 1200,
                    "lora_rank": 16,
                    "learning_rate": 0.0004,
                    "autocaption": True,
                    "autocaption_prefix": "MYFACE person photo"
                }
            )
            
            # Мониторинг обучения
            start_time = time.time()
            while training.status not in ["succeeded", "failed", "canceled"]:
                await asyncio.sleep(30)
                training.reload()
                
                elapsed = int((time.time() - start_time) / 60)
                progress = min(95, int((elapsed / 20) * 100))
                
                try:
                    await message.edit_text(
                        f"🔄 Обучение Flux LoRA...\n"
                        f"📊 Прогресс: ~{progress}%\n"
                        f"⏱ Прошло: {elapsed} мин"
                    )
                except:
                    pass
            
            if training.status == "succeeded":
                # Сохраняем модель
                self.db.save_lora_model(update.effective_user.id, training.output)
                context.user_data['lora_model'] = training.output
                
                # Показываем стили для генерации
                keyboard = []
                for style_id, style_info in list(STYLES.items())[:6]:
                    keyboard.append([InlineKeyboardButton(
                        f"{style_info['name']} (бесплатно с LoRA)",
                        callback_data=f"lora_style_{style_id}"
                    )])
                
                await message.edit_text(
                    "✅ **Модель обучена!**\n\n"
                    "Теперь вы можете генерировать в любых стилях бесплатно!\n"
                    "Выберите стиль:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                
                return SELECTING_STYLE
            else:
                raise Exception(f"Training failed: {training.status}")
                
        except Exception as e:
            logger.error(f"LoRA training error: {e}")
            await update.callback_query.message.reply_text(
                "❌ Ошибка обучения. Кредиты возвращены.\n/start"
            )
            self.db.update_credits(update.effective_user.id, 20)
            return ConversationHandler.END
    
    async def _generate_with_lora(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация с обученной Flux LoRA"""
        try:
            style_id = context.user_data['selected_style'].replace('lora_style_', '')
            style_info = STYLES[style_id]
            lora_model = context.user_data.get('lora_model')
            
            # Генерация через Flux с LoRA
            output = replicate.run(
                "black-forest-labs/flux-dev",
                input={
                    "prompt": f"MYFACE person, {style_info['prompt']}, masterpiece, best quality, professional",
                    "negative_prompt": style_info['negative'],
                    "lora": lora_model,
                    "lora_scale": 0.8,
                    "num_inference_steps": 35,
                    "guidance_scale": 7.5,
                    "width": 1024,
                    "height": 1024,
                    "num_outputs": 2
                }
            )
            
            if output:
                for i, img_url in enumerate(output[:2], 1):
                    await update.callback_query.message.reply_photo(
                        photo=img_url,
                        caption=f"✨ Pro генерация {i} - {style_info['name']}"
                    )
                
                keyboard = [
                    [InlineKeyboardButton("🎨 Еще стиль", callback_data="more_lora_styles")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ]
                
                await update.callback_query.message.reply_text(
                    "🎉 Ваша персональная модель работает отлично!\n"
                    "Генерируйте сколько угодно!",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
        except Exception as e:
            logger.error(f"LoRA generation error: {e}")
            await update.callback_query.message.reply_text("❌ Ошибка генерации")
        
        return MAIN_MENU
    
    async def buy_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Покупка кредитов"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("💵 10 кредитов - $5", callback_data="buy_10")],
            [InlineKeyboardButton("💵 25 кредитов - $10", callback_data="buy_25")],
            [InlineKeyboardButton("💵 60 кредитов - $20", callback_data="buy_60")],
            [InlineKeyboardButton("💵 150 кредитов - $40", callback_data="buy_150")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            "💳 **Покупка кредитов**\n\n"
            "Выберите пакет:\n\n"
            "• 10 кредитов = ~10 генераций\n"
            "• 25 кредитов = ~25 генераций\n"
            "• 60 кредитов = 2 LoRA модели\n"
            "• 150 кредитов = 5+ LoRA моделей\n\n"
            "Оплата в криптовалюте (USDT, BTC, ETH, TON)",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return PAYMENT_AMOUNT
    
    async def select_crypto(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор криптовалюты"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("buy_"):
            credits = int(query.data.replace("buy_", ""))
            context.user_data['buying_credits'] = credits
            context.user_data['payment_amount'] = self.crypto.prices[credits]
            
            keyboard = [
                [InlineKeyboardButton("💵 USDT (TRC20)", callback_data="crypto_USDT_TRC20")],
                [InlineKeyboardButton("💵 USDT (ERC20)", callback_data="crypto_USDT_ERC20")],
                [InlineKeyboardButton("₿ Bitcoin", callback_data="crypto_BTC")],
                [InlineKeyboardButton("💎 Ethereum", callback_data="crypto_ETH")],
                [InlineKeyboardButton("💠 TON", callback_data="crypto_TON")],
                [InlineKeyboardButton("🔙 Назад", callback_data="buy_credits")]
            ]
            
            await query.edit_message_text(
                f"💳 Покупка {credits} кредитов за ${context.user_data['payment_amount']}\n\n"
                "Выберите криптовалюту:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return PAYMENT_CRYPTO
    
    async def show_payment_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ деталей оплаты"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("crypto_"):
            crypto = query.data.replace("crypto_", "")
            credits = context.user_data['buying_credits']
            amount = context.user_data['payment_amount']
            
            payment_msg = self.crypto.generate_payment_message(crypto, amount, credits)
            
            keyboard = [
                [InlineKeyboardButton("✅ Я оплатил", callback_data="payment_done")],
                [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
            ]
            
            await query.edit_message_text(
                payment_msg,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            context.user_data['payment_crypto'] = crypto
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ панель"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        if user_id not in self.admin_ids:
            await query.answer("❌ Доступ запрещен", show_alert=True)
            return MAIN_MENU
        
        await query.answer()
        
        stats = self.db.get_stats()
        
        keyboard = [
            [InlineKeyboardButton("➕ Начислить кредиты", callback_data="admin_add_credits")],
            [InlineKeyboardButton("📊 Детальная статистика", callback_data="admin_detailed_stats")],
            [InlineKeyboardButton("💰 Транзакции", callback_data="admin_transactions")],
            [InlineKeyboardButton("📨 Рассылка", callback_data="admin_broadcast")],

    async def admin_functions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ функции"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        if user_id not in self.admin_ids:
            await query.answer("❌ Доступ запрещен", show_alert=True)
            return MAIN_MENU
        
        await query.answer()
        
        if query.data == "admin_add_credits":
            await query.edit_message_text(
                "➕ **Начисление кредитов**\n\n"
                "Отправьте сообщение в формате:\n"
                "`user_id количество`\n\n"
                "Например: `123456789 50`",
                parse_mode='Markdown'
            )
            context.user_data['admin_action'] = 'add_credits'
            return ADMIN_USER_SEARCH
            
        elif query.data == "admin_detailed_stats":
            cursor = self.db.conn.cursor()
            
            # Детальная статистика
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(*) as total_generations,
                    SUM(credits_used) as total_credits,
                    AVG(credits_used) as avg_credits
                FROM generations
                WHERE DATE(created_at) >= DATE('now', '-7 days')
            ''')
            week_stats = cursor.fetchone()
            
            cursor.execute('''
                SELECT style, COUNT(*) as count
                FROM generations
                GROUP BY style
                ORDER BY count DESC
                LIMIT 5
            ''')
            top_styles = cursor.fetchall()
            
            stats_text = f"""
📊 **Детальная статистика (7 дней)**

👥 Уникальных пользователей: {week_stats[0]}
🎨 Всего генераций: {week_stats[1]}
💰 Использовано кредитов: {week_stats[2] or 0}
📈 Среднее на генерацию: {week_stats[3] or 0:.1f}

**Популярные стили:**
"""
            for style, count in top_styles:
                style_name = STYLES.get(style, {}).get('name', style)
                stats_text += f"• {style_name}: {count} раз\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin")]]
            await query.edit_message_text(
                stats_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        elif query.data == "admin_transactions":
            cursor = self.db.conn.cursor()
            cursor.execute('''
                SELECT user_id, type, amount, credits, status, created_at
                FROM transactions
                ORDER BY created_at DESC
                LIMIT 10
            ''')
            transactions = cursor.fetchall()
            
            trans_text = "💰 **Последние транзакции:**\n\n"
            for t in transactions:
                trans_text += f"• User {t[0]}: {t[2]}$ за {t[3]} кредитов - {t[4]}\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin")]]
            await query.edit_message_text(
                trans_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        elif query.data == "admin_broadcast":
            await query.edit_message_text(
                "📨 **Рассылка**\n\n"
                "Отправьте текст сообщения для рассылки всем пользователям.\n"
                "Или /cancel для отмены",
                parse_mode='Markdown'
            )
            context.user_data['admin_action'] = 'broadcast'
            return ADMIN_USER_SEARCH

    async def handle_admin_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка админского ввода"""
        action = context.user_data.get('admin_action')
        
        if action == 'add_credits':
            try:
                parts = update.message.text.split()
                target_user_id = int(parts[0])
                credits = int(parts[1])
                
                self.db.update_credits(target_user_id, credits)
                
                await update.message.reply_text(
                    f"✅ Начислено {credits} кредитов пользователю {target_user_id}"
                )
                
                # Уведомляем пользователя
                try:
                    await context.bot.send_message(
                        target_user_id,
                        f"🎁 Вам начислено {credits} кредитов!"
                    )
                except:
                ,
                ADMIN_USER_SEARCH: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_admin_input),
                    CallbackQueryHandler(self.handle_navigation)
                ]
                    pass
                    
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
            
            context.user_data.clear()
            return MAIN_MENU
            
        elif action == 'broadcast':
            text = update.message.text
            
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT user_id FROM users')
            users = cursor.fetchall()
            
            sent = 0
            failed = 0
            
            msg = await update.message.reply_text("📨 Начинаю рассылку...")
            
            for user in users:
                try:
                    await context.bot.send_message(user[0], text)
                    sent += 1
                except:
                    failed += 1
                
                if (sent + failed) % 10 == 0:
                    await msg.edit_text(
                        f"📨 Рассылка...\n"
                        f"✅ Отправлено: {sent}\n"
                        f"❌ Ошибок: {failed}"
                    )
            
            await msg.edit_text(
                f"✅ Рассылка завершена!\n"
                f"Отправлено: {sent}\n"
                f"Не доставлено: {failed}"
            )
            
            context.user_data.clear()
            return MAIN_MENU
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
        ]
        
        stats_text = f"""
👨‍💼 **Админ панель**

📊 **Статистика:**
• Всего пользователей: {stats['total_users']}
• Активных сегодня: {stats['daily_active']}
• Генераций сегодня: {stats['daily_generations']}
• Общий доход: ${stats['total_revenue']:.2f}

🏆 **Топ пользователи:**
"""
        for user in stats['top_users'][:5]:
            stats_text += f"• @{user[1] or 'id'+str(user[0])} - {user[2]} генераций\n"
        
        await query.edit_message_text(
            stats_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return ADMIN_PANEL
    
    async def handle_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка навигации"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "main_menu":
            return await self.start(update, context)
        elif query.data == "back_to_menu":
            return await self.start(update, context)
        elif query.data == "another_style":
            # Возвращаемся к выбору стилей
            context.user_data['mode'] = 'instant'
            return await self.show_styles_menu(update, context)
        elif query.data == "new_photo":
            context.user_data['photos'] = []
            await query.edit_message_text("📸 Отправьте новое фото:")
            return UPLOADING_INSTANT
        elif query.data == "help":
            await self.help_command(update, context)
            return MAIN_MENU
        elif query.data == "balance":
            user_data = self.db.get_or_create_user(update.effective_user.id)
            await query.answer(f"💰 У вас {user_data['credits']} кредитов", show_alert=True)
            return MAIN_MENU
    
    async def show_styles_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ меню стилей"""
        keyboard = []
        row = []
        for i, (style_id, style_info) in enumerate(STYLES.items()):
            btn = InlineKeyboardButton(
                f"{style_info['name']} ({style_info['credits']}💰)",
                callback_data=f"style_{style_id}"
            )
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
        
        await update.callback_query.edit_message_text(
            "Выберите стиль генерации:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return SELECTING_STYLE
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        help_text = """
🤖 **AI Avatar Generator Bot**

**Режимы:**
⚡ Быстрый - 1 фото, 30 сек, 1 кредит
🎯 Pro (LoRA) - 5-10 фото, персональная модель, 20 кредитов

**Стили:**
20+ уникальных стилей от киберпанка до LinkedIn фото

**Кредиты:**
• Новым пользователям - 3 бесплатных
• Покупка от $5 за 10 кредитов
• Оплата в крипте (USDT, BTC, ETH, TON)

**Команды:**
/start - Главное меню
/help - Эта справка
/balance - Проверить баланс

**Поддержка:** @your_support_bot
        """
        
        if update.message:
            await update.message.reply_text(help_text, parse_mode='Markdown')
        else:
            await update.callback_query.message.reply_text(help_text, parse_mode='Markdown')
    
    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.telegram_token).build()
        
        # ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.start),
                CallbackQueryHandler(self.start, pattern="^main_menu$")
            ],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(self.mode_selection, pattern="^mode_"),
                    CallbackQueryHandler(self.buy_credits, pattern="^buy_credits$"),
                    CallbackQueryHandler(self.admin_panel, pattern="^admin$"),
                    CallbackQueryHandler(self.handle_navigation)
                ],
                UPLOADING_INSTANT: [
                    MessageHandler(filters.PHOTO, self.handle_instant_photo),
                    CallbackQueryHandler(self.handle_navigation)
                ],
                UPLOADING_LORA: [
                    MessageHandler(filters.PHOTO, self.handle_lora_photos),
                    CallbackQueryHandler(self.handle_lora_decision, pattern="^lora_"),
                    CallbackQueryHandler(self.handle_navigation)
                ],
                SELECTING_STYLE: [
                    CallbackQueryHandler(self.handle_style_selection),
                    CallbackQueryHandler(self.handle_navigation)
                ],
                PAYMENT_AMOUNT: [
                    CallbackQueryHandler(self.select_crypto),
                    CallbackQueryHandler(self.handle_navigation)
                ],
                PAYMENT_CRYPTO: [
                    CallbackQueryHandler(self.show_payment_details),
                    CallbackQueryHandler(self.handle_navigation)
                ],
                ADMIN_PANEL: [
                    CallbackQueryHandler(self.admin_functions),
                    CallbackQueryHandler(self.handle_navigation)
                ]
            },
            fallbacks=[
                CommandHandler("start", self.start),
                CallbackQueryHandler(self.start, pattern="^main_menu$")
            ],
            per_message=False
        )
        
        # Добавляем обработчики
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("help", self.help_command))
        
        # Команда баланса
        async def balance_cmd(update, context):
            user_data = self.db.get_or_create_user(update.effective_user.id)
            await update.message.reply_text(f"💰 Ваш баланс: {user_data['credits']} кредитов")
        application.add_handler(CommandHandler("balance", balance_cmd))
        
        # Запуск
        logger.info("🤖 Production Avatar Bot started!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

# Запуск
if __name__ == "__main__":
    load_dotenv()
    
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    
    if not TELEGRAM_BOT_TOKEN or not REPLICATE_API_TOKEN:
        logger.error("Missing tokens!")
        exit(1)
    
    bot = AvatarBot(TELEGRAM_BOT_TOKEN, REPLICATE_API_TOKEN, ADMIN_IDS)
    bot.run()
