# -*- coding: utf-8 -*-
"""
Переводы для бота на разные языки
"""

TRANSLATIONS = {
    "ru": {
        # Главное меню
        "welcome": "<b>Привет лютый воркер телеграмма по нфт!</b>",
        "subscribe_first": "<b>Йоу, подпишись на канал чтобы инфу не пропускать :)</b>",
        "btn_buy_access": "💳 Купить доступ",
        "btn_instruction": "📖 Инструкция",
        "btn_subscribe": "📢 Подписаться на канал",
        "btn_subscribed": "✅ Я подписался",
        "btn_back": "« Назад",
        
        # Инструкция
        "instruction_title": "📖 Инструкция",
        "instruction_connect": "<b>1. Подключение Telegram Business</b>\nПодключите этого бота к своему Business аккаунту через настройки Telegram",
        "instruction_send": "<b>2. Отправка оферов</b>",
        "instruction_profile": "<b>3. Настройка профиля передачи</b>\n<code>/transfer @username</code>\nМеняет профиль в кнопке \"Передать\"",
        "instruction_note": "При заморозке аккаунта, напишите овнеру @witensea для переноса доступа.",
        
        # Оферы
        "offer_sold": "успешно продан!",
        "offer_transfer_text": "• Передайте подарок покупателю для зачисления {amount} на ваш баланс.",
        "offer_expired": "Предложение действует ещё <b>{time}</b>.",
        "offer_declined": "<b>Предложение отменено.</b>",
        "offer_seller": "Пoльзoвaтeль",
        "offer_text": "прeдлaгaeт Вам {amount} за пoдарок",
        
        # Кнопки оферов
        "btn_decline": "Отклонить",
        "btn_accept": "Принять",
        "btn_transfer": "Передать",
        "btn_confirm": "Подтвердить передачу",
        
        # Ошибки
        "no_access": "❌ <b>У тя нет доступа, нужна купить, атата</b>",
        "not_subscribed": "❌ Вы ещё не подписались на канал!",
        "subscribed_ok": "✅ Отлично!",
        
        # Подтверждение передачи
        "seller_confirmed": "Передача подтверждена, ждём подтверждение покупателя.",
        "buyer_confirmed": "Подарок {title} успешно передан покупателю!\n\nОжидайте зачисление {amount} в течении 60 минут.",
        "already_confirmed": "Вы уже подтвердили.",
        "seller_not_confirmed": "Продавец не подтвердил поступление подарка {title} на его аккаунт. Повторите попытку после того как продавец подтвердит передачу.",
        "transfer_already_confirmed": "Передача уже подтверждена.",
    },
    
    "en": {
        # Main menu
        "welcome": "<b>Hey crypto NFT worker!</b>",
        "subscribe_first": "<b>Yo, subscribe to the channel to not miss updates :)</b>",
        "btn_buy_access": "💳 Buy Access",
        "btn_instruction": "📖 Instructions",
        "btn_subscribe": "📢 Subscribe to channel",
        "btn_subscribed": "✅ I subscribed",
        "btn_back": "« Back",
        
        # Instructions
        "instruction_title": "📖 Instructions",
        "instruction_connect": "<b>1. Connect Telegram Business</b>\nConnect this bot to your Business account via Telegram settings",
        "instruction_send": "<b>2. Sending offers</b>",
        "instruction_profile": "<b>3. Transfer profile setup</b>\n<code>/transfer @username</code>\nChanges profile in \"Transfer\" button",
        "instruction_note": "If account is frozen, contact owner @witensea to transfer access.",
        
        # Offers
        "offer_sold": "successfully sold!",
        "offer_transfer_text": "• Transfer the gift to the buyer to credit {amount} to your balance.",
        "offer_expired": "Offer valid for <b>{time}</b>.",
        "offer_declined": "<b>Offer declined.</b>",
        "offer_seller": "User",
        "offer_text": "offers you {amount} for the gift",
        
        # Offer buttons
        "btn_decline": "Decline",
        "btn_accept": "Accept",
        "btn_transfer": "Transfer",
        "btn_confirm": "Confirm Transfer",
        
        # Errors
        "no_access": "❌ <b>You have no access, need to buy, oops</b>",
        "not_subscribed": "❌ You haven't subscribed to the channel yet!",
        "subscribed_ok": "✅ Great!",
        
        # Transfer confirmation
        "seller_confirmed": "Transfer confirmed, waiting for buyer confirmation.",
        "buyer_confirmed": "Gift {title} successfully transferred to the buyer!\n\nExpect {amount} to be credited within 60 minutes.",
        "already_confirmed": "You have already confirmed.",
        "seller_not_confirmed": "Seller has not confirmed receipt of gift {title} on their account. Try again after seller confirms transfer.",
        "transfer_already_confirmed": "Transfer already confirmed.",
    },
    
    "zh": {
        # 主菜单
        "welcome": "<b>嘿，NFT 加密工作者！</b>",
        "subscribe_first": "<b>嘿，订阅频道以免错过更新 :)</b>",
        "btn_buy_access": "💳 购买访问权限",
        "btn_instruction": "📖 说明",
        "btn_subscribe": "📢 订阅频道",
        "btn_subscribed": "✅ 我已订阅",
        "btn_back": "« 返回",
        
        # 说明
        "instruction_title": "📖 说明",
        "instruction_connect": "<b>1. 连接 Telegram Business</b>\n通过 Telegram 设置将此机器人连接到您的商业账户",
        "instruction_send": "<b>2. 发送报价</b>",
        "instruction_profile": "<b>3. 转账配置文件设置</b>\n<code>/transfer @username</code>\n更改\"转账\"按钮中的配置文件",
        "instruction_note": "如果账户被冻结，请联系所有者 @witensea 转移访问权限。",
        
        # 报价
        "offer_sold": "成功售出！",
        "offer_transfer_text": "• 将礼物转给买家以将 {amount} 记入您的余额。",
        "offer_expired": "报价有效期为 <b>{time}</b>。",
        "offer_declined": "<b>报价已拒绝。</b>",
        "offer_seller": "用户",
        "offer_text": "为礼物向您提供 {amount}",
        
        # 报价按钮
        "btn_decline": "拒绝",
        "btn_accept": "接受",
        "btn_transfer": "转账",
        "btn_confirm": "确认转账",
        
        # 错误
        "no_access": "❌ <b>您没有访问权限，需要购买</b>",
        "not_subscribed": "❌ 您还没有订阅频道！",
        "subscribed_ok": "✅ 太好了！",
        
        # 转账确认
        "seller_confirmed": "转账已确认，等待买家确认。",
        "buyer_confirmed": "礼物 {title} 成功转给买家！\n\n预计 {amount} 将在 60 分钟内入账。",
        "already_confirmed": "您已确认。",
        "seller_not_confirmed": "卖家尚未确认在其账户上收到礼物 {title}。卖家确认转账后重试。",
        "transfer_already_confirmed": "转账已确认。",
    },
    
    "ar": {
        # القائمة الرئيسية
        "welcome": "<b>مرحبا عامل NFT المشفر!</b>",
        "subscribe_first": "<b>مرحبا، اشترك في القناة حتى لا تفوت التحديثات :)</b>",
        "btn_buy_access": "💳 شراء الوصول",
        "btn_instruction": "📖 التعليمات",
        "btn_subscribe": "📢 اشترك في القناة",
        "btn_subscribed": "✅ لقد اشتركت",
        "btn_back": "« رجوع",
        
        # التعليمات
        "instruction_title": "📖 التعليمات",
        "instruction_connect": "<b>1. ربط Telegram Business</b>\nقم بتوصيل هذا البوت بحساب الأعمال الخاص بك عبر إعدادات Telegram",
        "instruction_send": "<b>2. إرسال العروض</b>",
        "instruction_profile": "<b>3. إعداد ملف التحويل</b>\n<code>/transfer @username</code>\nيغير الملف الشخصي في زر \"التحويل\"",
        "instruction_note": "إذا تم تجميد الحساب، اتصل بالمالك @witensea لنقل الوصول.",
        
        # العروض
        "offer_sold": "تم البيع بنجاح!",
        "offer_transfer_text": "• انقل الهدية إلى المشتري لإضافة {amount} إلى رصيدك.",
        "offer_expired": "العرض صالح لمدة <b>{time}</b>.",
        "offer_declined": "<b>تم رفض العرض.</b>",
        "offer_seller": "المستخدم",
        "offer_text": "يعرض عليك {amount} مقابل الهدية",
        
        # أزرار العروض
        "btn_decline": "رفض",
        "btn_accept": "قبول",
        "btn_transfer": "تحويل",
        "btn_confirm": "تأكيد التحويل",
        
        # الأخطاء
        "no_access": "❌ <b>ليس لديك إذن، يجب الشراء</b>",
        "not_subscribed": "❌ لم تشترك في القناة بعد!",
        "subscribed_ok": "✅ رائع!",
        
        # تأكيد التحويل
        "seller_confirmed": "تم تأكيد التحويل، في انتظار تأكيد المشتري.",
        "buyer_confirmed": "تم نقل الهدية {title} بنجاح إلى المشتري!\n\nتوقع إضافة {amount} خلال 60 دقيقة.",
        "already_confirmed": "لقد أكدت بالفعل.",
        "seller_not_confirmed": "لم يؤكد البائع استلام الهدية {title} على حسابه. حاول مرة أخرى بعد أن يؤكد البائع التحويل.",
        "transfer_already_confirmed": "تم تأكيد التحويل بالفعل.",
    }
}


def t(key: str, locale: str = "ru", **kwargs) -> str:
    """
    Получить перевод по ключу
    
    Args:
        key: ключ перевода
        locale: язык (ru, en, zh, ar)
        **kwargs: параметры для форматирования строки
    
    Returns:
        Переведенная строка
    """
    if locale not in TRANSLATIONS:
        locale = "ru"
    
    text = TRANSLATIONS.get(locale, {}).get(key, TRANSLATIONS["ru"].get(key, key))
    
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    
    return text


def get_user_locale(message) -> str:
    """
    Определить язык пользователя из сообщения
    Приоритет: 1) язык из команды офера 2) язык Telegram 3) русский
    """
    if hasattr(message, 'from_user') and message.from_user:
        lang_code = message.from_user.language_code
        if lang_code:
            if lang_code.startswith('en'):
                return 'en'
            elif lang_code.startswith('zh'):
                return 'zh'
            elif lang_code.startswith('ar'):
                return 'ar'
    return 'ru'
