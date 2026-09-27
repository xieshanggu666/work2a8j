# -*- coding: utf-8 -*-
"""缺陷工单闭环状态流测试：派单/提交/复核/退回/超时与风险统计回写。"""
from datetime import timedelta

import pytest

from app.core.database import Base, engine, SessionLocal
from app.models import Line, Tower, Mission
from app.services import ticket_flow as flow
from app.services.ticket_flow import TicketFlowError


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()
    Base.metadata.drop_all(bind=engine)


def make_ctx(db):
    """一条线路 + 一基杆塔 + 一个已完成任务。"""
    line = Line(code="L-T", name="测试线路", voltage_kv=110, total_km=6.0, status="in_service")
    db.add(line)
    db.flush()
    tower = Tower(line_id=line.id, seq=1, code="T-001", lat=30.5, lng=104.0,
                  cum_km=0.0, risk_hint="normal")
    db.add(tower)
    db.flush()
    m = Mission(code="MSN-T", name="测试任务", line_id=line.id,
                start_tower_id=tower.id, end_tower_id=tower.id,
                plan_km=1.0, estimated_battery_pct=0.2,
                priority="normal", status="completed", route=[])
    db.add(m)
    db.commit()
    db.refresh(line)
    return line, tower, m


def test_full_close_loop(db):
    """open → processing → resolved → closed 全链路字段落库。"""
    line, tower, m = make_ctx(db)
    t = flow.make_ticket(m.id, 1, tower_id=tower.id, title="绝缘子破损", level="major")
    db.add(t)
    db.commit()

    flow.assign(db, t, "张三")
    assert t.status == "processing"
    assert t.assignee == "张三"
    assert t.assigned_at is not None

    flow.submit(db, t, "已更换绝缘子")
    assert t.status == "resolved"
    assert t.resolution == "已更换绝缘子"
    assert t.resolved_at is not None

    flow.review(db, t, approve=True, reviewer="李四")
    assert t.status == "closed"
    assert t.reviewer == "李四"
    assert t.closed_at is not None
    assert not flow.is_overdue(t)  # 已闭环不再判超时


def test_review_reject_and_reassign(db):
    """复核退回记录原因与次数，退回后可重新派单再闭环。"""
    line, tower, m = make_ctx(db)
    t = flow.make_ticket(m.id, 1, tower_id=tower.id, level="critical")
    db.add(t)
    db.commit()

    flow.assign(db, t, "张三")
    flow.submit(db, t, "初步处理")
    flow.review(db, t, approve=False, reviewer="李四", reason="消缺不彻底")
    assert t.status == "returned"
    assert t.return_reason == "消缺不彻底"
    assert t.return_count == 1

    # 退回后重新派单 -> 再提交 -> 复核通过
    flow.assign(db, t, "王五")
    assert t.status == "processing"
    assert t.assignee == "王五"
    flow.submit(db, t, "复检合格")
    flow.review(db, t, approve=True, reviewer="李四")
    assert t.status == "closed"
    assert t.return_count == 1  # 退回次数保留


def test_invalid_transitions(db):
    """非法流转一律拒绝。"""
    line, tower, m = make_ctx(db)
    t = flow.make_ticket(m.id, 1, tower_id=tower.id)
    db.add(t)
    db.commit()

    with pytest.raises(TicketFlowError):
        flow.submit(db, t)                       # open 不可直接提交
    with pytest.raises(TicketFlowError):
        flow.review(db, t, approve=True)         # open 不可复核
    with pytest.raises(TicketFlowError):
        flow.assign(db, t, "")                   # 处理人不能为空

    flow.assign(db, t, "张三")
    with pytest.raises(TicketFlowError):
        flow.assign(db, t, "李四")               # processing 不可重复派单
    flow.submit(db, t)
    with pytest.raises(TicketFlowError):
        flow.review(db, t, approve=False, reason="")   # 退回必须填原因
    flow.review(db, t, approve=True)
    with pytest.raises(TicketFlowError):
        flow.assign(db, t, "王五")               # closed 不可再派单


