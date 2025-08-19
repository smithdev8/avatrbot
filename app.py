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
    },
    "pixar": {
        "name": "🎬 Pixar стиль",
        "prompt": "3D pixar style, cute, rounded features, colorful, animated character",
        "negative": "realistic, dark, horror"
    },
    "viking": {
        "name": "⚔️ Викинг",
        "prompt": "viking warrior, norse mythology, epic beard, battle armor, fierce",
        "negative": "modern, weak, clean-shaven"
    },
    "steampunk": {
        "name": "⚙️ Стимпанк",
        "prompt": "steampunk style, victorian era, brass goggles, mechanical gears, vintage",
        "negative": "modern, digital, minimalist"
    }
}

class AvatarBot:
    def __init__(self, telegram_token: str, replicate_token: str):
        self.telegram_token = telegram_token
        os.environ["REPLICATE_API_TOKEN"] = replicate_token
        self.user_data: Dict = {}
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало работы с ботом"""
        user = update.effective_user
        
        keyboard = [
            [InlineKeyboardButton("⚡ Быстрая генерация (Instant ID)", callback_data="mode_instant")],
            [InlineKeyboardButton("🎯 Pro режим (LoRA Training)", callback_data="mode_lora")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"Привет, {user.first_name}! 👋\n\n"
            "Я помогу создать крутые аватарки с твоим лицом! 🎨\n\n"
            "У меня есть два режима:\n"
            "⚡ **Быстрый** - загрузи 1 фото и получи результат за минуту\n"
            "🎯 **Pro** - загрузи 5-10 селфи для обучения персональной модели (15-20 минут)\n\n"
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
            "1️⃣ Выберите режим генерации:\n"
            "   • Быстрый (Instant ID) - для одного фото\n"
            "   • Pro (LoRA) - для точной персонализации\n\n"
            "2️⃣ Загрузите фото:\n"
            "   • Для быстрого режима - 1 четкое селфи\n"
            "   • Для Pro режима - 5-10 разных селфи\n\n"
            "3️⃣ Выберите стиль генерации\n\n"
            "4️⃣ Получите результат!\n\n"
            "💡 **Советы:**\n"
            "• Используйте качественные фото с хорошим освещением\n"
            "• Лицо должно быть четко видно\n"
            "• Для Pro режима используйте фото с разных ракурсов\n\n"
            "/start - начать заново\n"
            "/help - эта справка\n"
            "/styles - посмотреть все стили"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора режима"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            help_text = (
                "ℹ️ **О режимах:**\n\n"
                "**Быстрый режим (Instant ID):**\n"
                "• Нужно только 1 фото\n"
                "• Генерация за 30-60 секунд\n"
                "• Хорошо для быстрых аватарок\n\n"
                "**Pro режим (LoRA):**\n"
                "• Нужно 5-10 фото\n"
                "• Обучение модели 15-20 минут\n"
                "• Максимальное сходство\n"
                "• Лучшее качество\n"
                "• Можно генерировать много раз"
            )
            await query.edit_message_text(help_text, parse_mode='Markdown')
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]]
            await query.message.reply_text(
                "Выберите действие:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return CHOOSING_MODE
            
        elif query.data == "back_to_start":
            return await self.start(update, context)
            
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
            
        elif query.data == "mode_lora":
            context.user_data['mode'] = 'lora'
            context.user_data['photos'] = []
            context.user_data['photo_count'] = 0
            
            await query.edit_message_text(
                "🎯 **Pro режим (LoRA Training)**\n\n"
                "Отправьте мне 5-10 фотографий для обучения.\n"
                "Требования:\n"
                "• Разные ракурсы и выражения\n"
                "• Четкие фото лица\n"
                "• Разное освещение приветствуется\n\n"
                "Отправлено: 0/10",
                parse_mode='Markdown'
            )
            return UPLOADING_LORA
    
    async def handle_instant_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка фото для Instant ID"""
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
    
    async def handle_lora_photos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка фото для LoRA"""
        photo = update.message.photo[-1]
        file = await photo.get_file()
        
        # Сохраняем фото
        photo_bytes = BytesIO()
        await file.download_to_memory(photo_bytes)
        photo_bytes.seek(0)
        
        context.user_data['photos'].append(photo_bytes)
        context.user_data['photo_count'] = len(context.user_data['photos'])
        
        count = context.user_data['photo_count']
        
        if count < 5:
            await update.message.reply_text(
                f"Получено фото: {count}/10\n"
                f"Минимум нужно еще {5 - count} фото."
            )
            return UPLOADING_LORA
        elif count < 10:
            keyboard = [
                [InlineKeyboardButton(f"✅ Достаточно ({count} фото)", callback_data="lora_ready")],
                [InlineKeyboardButton("➕ Добавить еще", callback_data="lora_more")]
            ]
            await update.message.reply_text(
                f"Получено {count} фото.\n"
                "Можете добавить еще или начать обучение:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return UPLOADING_LORA
        else:
            await update.message.reply_text(
                "✅ Получено максимум фото (10)! Начинаем обучение...\n"
                "⏳ Это займет 15-20 минут."
            )
            # Здесь начнется обучение LoRA
            return await self._start_lora_training(update, context)
    
    async def handle_lora_decision(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка решения о количестве фото для LoRA"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "lora_ready":
            await query.edit_message_text(
                "🚀 Начинаем обучение модели...\n"
                "⏳ Это займет 15-20 минут.\n"
                "☕ Можете пока выпить кофе!"
            )
            return await self._start_lora_training(update, context)
        elif query.data == "lora_more":
            count = context.user_data['photo_count']
            await query.edit_message_text(
                f"Отправьте еще фото (сейчас {count}/10):"
            )
            return UPLOADING_LORA
    
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
        if context.user_data['mode'] == 'instant':
            return await self._generate_instant_id(update, context)
        else:
            return await self._generate_with_lora(update, context)
    
    async def _generate_instant_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация через Instant ID"""
        try:
            style_id = context.user_data['selected_style']
            style_info = STYLES[style_id]
            photo = context.user_data['photos'][0]
            
            # Используем InstantID модель на Replicate
            output = replicate.run(
                "zsxkib/instant-id:083c93de8c45af26c3d598bba35d2b6d4c64fff10cb3e23b33ec01ba1bc088ef",
                input={
                    "image": photo,
                    "prompt": f"{style_info['prompt']}, professional avatar, high quality, detailed",
                    "negative_prompt": f"{style_info['negative']}, ugly, deformed, blurry",
                    "guidance_scale": 7.5,
                    "num_inference_steps": 30,
                    "seed": -1
                }
            )
            
            # Отправляем результат
            if output:
                await update.callback_query.message.reply_photo(
                    photo=output[0],
                    caption=f"✨ Ваш аватар в стиле {style_info['name']} готов!\n\n"
                           f"Хотите попробовать другой стиль? Используйте /start"
                )
            
            # Предлагаем еще стили
            keyboard = [
                [InlineKeyboardButton("🎨 Другой стиль", callback_data="more_styles")],
                [InlineKeyboardButton("🔄 Новое фото", callback_data="new_photo")],
                [InlineKeyboardButton("🏠 В начало", callback_data="restart")]
            ]
            
            await update.callback_query.message.reply_text(
                "Что дальше?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Error in Instant ID generation: {e}")
            await update.callback_query.message.reply_text(
                "❌ Произошла ошибка при генерации. Попробуйте еще раз.\n"
                "Используйте /start для начала."
            )
        
        return ConversationHandler.END
    
    async def _start_lora_training(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запуск обучения LoRA"""
        try:
            photos = context.user_data['photos']
            
            # Создаем zip архив с фотографиями для обучения
            # В реальном коде здесь нужно создать zip-файл
            
            message = await update.callback_query.message.reply_text(
                "🔄 Обучение модели началось...\n"
                "Прогресс: 0%"
            )
            
            # Запускаем обучение LoRA на Replicate
            training = replicate.trainings.create(
                version="ostris/flux-dev-lora-trainer:4ffd32160efd92e956d39c5338a9b8fbafca58e03f791f6d8011a3e17e1f6c70",
                input={
                    "input_images": photos,  # Здесь должен быть URL к zip-архиву
                    "trigger_word": "TOK",
                    "steps": 1000,
                    "learning_rate": 0.0004,
                }
            )
            
            # Ждем завершения обучения
            while training.status != "succeeded":
                await asyncio.sleep(30)
                training.reload()
                
                # Обновляем прогресс
                if hasattr(training, 'logs'):
                    # Парсим прогресс из логов
                    progress = self._parse_progress(training.logs)
                    await message.edit_text(
                        f"🔄 Обучение модели...\n"
                        f"Прогресс: {progress}%"
                    )
            
            # Сохраняем URL обученной модели
            context.user_data['lora_model'] = training.output
            
            await message.edit_text(
                "✅ Модель обучена! Теперь выберите стиль для генерации:",
                reply_markup=self._get_styles_keyboard()
            )
            
            return SELECTING_STYLE
            
        except Exception as e:
            logger.error(f"Error in LoRA training: {e}")
            await update.callback_query.message.reply_text(
                "❌ Ошибка при обучении модели. Попробуйте позже.\n"
                "Используйте /start для начала."
            )
            return ConversationHandler.END
    
    async def _generate_with_lora(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация с обученной LoRA моделью"""
        try:
            style_id = context.user_data['selected_style']
            style_info = STYLES[style_id]
            lora_model = context.user_data.get('lora_model')
            
            # Генерация с использованием обученной LoRA
            output = replicate.run(
                lora_model,
                input={
                    "prompt": f"TOK person, {style_info['prompt']}, masterpiece",
                    "negative_prompt": style_info['negative'],
                    "num_inference_steps": 50,
                    "guidance_scale": 7.5,
                    "width": 1024,
                    "height": 1024,
                    "num_outputs": 2
                }
            )
            
            # Отправляем результаты
            media_group = []
            for img_url in output[:2]:
                media_group.append(InputMediaPhoto(img_url))
            
            await update.callback_query.message.reply_media_group(media_group)
            await update.callback_query.message.reply_text(
                f"✨ Ваши аватары в стиле {style_info['name']} готовы!\n"
                f"Модель обучена специально под вас и может генерировать неограниченно.\n\n"
                f"Попробуйте другие стили или используйте /start для нового сеанса."
            )
            
            # Предлагаем еще опции
            keyboard = [
                [InlineKeyboardButton("🎨 Другой стиль", callback_data="more_styles_lora")],
                [InlineKeyboardButton("🏠 В начало", callback_data="restart")]
            ]
            
            await update.callback_query.message.reply_text(
                "Хотите еще?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Error in LoRA generation: {e}")
            await update.callback_query.message.reply_text(
                "❌ Ошибка при генерации. Попробуйте еще раз."
            )
        
        return ConversationHandler.END
    
    def _parse_progress(self, logs: str) -> int:
        """Парсинг прогресса из логов обучения"""
        # Простой парсер прогресса
        if "step" in logs:
            lines = logs.split('\n')
            for line in reversed(lines):
                if "step" in line:
                    try:
                        # Ищем паттерн вида "step 500/1000"
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "step" and i + 1 < len(parts):
                                step_info = parts[i + 1]
                                if "/" in step_info:
                                    current, total = step_info.split("/")
                                    return int((int(current) / int(total)) * 100)
                    except:
                        pass
        return 0
    
    async def show_styles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все доступные стили"""
        styles_text = "🎨 **Доступные стили:**\n\n"
        for style_id, style_info in STYLES.items():
            styles_text += f"{style_info['name']}\n"
        
        styles_text += "\nИспользуйте /start чтобы начать генерацию!"
        
        await update.message.reply_text(styles_text, parse_mode='Markdown')
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущей операции"""
        await update.message.reply_text(
            "Операция отменена. Используйте /start чтобы начать заново."
        )
        return ConversationHandler.END
    
    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.telegram_token).build()
        
        # Создаем ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                CHOOSING_MODE: [
                    CallbackQueryHandler(self.mode_selection)
                ],
                UPLOADING_INSTANT: [
                    MessageHandler(filters.PHOTO, self.handle_instant_photo)
                ],
                UPLOADING_LORA: [
                    MessageHandler(filters.PHOTO, self.handle_lora_photos),
                    CallbackQueryHandler(self.handle_lora_decision)
                ],
                SELECTING_STYLE: [
                    CallbackQueryHandler(self.handle_style_selection)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        
        # Добавляем обработчики
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("styles", self.show_styles))
        
        # Запускаем бота
        application.run_polling()

# Конфигурация
if __name__ == "__main__":
    # Вставьте свои токены
    TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
    REPLICATE_API_TOKEN = "YOUR_REPLICATE_API_TOKEN"
    
    # Создаем и запускаем бота
    bot = AvatarBot(TELEGRAM_BOT_TOKEN, REPLICATE_API_TOKEN)
    
    print("🤖 Бот запущен!")
    bot.run()
