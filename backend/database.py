import sqlite3
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("PHOTO_DB", r"C:\ML\photo_library.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path = None) -> None:
    target = db_path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(target))
    conn.executescript(schema)
    conn.commit()
    # Migrate: add columns added after initial schema creation
    for col_sql in [
        "ALTER TABLE photos ADD COLUMN embedding BLOB DEFAULT NULL",
        "ALTER TABLE photos ADD COLUMN phash TEXT DEFAULT NULL",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.close()
