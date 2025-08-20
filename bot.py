import os
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
import json
import time
from io import BytesIO
import base64

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
from replicate.exceptions import ReplicateError

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
    GENERATING,
    WAITING_LORA
) = range(6)

# Стили для генерации
STYLES = {
    "cyberpunk": {
        "name": "🤖 Киберпанк",
        "prompt": "cyberpunk style, neon lights, futuristic city, tech wear, holographic",
        "negative": "boring, plain, old-fashioned",
        "photomaker_style": "Neonpunk"
    },
    "anime": {
        "name": "🎌 Аниме",
        "prompt": "anime style, manga art, vibrant colors, expressive",
        "negative": "realistic, photographic",
        "photomaker_style": "Comic book"
    },
    "fantasy": {
        "name": "🧙 Фэнтези",
        "prompt": "fantasy art, magical, ethereal, mystical lighting",
        "negative": "modern, mundane",
        "photomaker_style": "Fantasy art"
    },
    "superhero": {
        "name": "🦸 Супергерой",
        "prompt": "superhero style, dynamic pose, dramatic lighting, powerful",
        "negative": "weak, ordinary",
        "photomaker_style": "Cinematic"
    },
    "portrait": {
        "name": "🎨 Арт-портрет",
        "prompt": "artistic portrait, professional lighting, masterpiece",
        "negative": "amateur, low quality",
        "photomaker_style": "Photographic (Default)"
    },
    "disney": {
        "name": "🏰 Disney/Pixar",
        "prompt": "disney pixar style, 3d animated character, colorful",
        "negative": "realistic, dark",
        "photomaker_style": "Disney Charactor"
    },
    "digital": {
        "name": "💻 Digital Art",
        "prompt": "digital art style, modern illustration, vibrant",
        "negative": "traditional, sketch",
        "photomaker_style": "Digital Art"
    },
    "neon": {
        "name": "💜 Неон",
        "prompt": "neon colors, glowing effects, night city, synthwave",
        "negative": "dull, muted colors",
        "photomaker_style": "Neonpunk"
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
        
        # Сброс данных пользователя
        context.user_data.clear()
        
        keyboard = [
            [InlineKeyboardButton("⚡ Быстрая генерация (30 сек)", callback_data="mode_instant")],
            [InlineKeyboardButton("🎯 Pro режим LoRA (20 мин)", callback_data="mode_lora")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"Привет, {user.first_name}! 👋\n\n"
            "🎨 Я создам крутые аватарки с твоим лицом!\n\n"
            "У меня есть два режима:\n\n"
            "⚡ **Быстрый** - 1 фото, результат за 30 секунд\n"
            "🎯 **Pro (LoRA)** - 5-10 фото для персональной модели\n\n"
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
            "   • Быстрый - для одного фото\n"
            "   • Pro (LoRA) - для точной персонализации\n\n"
            "2️⃣ Загрузите фото:\n"
            "   • Для быстрого - 1 четкое селфи\n"
            "   • Для Pro - 5-10 разных селфи\n\n"
            "3️⃣ Выберите стиль (8 вариантов)\n\n"
            "4️⃣ Получите результат!\n\n"
            "💡 **Советы:**\n"
            "• Качественные фото = лучший результат\n"
            "• Лицо должно быть четко видно\n"
            "• Для Pro используйте разные ракурсы\n\n"
            "/start - начать заново\n"
            "/help - эта справка\n"
            "/styles - все стили"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора режима"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            help_text = (
                "ℹ️ **Сравнение режимов:**\n\n"
                "**⚡ Быстрый режим:**\n"
                "• 1 фото\n"
                "• 30 секунд генерации\n"
                "• Хорошее качество\n"
                "• ~$0.01 за генерацию\n\n"
                "**🎯 Pro режим (LoRA):**\n"
                "• 5-10 фото для обучения\n"
                "• 15-20 минут обучения\n"
                "• Максимальное сходство\n"
                "• Можно генерировать много раз\n"
                "• ~$1-2 за обучение"
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
                [InlineKeyboardButton("⚡ Быстрая генерация (30 сек)", callback_data="mode_instant")],
                [InlineKeyboardButton("🎯 Pro режим LoRA (20 мин)", callback_data="mode_lora")],
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
                "📸 Отправьте одно четкое фото лица:\n\n"
                "Требования:\n"
                "• Фронтальный ракурс лучше\n"
                "• Хорошее освещение\n"
                "• Четкое лицо без обрезки",
                parse_mode='Markdown'
            )
            return UPLOADING_INSTANT
            
        elif query.data == "mode_lora":
            context.user_data['mode'] = 'lora'
            context.user_data['photos'] = []
            context.user_data['photo_count'] = 0
            
            await query.edit_message_text(
                "🎯 **Pro режим (LoRA Training)**\n\n"
                "📸 Отправьте 5-10 фотографий для обучения:\n\n"
                "Требования:\n"
                "• Разные ракурсы\n"
                "• Разные выражения лица\n"
                "• Четкие фото\n\n"
                "Отправлено: 0/10",
                parse_mode='Markdown'
            )
            return UPLOADING_LORA
    
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
                "✅ Фото получено! Теперь выберите стиль:",
                reply_markup=self._get_styles_keyboard()
            )
            
            return SELECTING_STYLE
            
        except Exception as e:
            logger.error(f"Error handling photo: {e}")
            await update.message.reply_text(
                "❌ Ошибка при обработке фото. Попробуйте еще раз.\n/start"
            )
            return ConversationHandler.END
    
    async def handle_lora_photos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка фото для LoRA"""
        try:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            
            # Сохраняем фото
            photo_bytes = BytesIO()
            await file.download_to_memory(photo_bytes)
            photo_bytes.seek(0)
            
            # Конвертируем в base64 для LoRA
            photo_base64 = base64.b64encode(photo_bytes.read()).decode('utf-8')
            photo_bytes.seek(0)
            
            if 'photos' not in context.user_data:
                context.user_data['photos'] = []
            if 'photos_base64' not in context.user_data:
                context.user_data['photos_base64'] = []
                
            context.user_data['photos'].append(photo_bytes)
            context.user_data['photos_base64'].append(f"data:image/jpeg;base64,{photo_base64}")
            context.user_data['photo_count'] = len(context.user_data['photos'])
            
            count = context.user_data['photo_count']
            
            if count < 5:
                await update.message.reply_text(
                    f"📸 Получено фото: {count}/10\n"
                    f"Минимум нужно еще {5 - count} фото."
                )
                return UPLOADING_LORA
            elif count < 10:
                keyboard = [
                    [InlineKeyboardButton(f"✅ Начать обучение ({count} фото)", callback_data="lora_ready")],
                    [InlineKeyboardButton("➕ Добавить еще", callback_data="lora_more")]
                ]
                await update.message.reply_text(
                    f"📸 Получено {count} фото.\n"
                    "Можете добавить еще или начать обучение:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return UPLOADING_LORA
            else:
                await update.message.reply_text(
                    "✅ Получено 10 фото! Начинаем обучение...\n"
                    "⏳ Это займет 15-20 минут."
                )
                return await self._start_lora_training(update, context)
                
        except Exception as e:
            logger.error(f"Error handling LoRA photos: {e}")
            await update.message.reply_text(
                "❌ Ошибка при загрузке фото. Попробуйте еще раз."
            )
            return UPLOADING_LORA
    
    async def handle_lora_decision(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка решения о количестве фото для LoRA"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "lora_ready":
            await query.edit_message_text(
                "🚀 Начинаем обучение модели...\n"
                "⏳ Это займет 15-20 минут.\n"
                "☕ Можете пока выпить кофе!\n\n"
                "Я отправлю уведомление когда будет готово."
            )
            return await self._start_lora_training(update, context)
        elif query.data == "lora_more":
            count = context.user_data.get('photo_count', 0)
            await query.edit_message_text(
                f"📸 Отправьте еще фото (сейчас {count}/10):"
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
        if context.user_data.get('mode') == 'instant':
            return await self._generate_instant_id(update, context)
        else:
            return await self._generate_with_lora(update, context)
    
    async def _generate_instant_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация через Instant ID (PhotoMaker)"""
        try:
            style_id = context.user_data['selected_style']
            style_info = STYLES[style_id]
            photo = context.user_data['photos'][0]
            
            # Сброс позиции в BytesIO
            photo.seek(0)
            
            logger.info(f"Starting generation for style: {style_id}")
            
            # Используем PhotoMaker для быстрой генерации
            output = replicate.run(
                "tencentarc/photomaker:ddfc2b08d209f9fa8c1eca692712918bd449f695dabb4a958da31802a9570fe4",
                input={
                    "prompt": f"img, {style_info['prompt']}, high quality, 8k, detailed",
                    "num_steps": 25,
                    "style_name": style_info['photomaker_style'],
                    "input_image": photo,
                    "num_outputs": 2,
                    "guidance_scale": 5,
                    "negative_prompt": f"{style_info['negative']}, ugly, deformed, blurry, low quality"
                }
            )
            
            # Отправляем результаты
            if output and len(output) > 0:
                # Отправляем первое изображение
                await update.callback_query.message.reply_photo(
                    photo=output[0],
                    caption=f"✨ Ваш аватар в стиле {style_info['name']} готов!"
                )
                
                # Если есть второе изображение
                if len(output) > 1:
                    await update.callback_query.message.reply_photo(
                        photo=output[1],
                        caption="🎨 Вот еще один вариант!"
                    )
                
                # Предлагаем еще опции
                keyboard = [
                    [InlineKeyboardButton("🎨 Другой стиль", callback_data="more_styles")],
                    [InlineKeyboardButton("📸 Новое фото", callback_data="new_photo")],
                    [InlineKeyboardButton("🏠 В начало", callback_data="restart")]
                ]
                
                await update.callback_query.message.reply_text(
                    "Что дальше?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info("Generation completed successfully")
            else:
                raise Exception("No output from model")
            
        except Exception as e:
            logger.error(f"Error in generation: {e}")
            error_text = self._get_error_message(e)
            
            await update.callback_query.message.reply_text(
                f"{error_text}\n\nИспользуйте /start для новой попытки."
            )
        
        return ConversationHandler.END
    
    async def _start_lora_training(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запуск обучения LoRA"""
        try:
            photos_base64 = context.user_data.get('photos_base64', [])
            
            if not photos_base64:
                raise Exception("No photos for training")
            
            message = await update.callback_query.message.reply_text(
                "🔄 Обучение модели началось...\n"
                "📊 Прогресс: 0%\n\n"
                "⏱ Примерное время: 15-20 минут"
            )
            
            context.user_data['progress_message'] = message
            
            logger.info(f"Starting LoRA training with {len(photos_base64)} photos")
            
            # Запускаем обучение LoRA
            training = replicate.trainings.create(
                version="ostris/flux-dev-lora-trainer:4ffd32160efd92e956d39c5338a9b8fbafca58e03f791f6d8011a3e17e1f6c70",
                input={
                    "input_images": photos_base64,
                    "trigger_word": "OHWX",
                    "steps": 1000,
                    "lora_rank": 16,
                    "learning_rate": 0.0004,
                    "caption_dropout_rate": 0.05,
                    "optimizer": "adamw8bit",
                    "autocaption": True,
                    "autocaption_prefix": "OHWX person"
                }
            )
            
            context.user_data['training_id'] = training.id
            logger.info(f"Training started with ID: {training.id}")
            
            # Ждем завершения обучения
            start_time = time.time()
            last_progress = 0
            
            while training.status not in ["succeeded", "failed", "canceled"]:
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд
                training.reload()
                
                # Обновляем прогресс
                elapsed_time = int((time.time() - start_time) / 60)
                estimated_progress = min(95, int((elapsed_time / 20) * 100))
                
                if estimated_progress > last_progress + 10:
                    last_progress = estimated_progress
                    try:
                        await message.edit_text(
                            f"🔄 Обучение модели...\n"
                            f"📊 Прогресс: ~{estimated_progress}%\n"
                            f"⏱ Прошло: {elapsed_time} минут\n\n"
                            f"Статус: {training.status}"
                        )
                    except:
                        pass  # Игнорируем ошибки редактирования
                
                # Таймаут через 30 минут
                if elapsed_time > 30:
                    raise Exception("Training timeout")
            
            if training.status == "succeeded":
                # Сохраняем URL обученной модели
                context.user_data['lora_model'] = training.output
                
                await message.edit_text(
                    "✅ Модель успешно обучена!\n\n"
                    "Теперь выберите стиль для генерации:",
                    reply_markup=self._get_styles_keyboard()
                )
                
                logger.info(f"Training completed: {training.output}")
                return SELECTING_STYLE
                
            else:
                raise Exception(f"Training failed: {training.status}")
            
        except Exception as e:
            logger.error(f"Error in LoRA training: {e}")
            await update.callback_query.message.reply_text(
                f"❌ Ошибка при обучении: {str(e)[:200]}\n\n"
                "Попробуйте позже или используйте быстрый режим.\n"
                "/start - начать заново"
            )
            return ConversationHandler.END
    
    async def _generate_with_lora(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация с обученной LoRA моделью"""
        try:
            style_id = context.user_data['selected_style']
            style_info = STYLES[style_id]
            lora_model = context.user_data.get('lora_model')
            
            if not lora_model:
                raise Exception("LoRA model not found")
            
            logger.info(f"Generating with LoRA model: {lora_model}")
            
            # Генерация с использованием обученной LoRA
            output = replicate.run(
                lora_model,
                input={
                    "prompt": f"OHWX person, {style_info['prompt']}, masterpiece, best quality",
                    "negative_prompt": f"{style_info['negative']}, ugly, deformed",
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                    "width": 1024,
                    "height": 1024,
                    "num_outputs": 2
                }
            )
            
            # Отправляем результаты
            if output:
                for i, img_url in enumerate(output[:2], 1):
                    await update.callback_query.message.reply_photo(
                        photo=img_url,
                        caption=f"✨ Вариант {i} в стиле {style_info['name']}"
                    )
                
                await update.callback_query.message.reply_text(
                    "🎉 Ваша персональная модель готова!\n"
                    "Можете генерировать неограниченно в разных стилях.\n\n"
                    "Попробуйте другие стили или /start для нового сеанса."
                )
                
                # Предлагаем еще опции
                keyboard = [
                    [InlineKeyboardButton("🎨 Другой стиль", callback_data="more_styles_lora")],
                    [InlineKeyboardButton("🏠 В начало", callback_data="restart")]
                ]
                
                await update.callback_query.message.reply_text(
                    "Продолжить генерацию?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
        except Exception as e:
            logger.error(f"Error in LoRA generation: {e}")
            await update.callback_query.message.reply_text(
                f"❌ Ошибка при генерации: {str(e)[:200]}\n"
                "Попробуйте еще раз."
            )
        
        return ConversationHandler.END
    
    async def handle_more_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка дополнительных действий"""
        query = update.callback_query
        await query.answer()
        
        if query.data in ["more_styles", "more_styles_lora"]:
            # Показываем стили снова
            await query.edit_message_text(
                "Выберите новый стиль:",
                reply_markup=self._get_styles_keyboard()
            )
            return SELECTING_STYLE
            
        elif query.data == "new_photo":
            context.user_data['photos'] = []
            await query.edit_message_text(
                "📸 Отправьте новое фото:"
            )
            return UPLOADING_INSTANT
            
        elif query.data == "restart":
            # Начинаем заново
            keyboard = [
                [InlineKeyboardButton("⚡ Быстрая генерация", callback_data="mode_instant")],
                [InlineKeyboardButton("🎯 Pro режим (LoRA)", callback_data="mode_lora")],
                [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
            ]
            await query.edit_message_text(
                "Выберите режим:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return CHOOSING_MODE
    
    def _get_error_message(self, error):
        """Получение понятного сообщения об ошибке"""
        error_str = str(error).lower()
        
        if "billing" in error_str or "payment" in error_str:
            return "❌ Ошибка: Проверьте баланс на Replicate"
        elif "api" in error_str or "token" in error_str:
            return "❌ Ошибка: Проблема с API токеном"
        elif "rate" in error_str:
            return "❌ Слишком много запросов. Подождите минуту"
        elif "timeout" in error_str:
            return "❌ Превышено время ожидания"
        else:
            return f"❌ Ошибка: {error_str[:100]}"
    
    async def show_styles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все доступные стили"""
        styles_text = "🎨 **Доступные стили:**\n\n"
        for style_id, style_info in STYLES.items():
            styles_text += f"{style_info['name']}\n"
        
        styles_text += "\n8 уникальных стилей для ваших аватарок!\n\nИспользуйте /start чтобы начать"
        
        await update.message.reply_text(styles_text, parse_mode='Markdown')
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущей операции"""
        await update.message.reply_text(
            "Операция отменена. Используйте /start чтобы начать заново."
        )
        return ConversationHandler.END
    
    def run(self):
        """Запуск бота"""
        try:
            # Создаем приложение
            application = Application.builder().token(self.telegram_token).build()
            
            # Создаем ConversationHandler
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("start", self.start)],
                states={
                    CHOOSING_MODE: [
                        CallbackQueryHandler(self.mode_selection)
                    ],
                    UPLOADING_INSTANT: [
                        MessageHandler(filters.PHOTO, self.handle_instant_photo),
                        CallbackQueryHandler(self.handle_more_actions)
                    ],
                    UPLOADING_LORA: [
                        MessageHandler(filters.PHOTO, self.handle_lora_photos),
                        CallbackQueryHandler(self.handle_lora_decision)
                    ],
                    SELECTING_STYLE: [
                        CallbackQueryHandler(self.handle_style_selection)
                    ],
                    WAITING_LORA: [
                        CallbackQueryHandler(self.handle_style_selection)
                    ]
                },
                fallbacks=[
                    CommandHandler("cancel", self.cancel),
                    CallbackQueryHandler(self.handle_more_actions)
                ],
                per_message=False  # Важно для работы CommandHandler
            )
            
            # Добавляем обработчики
            application.add_handler(conv_handler)
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(CommandHandler("styles", self.show_styles))
            
            # Простая команда для теста
            async def test_cmd(update, context):
                await update.message.reply_text("✅ Бот работает! Используйте /start")
            application.add_handler(CommandHandler("test", test_cmd))
            
            # Запускаем бота
            logger.info("Starting bot polling...")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise

# Конфигурация и запуск
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Получаем токены и очищаем их
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()
    
    # Дополнительная очистка от невидимых символов
    TELEGRAM_BOT_TOKEN = ''.join(c for c in TELEGRAM_BOT_TOKEN if c.isprintable())
    REPLICATE_API_TOKEN = ''.join(c for c in REPLICATE_API_TOKEN if c.isprintable())
    
    # Проверка токенов
    if not TELEGRAM_BOT_TOKEN or not REPLICATE_API_TOKEN:
        logger.error("❌ Ошибка: Не установлены токены!")
        logger.error("Установите TELEGRAM_BOT_TOKEN и REPLICATE_API_TOKEN")
        sys.exit(1)
    
    # Валидация формата токена Telegram
    if ':' not in TELEGRAM_BOT_TOKEN:
        logger.error("❌ Неверный формат TELEGRAM_BOT_TOKEN!")
        sys.exit(1)
    
    # Безопасный вывод токенов
    safe_tg = f"{TELEGRAM_BOT_TOKEN.split(':')[0]}:***"
    safe_rep = f"{REPLICATE_API_TOKEN[:4]}...{REPLICATE_API_TOKEN[-4:]}" if len(REPLICATE_API_TOKEN) > 8 else "***"
    
    # Создаем и запускаем бота
    try:
        bot = AvatarBot(TELEGRAM_BOT_TOKEN, REPLICATE_API_TOKEN)
        
        logger.info("="*50)
        logger.info("🤖 Telegram Avatar Bot v2.0")
        logger.info("="*50)
        logger.info(f"✅ Telegram Token: {safe_tg}")
        logger.info(f"✅ Replicate Token: {safe_rep}")
        logger.info("🚀 Starting bot on Railway...")
        logger.info("="*50)
        
        bot.run()
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
