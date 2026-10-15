"""Тест переводов"""
from translations import t

# Тестируем разные языки
locales = ["ru", "en", "zh", "ar"]

print("Тест кнопок:")
for locale in locales:
    print(f"\n{locale}:")
    print(f"  btn_accept: {t('btn_accept', locale)}")
    print(f"  btn_decline: {t('btn_decline', locale)}")
    print(f"  btn_transfer: {t('btn_transfer', locale)}")
    print(f"  btn_confirm: {t('btn_confirm', locale)}")

print("\n\nТест текстов оферов:")
for locale in locales:
    print(f"\n{locale}:")
    print(f"  offer_seller: {t('offer_seller', locale)}")
    print(f"  offer_text: {t('offer_text', locale, amount='1000₽')}")
    print(f"  offer_sold: {t('offer_sold', locale)}")

print("\n\nТест с параметрами:")
title = "PartySparkler #123"
print(f"RU: {t('buyer_confirmed', 'ru', title=title)}")
print(f"EN: {t('buyer_confirmed', 'en', title=title)}")
print(f"ZH: {t('buyer_confirmed', 'zh', title=title)}")
print(f"AR: {t('buyer_confirmed', 'ar', title=title)}")
