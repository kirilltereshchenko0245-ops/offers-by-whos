# OfferBot

Независимый маленький Telegram-бот только для Telegram Business + оферов NFT + Accept/Decline + кнопки Transfer. Без Telethon, MTProto, scanner/parser/GiftParser.

## Установка

1. Создайте бота через BotFather.
2. Скопируйте `.env.example` в `.env`.
3. Укажите `BOT_TOKEN` и `OWNER_ID`.
4. Установите зависимости:

```bash
pip install -r requirements.txt
```

5. Запустите:

```bash
python bot.py
```

SQLite создаётся автоматически. Используется WAL и timeout 30.

## Business

Подключите Telegram Business к боту. В Business-чате проверьте:

```text
.привет
.бизнестест
```

Обычный тест:

```text
.привет
```

Для Business update всегда используется `message.business_connection_id`. OWNER_ID никогда не подставляется вместо connection_id.

## Офер

```text
купить https://t.me/nft/PartySparkler-140864 150 грам
купить https://t.me/nft/PartySparkler-140864 4500 зв
купить https://t.me/nft/PartySparkler-140864 2000 р
```

Языки (добавить в конец команды):

```text
купить https://t.me/nft/... 500 грам англ
купить https://t.me/nft/... 500 грам араб
купить https://t.me/nft/... 500 грам китай
```

Поддерживаются:
- `грам/грамм/gram/grams`
- `зв/звёзд/звезд/stars/star`
- `р/руб/рубль/рублей/rub`

## Transfer target

Продавец может сохранить username:

```text
/transfer witensea
```

После этого кнопка Transfer открывает `tg://send_gift?to=witensea`.

## Админка

Только `OWNER_ID`:

```text
/admin
/allow 123456789
/block 123456789
/unblock 123456789
```

`OFFER_ACCESS_MODE=owner`: доступ имеют владелец и пользователи из `offer_access_users`.
`OFFER_ACCESS_MODE=all`: доступ имеют все, кроме заблокированных.

`OFFER_ALWAYS_ALLOWED_IDS=8628184531` автоматически добавляет ID в allow-list при каждом запуске.

## Безопасность

Токен не хранится в Python-коде и не логируется. Рабочий токен должен находиться только в `.env`, который добавлен в `.gitignore`.

> Если токен уже был опубликован в чате/репозитории, безопаснее перевыпустить его через BotFather и заменить значение в `.env`.

## Проверки

```bash
python -m py_compile *.py
```

Проверяются также импорт модулей, SQLite schema, parser examples, callback data и наличие `allowed_updates=dp.resolve_used_update_types()`.
