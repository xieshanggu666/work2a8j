# -*- coding: utf-8 -*-
"""缺陷工单闭环状态流测试：派单/提交/复核/退回/超时与风险统计回写。"""
from datetime import timedelta

import pytest

from app.core.database import Base, engine, SessionLocal
from app.models import Line, Tower, Mission
from app.services.tickets import (
    WorkflowError,
    is_overdue,
    new_ticket,
    assign,
    submit,
    review,
    refresh_stats,
    utcnow,
)


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()
    Base.metadata.drop_all(bind=engine)


def make_mission(db):
    line = Line(code="L-F", name="流程测试线", voltage_kv=110, total_km=6.0, status="in_service")
    db.add(line)
    db.flush()
    db.add(Tower(line_id=line.id, seq=1, code="T-001", lat=30.5, lng=104.0, cum_km=0.0))
    m = Mission(
        code="MSN-F-001", name="流程任务", line_id=line.id,
        start_tower_id=1, end_tower_id=1,
        plan_km=1.0, estimated_battery_pct=0.3,
        priority="normal", status="completed",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def make_ticket(db, level="major"):
    m = make_mission(db)
    t = new_ticket(db, mission_id=m.id, code=f"WO-F-{m.id:02d}",
                   title="绝缘子破损", level=level, detail="现场复核")
    db.commit()
    db.refresh(t)
    return t


def test_new_ticket_sets_sla_due(db):
    t = make_ticket(db, level="critical")
    assert t.status == "open"
    assert t.due_at is not None
    delta = t.due_at - t.created_at.replace(tzinfo=None)
    assert 23 < delta.total_seconds() / 3600 < 25  # 重大缺陷 24h 时限
    assert any(e.action == "create" for e in t.events)


def test_full_closed_loop(db):
    t = make_ticket(db)
    assign(db, t, "张工")
    assert t.status == "processing"
    assert t.assignee == "张工" and t.assigned_at is not None

    submit(db, t, "已更换绝缘子")
    assert t.status == "resolved"
    assert t.resolve_note == "已更换绝缘子" and t.resolved_at is not None

    review(db, t, "李班长", approve=True)
    assert t.status == "closed"
    assert t.reviewer == "李班长" and t.closed_at is not None
    db.commit()
    actions = [e.action for e in t.events]
    assert actions == ["create", "assign", "submit", "approve"]


def test_review_reject_returns_to_processing(db):
    t = make_ticket(db)
    assign(db, t, "张工")
    submit(db, t, "已处理")
    old_due = t.due_at

    review(db, t, "李班长", approve=False, reason="照片不清晰，需复飞补拍")
    assert t.status == "processing"          # 退回处理中
    assert t.reject_count == 1
    assert "复飞补拍" in t.reject_reason
    assert t.due_at > old_due                # 退回后重新计时

    # 退回后仍可再次提交并通过复核闭环
    submit(db, t, "补拍完成")
    review(db, t, "李班长", approve=True)
    assert t.status == "closed"
    db.commit()
    actions = [e.action for e in t.events]
    assert actions == ["create", "assign", "submit", "reject", "submit", "approve"]


def test_invalid_transitions_raise(db):
    t = make_ticket(db)
    with pytest.raises(WorkflowError):
        submit(db, t)                        # 未派单不能提交
    with pytest.raises(WorkflowError):
        review(db, t, "李班长", True)        # 未提交不能复核
    assign(db, t, "张工")
    submit(db, t)
    with pytest.raises(WorkflowError):
        assign(db, t, "王工")                # 待复核不可派单
    with pytest.raises(WorkflowError):
        review(db, t, "李班长", approve=False, reason="")  # 退回必须填原因


def test_overdue_detection(db):
    t = make_ticket(db)
    assert not is_overdue(t)
    t.due_at = utcnow() - timedelta(hours=1)
    assert is_overdue(t)                     # 未闭环且越过时限 → 超时
    assign(db, t, "张工", due_hours=2)
    assert not is_overdue(t)                 # 派单重计时限
    t.due_at = utcnow() - timedelta(hours=1)
    t.status = "closed"
    assert not is_overdue(t)                 # 已闭环不再判超时


def test_stats_write_back_to_mission_and_line(db):
    m = make_mission(db)
    t1 = new_ticket(db, mission_id=m.id, code="WO-S-01", title="重大缺陷", level="critical")
    t2 = new_ticket(db, mission_id=m.id, code="WO-S-02", title="轻微缺陷", level="minor")
    for t in (t1, t2):
        refresh_stats(db, t)
    db.commit()
    db.refresh(m)
    db.refresh(m.line)

    assert m.open_ticket_count == 2          # 回写任务统计
    assert m.line.open_ticket_count == 2     # 回写线路统计
    assert m.line.risk_level == "key"        # 存在未闭环重大缺陷 → 重点

    # 重大缺陷闭环后降级为 normal（仅剩轻微）
    assign(db, t1, "张工")
    submit(db, t1, "已消缺")
    review(db, t1, "李班长", approve=True)
    refresh_stats(db, t1)
    db.commit()
    db.refresh(m.line)
    assert m.line.open_ticket_count == 1
    assert m.line.risk_level == "normal"

    # 全部闭环后归零
    assign(db, t2, "张工")
    submit(db, t2, "已处理")
    review(db, t2, "李班长", approve=True)
    refresh_stats(db, t2)
    db.commit()
    db.refresh(m)
    db.refresh(m.line)
    assert m.open_ticket_count == 0
    assert m.line.open_ticket_count == 0
    assert m.line.risk_level == "normal"


def test_major_open_makes_line_suspect(db):
    m = make_mission(db)
    t = new_ticket(db, mission_id=m.id, code="WO-S-03", title="较大缺陷", level="major")
    refresh_stats(db, t)
    db.commit()
    db.refresh(m.line)
    assert m.line.risk_level == "suspect"
