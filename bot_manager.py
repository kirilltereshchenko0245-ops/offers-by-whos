# -*- coding: utf-8 -*-
"""
Менеджер клиентских ботов
Управляет запуском и остановкой ботов пользователей
"""

import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError, TelegramBadRequest
from aiogram.types import BusinessConnection, Message

from config import Config
from database import Database
from offer import parse_offer, display_amount, format_remaining, gift_title, make_expiry
from offer import ACCEPT_EMOJI_ID, DECLINE_EMOJI_ID, GIFT_EMOJI_ID, TRANSFER_EMOJI_ID, CONFIRM_EMOJI_ID
from translations import t, get_user_locale

log = logging.getLogger("bot_manager")


class ClientBot:
    """Один клиентский бот"""
    
    def __init__(self, bot_id: int, token: str, owner_id: int, db: Database, cfg: Config):
        self.bot_id = bot_id
        self.token = token
        self.owner_id = owner_id
        self.db = db
        self.cfg = cfg
        
        self.bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.task: Optional[asyncio.Task] = None
        self.is_running = False
        
        # Регистрируем handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Регистрируем обработчики событий"""
        
        @self.dp.business_connection()
        async def on_business_connection(bc: BusinessConnection):
            self.db.upsert_business_connection(bc.id, bc.user.id, bc.user.username, 
                                             bc.user.first_name, bc.user.last_name, bc.is_enabled)
            log.info(f"[BOT {self.bot_id}] Business connection id={bc.id} user_id={bc.user.id}")
        
        @self.dp.business_message()
        async def on_business_message(message: Message):
            await self._handle_message(message, True)
    
    async def _handle_message(self, message: Message, is_business: bool):
        """Обработка сообщений"""
        text = (message.text or "").strip().lower()
        
        # Команда "купить"
        if text.startswith("купить ") or text.startswith("buy "):
            await self._process_offer(message, message.business_connection_id if is_business else None)
    
    async def _process_offer(self, message: Message, business_connection_id: str | None = None):
        """Обработка создания офера"""
        from bot import process_offer_logic  # Импортируем общую логику
        
        # Проверяем что у владельца бота есть активный доступ
        if not self.db.has_access(self.owner_id, self.cfg.owner_id, self.cfg.offer_access_mode):
            await self._reply_message(message, "❌ У владельца бота истёк доступ. Обратитесь к @witensea")
            return
        
        # Обрабатываем офер через общую логику
        await process_offer_logic(
            message=message,
            business_connection_id=business_connection_id,
            db=self.db,
            cfg=self.cfg,
            bot=self.bot,
            force_seller_id=None  # Используем реального отправителя
        )
    
    async def _reply_message(self, message: Message, text: str):
        """Ответ на сообщение"""
        try:
            if message.business_connection_id:
                await self.bot.send_message(
                    chat_id=message.chat.id,
                    business_connection_id=message.business_connection_id,
                    text=text
                )
            else:
                await self.bot.send_message(chat_id=message.chat.id, text=text)
        except Exception as e:
            log.error(f"[BOT {self.bot_id}] Failed to reply: {e}")
    
    async def start(self):
        """Запуск бота"""
        if self.is_running:
            return
        
        try:
            self.is_running = True
            self.task = asyncio.create_task(self._run())
            log.info(f"[BOT {self.bot_id}] Started for user {self.owner_id}")
        except Exception as e:
            log.error(f"[BOT {self.bot_id}] Failed to start: {e}")
            self.is_running = False
            raise
    
    async def _run(self):
        """Основной цикл бота"""
        try:
            await self.dp.start_polling(
                self.bot,
                allowed_updates=self.dp.resolve_used_update_types()
            )
        except Exception as e:
            log.error(f"[BOT {self.bot_id}] Polling error: {e}")
        finally:
            self.is_running = False
    
    async def stop(self):
        """Остановка бота"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        await self.bot.session.close()
        log.info(f"[BOT {self.bot_id}] Stopped")
    
    async def verify_token(self) -> tuple[bool, str]:
        """Проверка валидности токена"""
        try:
            me = await self.bot.get_me()
            return True, me.username or f"bot_{me.id}"
        except TelegramUnauthorizedError:
            return False, "Неверный токен"
        except Exception as e:
            return False, str(e)


class BotManager:
    """Менеджер всех клиентских ботов"""
    
    def __init__(self, db: Database, cfg: Config):
        self.db = db
        self.cfg = cfg
        self.bots: Dict[int, ClientBot] = {}  # bot_id -> ClientBot
    
    async def load_all_bots(self):
        """Загрузка и запуск всех активных ботов из БД"""
        bots = self.db.get_all_client_bots(active_only=True)
        
        for bot_data in bots:
            try:
                await self.start_bot(
                    bot_id=bot_data["id"],
                    token=bot_data["token"],
                    owner_id=bot_data["owner_id"]
                )
            except Exception as e:
                log.error(f"Failed to start bot {bot_data['id']}: {e}")
    
    async def start_bot(self, bot_id: int, token: str, owner_id: int) -> tuple[bool, str]:
        """Запуск одного бота"""
        # Проверяем что бот не запущен
        if bot_id in self.bots:
            return False, "Бот уже запущен"
        
        try:
            # Создаём экземпляр бота
            client_bot = ClientBot(bot_id, token, owner_id, self.db, self.cfg)
            
            # Проверяем токен
            is_valid, error = await client_bot.verify_token()
            if not is_valid:
                await client_bot.stop()
                return False, f"Ошибка токена: {error}"
            
            # Запускаем
            await client_bot.start()
            self.bots[bot_id] = client_bot
            
            return True, "Бот успешно запущен"
        except Exception as e:
            log.exception(f"Failed to start bot {bot_id}")
            return False, str(e)
    
    async def stop_bot(self, bot_id: int) -> tuple[bool, str]:
        """Остановка бота"""
        if bot_id not in self.bots:
            return False, "Бот не найден"
        
        try:
            client_bot = self.bots[bot_id]
            await client_bot.stop()
            del self.bots[bot_id]
            return True, "Бот остановлен"
        except Exception as e:
            log.exception(f"Failed to stop bot {bot_id}")
            return False, str(e)
    
    async def restart_bot(self, bot_id: int) -> tuple[bool, str]:
        """Перезапуск бота"""
        # Получаем данные из БД
        bot_data = self.db.get_client_bot(bot_id)
        if not bot_data:
            return False, "Бот не найден в БД"
        
        # Останавливаем если запущен
        if bot_id in self.bots:
            await self.stop_bot(bot_id)
        
        # Запускаем заново
        return await self.start_bot(bot_id, bot_data["token"], bot_data["owner_id"])
    
    async def stop_all(self):
        """Остановка всех ботов"""
        for bot_id in list(self.bots.keys()):
            await self.stop_bot(bot_id)
    
    def get_bot_status(self, bot_id: int) -> str:
        """Получить статус бота"""
        if bot_id in self.bots:
            return "🟢 Запущен" if self.bots[bot_id].is_running else "🟡 Запускается"
        return "🔴 Остановлен"
    
    def get_all_statuses(self) -> list[dict]:
        """Получить статусы всех ботов"""
        all_bots = self.db.get_all_client_bots(active_only=False)
        
        result = []
        for bot_data in all_bots:
            result.append({
                "id": bot_data["id"],
                "username": bot_data["username"],
                "owner_id": bot_data["owner_id"],
                "status": self.get_bot_status(bot_data["id"]),
                "is_active": bot_data["is_active"]
            })
        
        return result
