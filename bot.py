import os
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
import json
import aiohttp
from io import BytesIO

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

# Replicate import
import replicate

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(
    CHOOSING_MODE,
    UPLOADING_INSTANT,
    UPLOADING_LORA,
    SELECTING_STYLE,
    GENERATING
) = range(5)

# Стили для генерации
STYLES = {
    "cyberpunk": {
        "name": "🤖 Киберпанк",
        "prompt": "cyberpunk style, neon lights, futuristic, tech wear, holographic effects",
        "negative": "boring, plain, old-fashioned"
    },
    "anime": {
        "name": "🎌 Аниме",
        "prompt": "anime style, manga art, cel shading, vibrant colors, large expressive eyes",
        "negative": "realistic, photographic, western cartoon"
    },
    "fantasy": {
        "name": "🧙 Фэнтези",
        "prompt": "fantasy art, magical, ethereal, mystical lighting, epic character",
        "negative": "modern, mundane, ordinary"
    },
    "superhero": {
        "name": "🦸 Супергерой",
        "prompt": "superhero style, dynamic pose, dramatic lighting, powerful, comic book art",
        "negative": "weak, ordinary, civilian clothes"
    },
    "portrait": {
        "name": "🎨 Арт-портрет",
        "prompt": "artistic portrait, professional lighting, high quality, masterpiece",
        "negative": "amateur, low quality, blurry"
    }
}

