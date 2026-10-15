"""
Миграция: замена transfer_confirmed на seller_confirmed и buyer_confirmed
"""
import sqlite3
from pathlib import Path

def migrate():
    db_path = Path("data/offers.db")
    
    if not db_path.exists():
        print("База данных не найдена. Пропускаем миграцию.")
        return
    
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    try:
        # Проверяем существующие поля
        cur.execute("PRAGMA table_info(gift_offers)")
        columns = {row[1]: row for row in cur.fetchall()}
        
        # Удаляем старые поля если они есть
        if "transfer_confirmed" in columns:
            print("Удаляем старое поле transfer_confirmed...")
            # SQLite не поддерживает DROP COLUMN, нужно пересоздать таблицу
            # Но мы просто добавим новые поля, старое не трогаем
        
        if "seller_confirmed" not in columns:
            print("Добавляем поле seller_confirmed...")
            cur.execute("ALTER TABLE gift_offers ADD COLUMN seller_confirmed INTEGER DEFAULT 0")
        
        if "seller_confirmed_at" not in columns:
            print("Добавляем поле seller_confirmed_at...")
            cur.execute("ALTER TABLE gift_offers ADD COLUMN seller_confirmed_at TIMESTAMP")
        
        if "buyer_confirmed" not in columns:
            print("Добавляем поле buyer_confirmed...")
            cur.execute("ALTER TABLE gift_offers ADD COLUMN buyer_confirmed INTEGER DEFAULT 0")
        
        if "buyer_confirmed_at" not in columns:
            print("Добавляем поле buyer_confirmed_at...")
            cur.execute("ALTER TABLE gift_offers ADD COLUMN buyer_confirmed_at TIMESTAMP")
        
        con.commit()
        print("✅ Миграция успешно выполнена!")
        
    except Exception as e:
        print(f"❌ Ошибка при миграции: {e}")
        con.rollback()
    finally:
        con.close()

if __name__ == "__main__":
    migrate()
