# -*- coding: utf-8 -*-
"""
Менеджер клиентских ботов
Управляет запуском и остановкой ботов пользователей
"""

import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BusinessConnection, Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

from config import Config
from database import Database
from offer import parse_offer, display_amount, format_remaining, gift_title, make_expiry
from offer import ACCEPT_EMOJI_ID, DECLINE_EMOJI_ID, GIFT_EMOJI_ID, TRANSFER_EMOJI_ID, CONFIRM_EMOJI_ID
from translations import t

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
        self.offer_locks = {}
        
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
        
        @self.dp.callback_query(F.data.startswith("of:"))
        async def offer_callback(call: CallbackQuery):
            await self._handle_offer_callback(call)
    
    async def _handle_message(self, message: Message, is_business: bool):
        """Обработка сообщений"""
        text = (message.text or "").strip().lower()
        
        # Команда "купить"
        if text.startswith("купить ") or text.startswith("buy "):
            await self._process_offer(message, message.business_connection_id if is_business else None)
    
    async def _process_offer(self, message: Message, business_connection_id: str | None = None):
        """Обработка создания офера - полная копия логики главного бота"""
        text = message.text or message.caption or ""
        parsed = parse_offer(text)
        
        if text.strip().lower() in {"купить", "buy"}:
            instruction = ("📖 <b>Использование</b>\n\n"
                          "<code>купить https://t.me/nft/... 150 грам</code>\n"
                          "<code>купить https://t.me/nft/... 4500 зв</code>\n"
                          "<code>купить https://t.me/nft/... 2000 р</code>")
            await self._reply_message(message, instruction)
            return
        
        if parsed.get("error"):
            error_msg = "❌ Ошибка в команде"
            if parsed["error"] == "nft":
                error_msg = "❌ Не нашёл ссылку на NFT.\n\n<code>купить https://t.me/nft/... 150 грам</code>"
            elif parsed["error"] == "price":
                error_msg = "❌ Не нашёл цену офера.\n\n<code>купить https://t.me/nft/... 150 грам</code>"
            await self._reply_message(message, error_msg)
            return
        
        sender = message.from_user
        if not sender:
            await self._reply_message(message, "❌ Не удалось определить отправителя.")
            return
        
        # Проверяем что у владельца бота есть активный доступ
        if not self.db.has_access(self.owner_id, self.cfg.owner_id, self.cfg.offer_access_mode):
            await self._reply_message(message, "❌ У владельца бота истёк доступ. Обратитесь к @witensea")
            return
        
        if not business_connection_id:
            await self._reply_message(message, "❌ Эта команда работает только через Telegram Business")
            return
        
        bc = self.db.get_business_connection(business_connection_id)
        if not bc or not bc["is_enabled"]:
            await self._reply_message(message, "❌ Для офера сначала подключите Telegram Business к этому боту.")
            return
        
        seller_id = bc["user_id"]
        buyer_id = message.chat.id
        seller_username = bc["username"]
        buyer_username = sender.username
        buyer_url = f"tg://user?id={buyer_id}"
        
        if self.db.is_blocked(seller_id) or int(bc["is_blocked"]):
            await self._reply_message(message, "❌ Доступ заблокирован")
            return
        
        # Получаем профиль для transfer
        profile = self.db.get_profile(seller_id)
        transfer_username = profile["name"] if profile and profile["name"] else seller_username
        transfer_url = (f"tg://send_gift?to={transfer_username.lstrip('@')}" if transfer_username else f"tg://user?id={seller_id}")
        
        # Создаём офер
        now = datetime.now(timezone.utc)
        expires = make_expiry(now, self.cfg.offer_expire_hours)
        
        data = dict(
            bot_id=self.bot_id,  # ID клиентского бота
            seller_id=seller_id, seller_username=seller_username, 
            buyer_id=buyer_id, buyer_username=buyer_username, buyer_url=buyer_url,
            gift_name=parsed["gift_name"], gift_number=parsed["gift_number"], gift_url=parsed["gift_url"],
            amount=parsed["amount"], currency=parsed["currency"], locale=parsed["locale"],
            status="pending", created_at=now.isoformat(), expires_at=expires.isoformat(),
            message_chat_id=None, message_id=None, business_connection_id=business_connection_id,
            transfer_url=transfer_url
        )
        
        offer_id = self.db.create_offer(data)
        log.info(f"[BOT {self.bot_id}] OFFER CREATE offer_id={offer_id} seller_id={seller_id} buyer_id={buyer_id}")
        
        # Отправляем офер
        seller_name = " ".join(x for x in [bc["first_name"], bc["last_name"]] if x) or "Пользователь"
        title = gift_title(parsed["gift_name"], parsed["gift_number"])
        amount_str = display_amount(parsed["amount"], parsed["currency"])
        remaining = format_remaining((expires - now).total_seconds())
        
        body = f"Пoльзoвaтeль <b>{seller_name}</b> прeдлaгaeт Вам {amount_str} за пoдарок <a href=\"{parsed['gift_url']}\">{title}</a>.\n\nПредложение действует ещё <b>{remaining}</b>."
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Отклонить", icon_custom_emoji_id=DECLINE_EMOJI_ID, callback_data=f"of:decline:{offer_id}"),
            InlineKeyboardButton(text="Принять", icon_custom_emoji_id=ACCEPT_EMOJI_ID, callback_data=f"of:accept:{offer_id}"),
        ]])
        
        try:
            sent = await self.bot.send_message(
                chat_id=buyer_id,
                business_connection_id=business_connection_id,
                text=body,
                reply_markup=kb,
                link_preview_options=LinkPreviewOptions(url=parsed["gift_url"], show_above_text=True)
            )
            self.db.set_offer_message(offer_id, buyer_id, sent.message_id)
            log.info(f"[BOT {self.bot_id}] OFFER SENT offer_id={offer_id}")
            
            # Удаляем исходное сообщение
            try:
                await self.bot.delete_business_messages(
                    business_connection_id=business_connection_id,
                    message_ids=[message.message_id]
                )
            except Exception:
                pass
                
        except Exception as e:
            log.exception(f"[BOT {self.bot_id}] OFFER SEND FAILED offer_id={offer_id} error={e}")
            self.db.delete_offer(offer_id)
            await self._reply_message(message, "❌ Не удалось отправить офер. Попробуйте ещё раз позже.")
    
    async def _handle_offer_callback(self, call: CallbackQuery):
        """Обработка callback'ов от оферов"""
        parts = call.data.split(":")
        if len(parts) < 3 or not parts[2].isdigit():
            await call.answer("Некорректный офер.", show_alert=True)
            return
        
        offer_id = int(parts[2])
        action = parts[1]
        
        # Обработка подтверждения передачи
        if action == "confirm":
            offer = self.db.get_offer(offer_id)
            if not offer:
                await call.answer("Офер не найден.", show_alert=True)
                return
            
            if offer["status"] != "accepted":
                await call.answer("Этот офер ещё не принят.", show_alert=True)
                return
            
            title = gift_title(offer["gift_name"], offer["gift_number"])
            amount = display_amount(offer["amount"], offer["currency"])
            
            is_seller = call.from_user and call.from_user.id == offer["seller_id"]
            is_buyer = call.from_user and call.from_user.id == offer["buyer_id"]
            
            if not is_seller and not is_buyer:
                await call.answer("Это не ваш офер.", show_alert=True)
                return
            
            # Продавец подтверждает первым
            if is_seller:
                if offer["seller_confirmed"]:
                    await call.answer(t("already_confirmed", offer["locale"]), show_alert=True)
                    return
                
                self.db.confirm_seller(offer_id)
                await call.answer(t("seller_confirmed", offer["locale"]), show_alert=True)
                return
            
            # Покупатель подтверждает вторым
            if is_buyer:
                if not offer["seller_confirmed"]:
                    await call.answer(t("seller_not_confirmed", offer["locale"], title=title), show_alert=True)
                    return
                
                if offer["buyer_confirmed"]:
                    await call.answer(t("transfer_already_confirmed", offer["locale"]), show_alert=True)
                    return
                
                self.db.confirm_buyer(offer_id)
                await call.answer(t("buyer_confirmed", offer["locale"], title=title, amount=amount), show_alert=True)
                return
        
        # Обработка принятия/отклонения
        if action not in {"accept", "decline"}:
            await call.answer("Некорректный офер.", show_alert=True)
            return
        
        if offer_id not in self.offer_locks:
            self.offer_locks[offer_id] = asyncio.Lock()
        
        async with self.offer_locks[offer_id]:
            offer = self.db.get_offer(offer_id)
            if not offer or offer["status"] != "pending":
                await call.answer("Офер уже обработан.", show_alert=True)
                return
            
            if action == "accept":
                url = offer["transfer_url"] or f"tg://user?id={offer['seller_id']}"
                title = gift_title(offer["gift_name"], offer["gift_number"])
                gift_url = offer["gift_url"]
                amount = display_amount(offer['amount'], offer['currency'])
                
                final = f"<tg-emoji emoji-id=\"{GIFT_EMOJI_ID}\">🎁</tg-emoji> Gift: <a href=\"{gift_url}\">{title}</a> {t('offer_sold', offer['locale'])}\n\n{t('offer_transfer_text', offer['locale'], amount=amount)}"
                
                transfer_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=t("btn_transfer", offer["locale"]),
                        icon_custom_emoji_id=TRANSFER_EMOJI_ID, url=url)],
                    [InlineKeyboardButton(
                        text=t("btn_confirm", offer["locale"]),
                        icon_custom_emoji_id=GIFT_EMOJI_ID,
                        callback_data=f"of:confirm:{offer_id}")]
                ])
                
                try:
                    sent = await self.bot.send_message(
                        chat_id=offer["buyer_id"],
                        business_connection_id=offer["business_connection_id"],
                        text=final,
                        reply_markup=transfer_kb,
                        link_preview_options=LinkPreviewOptions(url=gift_url, show_above_text=True)
                    )
                    try:
                        await self.bot.delete_business_messages(
                            business_connection_id=offer["business_connection_id"],
                            message_ids=[offer["message_id"]]
                        )
                    except Exception:
                        pass
                    
                    self.db.set_offer_message(offer_id, offer["buyer_id"], sent.message_id)
                    self.db.update_offer_status(offer_id, "accepted", url)
                    log.info(f"[BOT {self.bot_id}] OFFER ACCEPT offer_id={offer_id}")
                    
                    answer_text = f"{title} {t('offer_sold', offer['locale'])}"
                    await call.answer(answer_text, show_alert=True)
                except Exception as e:
                    log.exception(f"[BOT {self.bot_id}] OFFER ACCEPT FAILED offer_id={offer_id}")
                    await call.answer("Не удалось завершить принятие офера.", show_alert=True)
            else:
                # Decline
                final = f"<tg-emoji emoji-id=\"{DECLINE_EMOJI_ID}\">❌</tg-emoji> {t('offer_declined', offer['locale'])}"
                try:
                    sent = await self.bot.send_message(
                        chat_id=offer["buyer_id"],
                        business_connection_id=offer["business_connection_id"],
                        text=final
                    )
                    try:
                        await self.bot.delete_business_messages(
                            business_connection_id=offer["business_connection_id"],
                            message_ids=[offer["message_id"]]
                        )
                    except Exception:
                        pass
                    
                    self.db.set_offer_message(offer_id, offer["buyer_id"], sent.message_id)
                    self.db.update_offer_status(offer_id, "declined")
                    log.info(f"[BOT {self.bot_id}] OFFER DECLINE offer_id={offer_id}")
                    await call.answer("Предложение отклонено.")
                except Exception:
                    await call.answer("Не удалось отклонить офер.", show_alert=True)
    
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
