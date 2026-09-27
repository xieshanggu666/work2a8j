# -*- coding: utf-8 -*-
"""轻量迁移：为已有 SQLite 数据库补齐新增列并回填数据。

create_all 只会建新表，不会改老表；这里用 PRAGMA 检查列是否存在，
缺失则 ALTER TABLE 补齐，再回填工单时限与任务/线路风险统计。
"""
from datetime import timedelta

from sqlalchemy import text

from .database import engine, SessionLocal, Base
from ..models import RepairTicket
from ..services.tickets import sla_hours, refresh_all_stats, utcnow

# 表 -> [(列名, 列定义)]
NEW_COLUMNS = {
    "repair_tickets": [
        ("assignee", "VARCHAR(32)"),
        ("assigned_at", "DATETIME"),
        ("due_at", "DATETIME"),
        ("resolve_note", "TEXT NOT NULL DEFAULT ''"),
        ("reviewer", "VARCHAR(32)"),
        ("reviewed_at", "DATETIME"),
        ("closed_at", "DATETIME"),
        ("reject_reason", "TEXT NOT NULL DEFAULT ''"),
        ("reject_count", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "missions": [
        ("open_ticket_count", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "lines": [
        ("risk_level", "VARCHAR(16) NOT NULL DEFAULT 'normal'"),
        ("open_ticket_count", "INTEGER NOT NULL DEFAULT 0"),
    ],
}


def run_migrations():
    # 新表（如 ticket_events）由 create_all 建立
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table, cols in NEW_COLUMNS.items():
            existing = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

    # 回填：老工单补处理时限；全量重算任务/线路统计
    db = SessionLocal()
    try:
        for t in db.query(RepairTicket).filter(RepairTicket.due_at.is_(None)).all():
            base = t.created_at or utcnow()
            t.due_at = base + timedelta(hours=sla_hours(t.level))
        refresh_all_stats(db)
        db.commit()
    finally:
        db.close()
