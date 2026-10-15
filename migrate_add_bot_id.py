# -*- coding: utf-8 -*-
"""
Миграция: добавление bot_id в gift_offers
"""

import sqlite3
from pathlib import Path

def migrate():
    db_path = Path("data/offers.db")
    if not db_path.exists():
        print("❌ База данных не найдена")
        return
    
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    # Проверяем есть ли колонка bot_id
    cur.execute("PRAGMA table_info(gift_offers)")
    columns = [row[1] for row in cur.fetchall()]
    
    if "bot_id" in columns:
        print("✅ Колонка bot_id уже существует")
        con.close()
        return
    
    print("📝 Добавляю колонку bot_id...")
    
    try:
        # Добавляем колонку
        cur.execute("ALTER TABLE gift_offers ADD COLUMN bot_id INTEGER DEFAULT 0")
        
        # Создаём индекс
        cur.execute("CREATE INDEX IF NOT EXISTS idx_offers_bot ON gift_offers(bot_id)")
        
        con.commit()
        print("✅ Миграция выполнена успешно!")
        
        # Показываем статистику
        cur.execute("SELECT COUNT(*) FROM gift_offers WHERE bot_id = 0")
        count = cur.fetchone()[0]
        print(f"📊 Оферов от главного бота (bot_id=0): {count}")
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        con.rollback()
    finally:
        con.close()

if __name__ == "__main__":
    migrate()
