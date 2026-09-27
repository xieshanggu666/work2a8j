from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 工单闭环升级新增列（对已有 SQLite 库幂等补齐）
_TICKET_NEW_COLUMNS = {
    "assignee": "VARCHAR(32)",
    "assigned_at": "DATETIME",
    "due_at": "DATETIME",
    "resolution": "TEXT DEFAULT ''",
    "reviewer": "VARCHAR(32)",
    "closed_at": "DATETIME",
    "return_reason": "TEXT DEFAULT ''",
    "return_count": "INTEGER DEFAULT 0",
}


def ensure_schema():
    """轻量迁移：为已存在的旧库补齐工单闭环新列（幂等）。"""
    insp = inspect(engine)
    if "repair_tickets" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("repair_tickets")}
    with engine.begin() as conn:
        for name, ddl in _TICKET_NEW_COLUMNS.items():
            if name not in cols:
                conn.execute(text(f"ALTER TABLE repair_tickets ADD COLUMN {name} {ddl}"))