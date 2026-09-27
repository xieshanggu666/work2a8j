# -*- coding: utf-8 -*-
"""缺陷工单闭环状态流与风险统计回写。

状态机：
    open       待处理 ──派单(处理人)──▶ processing 处理中
    processing 处理中 ──提交处理结果──▶ resolved   待复核
    resolved   待复核 ──复核通过──────▶ closed     已关闭
    resolved   待复核 ──复核退回──────▶ returned   已退回
    returned   已退回 ──重新派单──────▶ processing 处理中

超时：建单时按缺陷等级写入 due_at（SLA 时限），逾期未闭环即判定超时。
每次流转后回写杆塔风险标识，并向任务/线路汇总统计。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..core.config import TICKET_SLA_HOURS
from ..models import RepairTicket, Tower

# 未闭环状态集合
OPEN_STATES = ("open", "processing", "resolved", "returned")
# 缺陷等级 -> 杆塔风险标识
_LEVEL_RISK = {"critical": "key", "major": "suspect", "minor": "normal"}


class TicketFlowError(Exception):
    """工单状态流转非法。"""


def utcnow():
    """与 SQLite server_default(func.now()) 一致的 UTC 时间。"""
    return datetime.utcnow()


def sla_hours(level: str) -> int:
    return TICKET_SLA_HOURS.get(level, TICKET_SLA_HOURS["minor"])


def make_ticket(mission_id: int, seq: int, tower_id=None, title="巡检缺陷",
                level="minor", detail="", now=None) -> RepairTicket:
    """按等级 SLA 创建工单（open，含闭环时限）。"""
    now = now or utcnow()
    return RepairTicket(
        code=f"WO-{mission_id}-{seq:02d}",
        mission_id=mission_id,
        tower_id=tower_id,
        title=title,
        level=level,
        status="open",
        detail=detail,
        due_at=now + timedelta(hours=sla_hours(level)),
    )


def is_overdue(t: RepairTicket, now=None) -> bool:
    """未在 SLA 时限内闭环即为超时。"""
    if t.status == "closed" or t.due_at is None:
        return False
    return (now or utcnow()) > t.due_at


# ---------- 状态流转 ----------
def assign(db: Session, t: RepairTicket, assignee: str, now=None):
    """派单/认领：open|returned -> processing，记录处理人。"""
    if t.status not in ("open", "returned"):
        raise TicketFlowError(f"当前状态（{t.status}）不可派单")
    assignee = (assignee or "").strip()
    if not assignee:
        raise TicketFlowError("处理人不能为空")
    t.assignee = assignee
    t.assigned_at = now or utcnow()
    t.status = "processing"
    _after_change(db, t)


def submit(db: Session, t: RepairTicket, resolution: str = "", now=None):
    """提交处理结果：processing -> resolved（待复核）。"""
    if t.status != "processing":
        raise TicketFlowError("仅处理中的工单可提交复核")
    t.resolution = (resolution or "").strip()
    t.resolved_at = now or utcnow()
    t.status = "resolved"
    _after_change(db, t)


def review(db: Session, t: RepairTicket, approve: bool, reviewer: str = "",
           reason: str = "", now=None):
    """复核：resolved -> closed（通过）或 returned（退回，须填原因）。"""
    if t.status != "resolved":
        raise TicketFlowError("仅待复核的工单可复核")
    t.reviewer = (reviewer or "").strip() or None
    if approve:
        t.status = "closed"
        t.closed_at = now or utcnow()
        t.return_reason = ""
    else:
        reason = (reason or "").strip()
        if not reason:
            raise TicketFlowError("退回必须填写退回原因")
        t.status = "returned"
        t.return_reason = reason
        t.return_count = (t.return_count or 0) + 1
    _after_change(db, t)


# ---------- 风险统计回写 ----------
def _after_change(db: Session, t: RepairTicket):
    """流转后回写杆塔风险标识。"""
    if t.tower_id:
        sync_tower_risk(db, t.tower_id)


def sync_tower_risk(db: Session, tower_id: int):
    """按该塔未闭环工单的最高等级回写 risk_hint：critical→key / major→suspect / 无→normal。"""
    tower = db.get(Tower, tower_id)
    if tower is None:
        return
    db.flush()  # 会话关闭了 autoflush，先落盘本次流转再统计
    open_tickets = (db.query(RepairTicket)
                    .filter(RepairTicket.tower_id == tower_id,
                            RepairTicket.status.in_(OPEN_STATES))
                    .all())
    risk = "normal"
    for tk in open_tickets:
        r = _LEVEL_RISK.get(tk.level, "normal")
        if r == "key":
            risk = "key"
            break
        if r == "suspect":
            risk = "suspect"
    tower.risk_hint = risk


def mission_ticket_stats(mission, now=None) -> dict:
    """任务维度的工单状态分布（含超时数），用于任务详情回写。"""
    stats = {"open": 0, "processing": 0, "resolved": 0,
             "returned": 0, "closed": 0, "overdue": 0}
    for t in mission.tickets:
        stats[t.status] = stats.get(t.status, 0) + 1
        if is_overdue(t, now):
            stats["overdue"] += 1
    return stats


def line_risk_stats(line, now=None) -> dict:
    """线路维度的风险统计：未闭环缺陷数、超时数、综合风险等级。"""
    open_cnt = overdue_cnt = 0
    risk = "normal"
    for m in line.missions:
        for t in m.tickets:
            if t.status in OPEN_STATES:
                open_cnt += 1
                r = _LEVEL_RISK.get(t.level, "normal")
                if r == "key":
                    risk = "key"
                elif r == "suspect" and risk != "key":
                    risk = "suspect"
                if is_overdue(t, now):
                    overdue_cnt += 1
    return {"open_defects": open_cnt, "overdue_defects": overdue_cnt,
            "risk_level": risk}