class AvatarBot:
    def __init__(self, telegram_token: str, replicate_token: str):
        # Очищаем токены от невидимых символов
        self.telegram_token = telegram_token.strip()
        replicate_token = replicate_token.strip()
        os.environ["REPLICATE_API_TOKEN"] = replicate_token
        self.user_data: Dict = {}
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало работы с ботом"""
        user = update.effective_user
        
        keyboard = [
            [InlineKeyboardButton("⚡ Быстрая генерация (Instant ID)", callback_data="mode_instant")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"Привет, {user.first_name}! 👋\n\n"
            "Я помогу создать крутые аватарки с твоим лицом! 🎨\n\n"
            "⚡ **Быстрый режим** - загрузи 1 фото и получи результат за минуту\n\n"
            "Выбери режим:"
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        return CHOOSING_MODE
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда помощи"""
        help_text = (
            "🤖 **Как пользоваться ботом:**\n\n"
            "1️⃣ Нажмите кнопку 'Быстрая генерация'\n"
            "2️⃣ Загрузите четкое фото лица\n"
            "3️⃣ Выберите стиль генерации\n"
            "4️⃣ Получите результат!\n\n"
            "💡 **Советы:**\n"
            "• Используйте качественные фото\n"
            "• Лицо должно быть четко видно\n\n"
            "/start - начать заново\n"
            "/help - эта справка"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора режима"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            help_text = (
                "ℹ️ **О режиме:**\n\n"
                "**Быстрый режим:**\n"
                "• Нужно только 1 фото\n"
                "• Генерация за 30-60 секунд\n"
                "• Хорошо для быстрых аватарок"
            )
            await query.edit_message_text(help_text, parse_mode='Markdown')
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]]
            await query.message.reply_text(
                "Выберите действие:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return CHOOSING_MODE
            
        elif query.data == "back_to_start":
            keyboard = [
                [InlineKeyboardButton("⚡ Быстрая генерация (Instant ID)", callback_data="mode_instant")],
                [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
            ]
            await query.edit_message_text(
                "Выберите режим:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return CHOOSING_MODE
            
        elif query.data == "mode_instant":
            context.user_data['mode'] = 'instant'
            context.user_data['photos'] = []
            
            await query.edit_message_text(
                "⚡ **Быстрый режим**\n\n"
                "Отправьте мне одно четкое фото вашего лица.\n"
                "Требования:\n"
                "• Фронтальный ракурс\n"
                "• Хорошее освещение\n"
                "• Четкое изображение лица",
                parse_mode='Markdown'
            )
            return UPLOADING_INSTANT
    
    async def handle_instant_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка фото для Instant ID"""
        try:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            
            # Сохраняем фото
            photo_bytes = BytesIO()
            await file.download_to_memory(photo_bytes)
            photo_bytes.seek(0)
            
            context.user_data['photos'] = [photo_bytes]
            
            await update.message.reply_text(
                "✅ Фото получено! Теперь выберите стиль генерации:",
                reply_markup=self._get_styles_keyboard()
            )
            
            return SELECTING_STYLE
        except Exception as e:
            logger.error(f"Error handling photo: {e}")
            await update.message.reply_text(
                "❌ Ошибка при обработке фото. Попробуйте еще раз.\n/start"
            )
            return ConversationHandler.END
    
    def _get_styles_keyboard(self):
        """Создание клавиатуры со стилями"""
        keyboard = []
        for style_id, style_info in STYLES.items():
            keyboard.append([InlineKeyboardButton(
                style_info['name'],
                callback_data=f"style_{style_id}"
            )])
        return InlineKeyboardMarkup(keyboard)
    
    async def handle_style_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора стиля"""
        query = update.callback_query
        await query.answer()
        
        style_id = query.data.replace("style_", "")
        context.user_data['selected_style'] = style_id
        style_info = STYLES[style_id]
        
        await query.edit_message_text(
            f"Выбран стиль: {style_info['name']}\n\n"
            "🎨 Начинаю генерацию...\n"
            "⏳ Подождите 30-60 секунд..."
        )
        
        # Запускаем генерацию
        return await self._generate_instant_id(update, context)
    
    async def _generate_instant_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация через Instant ID"""
        try:
            style_id = context.user_data['selected_style']
            style_info = STYLES[style_id]
            photo = context.user_data['photos'][0]
            
            # Сброс позиции в BytesIO
            photo.seek(0)
            
            logger.info(f"Starting generation for style: {style_id}")
            
            # Используем более простую модель для теста
            # photomaker работает быстрее и стабильнее для начала
            output = replicate.run(
                "tencentarc/photomaker:ddfc2b08d209f9fa8c1eca692712918bd449f695dabb4a958da31802a9570fe4",
                input={
                    "prompt": f"person, {style_info['prompt']}, high quality portrait",
                    "num_steps": 20,
                    "style_name": "Photographic",
                    "input_image": photo,
                    "guidance_scale": 5,
                    "negative_prompt": style_info['negative']
                }
            )
            
            # Отправляем результат
            if output and len(output) > 0:
                result_url = output[0] if isinstance(output, list) else output
                
                await update.callback_query.message.reply_photo(
                    photo=result_url,
                    caption=f"✨ Ваш аватар в стиле {style_info['name']} готов!\n\n"
                           f"Хотите попробовать другой стиль? Используйте /start"
                )
                
                logger.info("Generation completed successfully")
            else:
                raise Exception("No output from model")
            
        except Exception as e:
            logger.error(f"Error in Instant ID generation: {e}")
            error_message = str(e)
            
            # Более информативное сообщение об ошибке
            if "billing" in error_message.lower():
                error_text = "❌ Ошибка: Проверьте баланс на Replicate"
            elif "api" in error_message.lower():
                error_text = "❌ Ошибка: Проблема с API токеном Replicate"
            else:
                error_text = f"❌ Ошибка генерации: {error_message[:100]}"
            
            await update.callback_query.message.reply_text(
                f"{error_text}\n\nИспользуйте /start для новой попытки."
            )
        
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущей операции"""
        await update.message.reply_text(
            "Операция отменена. Используйте /start чтобы начать заново."
        )
        return ConversationHandler.END
    
    def run(self):
        """Запуск бота"""
        try:
            # Создаем приложение с очищенным токеном
            application = Application.builder().token(self.telegram_token).build()
            
            # Создаем ConversationHandler с per_message=True чтобы избежать предупреждения
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("start", self.start)],
                states={
                    CHOOSING_MODE: [
                        CallbackQueryHandler(self.mode_selection)
                    ],
                    UPLOADING_INSTANT: [
                        MessageHandler(filters.PHOTO, self.handle_instant_photo)
                    ],
                    SELECTING_STYLE: [
                        CallbackQueryHandler(self.handle_style_selection)
                    ]
                },
                fallbacks=[CommandHandler("cancel", self.cancel)],
                per_message=True  # Исправляем предупреждение
            )
            
            # Добавляем обработчики
            application.add_handler(conv_handler)
            application.add_handler(CommandHandler("help", self.help_command))
            
            # Запускаем бота
            logger.info("Starting bot polling...")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise

# Конфигурация
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Получаем токены и очищаем их от лишних символов
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()
    
    # Дополнительная очистка от невидимых символов
    TELEGRAM_BOT_TOKEN = ''.join(c for c in TELEGRAM_BOT_TOKEN if c.isprintable())
    REPLICATE_API_TOKEN = ''.join(c for c in REPLICATE_API_TOKEN if c.isprintable())
    
    # Проверка токенов
    if not TELEGRAM_BOT_TOKEN or not REPLICATE_API_TOKEN:
        logger.error("❌ Ошибка: Не установлены токены!")
        logger.error("Установите TELEGRAM_BOT_TOKEN и REPLICATE_API_TOKEN в переменных окружения")
        sys.exit(1)
    
    # Валидация формата токена Telegram (должен быть вида: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11)
    if ':' not in TELEGRAM_BOT_TOKEN:
        logger.error("❌ Неверный формат TELEGRAM_BOT_TOKEN!")
        logger.error("Токен должен содержать ':' (например: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)")
        sys.exit(1)
    
    # Создаем и запускаем бота
    try:
        bot = AvatarBot(TELEGRAM_BOT_TOKEN, REPLICATE_API_TOKEN)
        
        logger.info("🤖 Бот запущен на Railway!")
        logger.info(f"✅ Telegram Token: ...{TELEGRAM_BOT_TOKEN[-10:]}")
        logger.info(f"✅ Replicate Token: ...{REPLICATE_API_TOKEN[-10:]}")
        
        bot.run()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