def test_sla_hours_by_level(db):
    """SLA 时限按等级：critical 24h / major 72h / minor 168h。"""
    line, tower, m = make_ctx(db)
    now = flow.utcnow()
    for i, (lv, h) in enumerate([("critical", 24), ("major", 72), ("minor", 168)], 1):
        t = flow.make_ticket(m.id, i, level=lv, now=now)
        assert flow.sla_hours(lv) == h
        assert t.due_at == now + timedelta(hours=h)


def test_overdue_flag(db):
    """超过 SLA 未闭环判超时；闭环后不再超时。"""
    line, tower, m = make_ctx(db)
    past = flow.utcnow() - timedelta(hours=30)
    t = flow.make_ticket(m.id, 1, tower_id=tower.id, level="critical", now=past)  # SLA 24h
    db.add(t)
    db.commit()
    assert flow.is_overdue(t) is True

    flow.assign(db, t, "张三")
    flow.submit(db, t)
    assert flow.is_overdue(t) is True            # 待复核仍未闭环，保持超时
    flow.review(db, t, approve=True)
    assert flow.is_overdue(t) is False           # 闭环后清除超时


def test_tower_risk_writeback(db):
    """工单流转回写杆塔风险：critical 未闭环→key，全部闭环→normal。"""
    line, tower, m = make_ctx(db)
    t = flow.make_ticket(m.id, 1, tower_id=tower.id, level="critical")
    db.add(t)
    db.commit()
    flow.sync_tower_risk(db, tower.id)
    db.commit()
    db.refresh(tower)
    assert tower.risk_hint == "key"

    flow.assign(db, t, "张三")
    flow.submit(db, t)
    db.commit()
    db.refresh(tower)
    assert tower.risk_hint == "key"              # 未闭环保持

    flow.review(db, t, approve=True)
    db.commit()
    db.refresh(tower)
    assert tower.risk_hint == "normal"           # 闭环后解除


def test_tower_risk_takes_highest_level(db):
    """多工单并存时杆塔风险取最高等级。"""
    line, tower, m = make_ctx(db)
    t1 = flow.make_ticket(m.id, 1, tower_id=tower.id, level="major")
    t2 = flow.make_ticket(m.id, 2, tower_id=tower.id, level="critical")
    db.add_all([t1, t2])
    db.commit()
    flow.sync_tower_risk(db, tower.id)
    db.commit()
    db.refresh(tower)
    assert tower.risk_hint == "key"

    # 关掉 critical，剩 major -> suspect
    flow.assign(db, t2, "张三")
    flow.submit(db, t2)
    flow.review(db, t2, approve=True)
    db.commit()
    db.refresh(tower)
    assert tower.risk_hint == "suspect"


def test_mission_and_line_stats(db):
    """任务工单状态分布与线路风险统计回写。"""
    line, tower, m = make_ctx(db)
    past = flow.utcnow() - timedelta(hours=30)
    t1 = flow.make_ticket(m.id, 1, tower_id=tower.id, level="critical", now=past)  # 超时
    t2 = flow.make_ticket(m.id, 2, tower_id=tower.id, level="minor")
    db.add_all([t1, t2])
    db.commit()
    flow.assign(db, t2, "张三")

    stats = flow.mission_ticket_stats(m)
    assert stats["open"] == 1
    assert stats["processing"] == 1
    assert stats["overdue"] == 1

    risk = flow.line_risk_stats(line)
    assert risk["open_defects"] == 2
    assert risk["overdue_defects"] == 1
    assert risk["risk_level"] == "key"           # 有 critical 未闭环

    # 全部闭环后统计清零、风险解除
    for t in (t1, t2):
        if t.status == "open":
            flow.assign(db, t, "张三")
        flow.submit(db, t)
        flow.review(db, t, approve=True)
    risk = flow.line_risk_stats(line)
    assert risk["open_defects"] == 0
    assert risk["risk_level"] == "normal"
