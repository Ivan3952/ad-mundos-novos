"""Показывает структуру SQLite-базы бота, чтобы написать импорт работ в галактику.
Ничего не меняет в базе (открывает только на чтение).
    python tools/inspect_db.py "Z:\\Личное\\SW\\art_event_bot\\<файл>.db"
Вывод скопируй и пришли — токены и личные данные в нём не печатаются, только 2 строки-примера на таблицу.
"""
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    cols = con.execute(f'PRAGMA table_info("{name}")').fetchall()
    n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    print(f"\n== {name} ({n} строк)")
    print("   " + ", ".join(f"{c[1]}:{c[2]}" for c in cols))
    for row in con.execute(f'SELECT * FROM "{name}" LIMIT 2'):
        print("   >", tuple(str(v)[:60] for v in row))
