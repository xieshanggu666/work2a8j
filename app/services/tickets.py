# -*- coding: utf-8 -*-
"""缺陷工单闭环状态流。

状态机：
    open ──派单──> processing ──提交处理──> resolved ──复核通过──> closed
                     ▲   │                        │
                     │     └──────── 复核退回 ─────────┘
                     └────────── 退回后重新计时 ──────┘

配套能力：
  - 处理时限（SLA）：按缺陷等级给定时限，超时工单动态判定；
  - 流转事件：每次状态变化写入 TicketEvent，可回溯；
  - 风险回写：状态变化后重算所属任务的未闭环工单数与线路风险等级。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Line, Mission, RepairTicket, TicketEvent

# 各等级缺陷的处理时限（小时）：重大 24h / 较大 72h / 轻微 7 天
SLA_HOURS = {"critical": 24, "major": 72, "minor": 168}
DEFAULT_SLA_HOURS = 168

# 未闭环状态（参与任务/线路统计）
OPEN_STATUSES = ("open", "processing", "resolved")


class WorkflowError(Exception):
    """非法状态流转。"""


def utcnow():
    return datetime.utcnow()


def sla_hours(level: str) -> int:
    return SLA_HOURS.get(level, DEFAULT_SLA_HOURS)


def is_overdue(ticket: RepairTicket, now: datetime = None) -> bool:
    """超时判定：未闭环且已越过处理时限。"""
    if ticket.status == "closed" or ticket.due_at is None:
        return False
    return ticket.due_at < (now or utcnow())


# ---------- 状态流转 ----------
def new_ticket(db: Session, mission_id: int, code: str, title: str,
               level: str = "minor", detail: str = "", tower_id=None,
               actor: str = "系统") -> RepairTicket:
    """创建工单：按等级写入处理时限，并记录创建事件。"""
    t = RepairTicket(
        code=code, mission_id=mission_id, tower_id=tower_id,
        title=title, level=level, status="open", detail=detail,
        due_at=utcnow() + timedelta(hours=sla_hours(level)),
    )
    db.add(t)
    db.flush()
    _log(db, t, "create", actor, f"工单创建，时限 {sla_hours(level)} 小时")
    return t


def assign(db: Session, t: RepairTicket, assignee: str,
           due_hours: float = None, actor: str = None) -> RepairTicket:
    """派单/改派：open→processing（处理中可改派，重计时限）。"""
    if t.status not in ("open", "processing"):
        raise WorkflowError("仅待处理/处理中的工单可派单")
    assignee = (assignee or "").strip()
    if not assignee:
        raise WorkflowError("处理人不能为空")
    hours = due_hours if due_hours and due_hours > 0 else sla_hours(t.level)
    t.assignee = assignee
    t.assigned_at = utcnow()
    t.due_at = t.assigned_at + timedelta(hours=hours)
    t.status = "processing"
    _log(db, t, "assign", actor or assignee,
         f"派单给 {assignee}，时限 {hours:g} 小时")
    return t


def submit(db: Session, t: RepairTicket, note: str = "",
           actor: str = None) -> RepairTicket:
    """提交处理结果：processing→resolved（待复核）。"""
    if t.status != "processing":
        raise WorkflowError("仅处理中的工单可提交处理")
    t.status = "resolved"
    t.resolved_at = utcnow()
    t.resolve_note = (note or "").strip()
    _log(db, t, "submit", actor or t.assignee or "系统",
         t.resolve_note or "处理完成，提交复核")
    return t


def review(db: Session, t: RepairTicket, reviewer: str, approve: bool,
           reason: str = "") -> RepairTicket:
    """复核：通过→closed；退回→processing（退回次数+1，重计时限）。"""
    if t.status != "resolved":
        raise WorkflowError("仅待复核的工单可复核")
    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise WorkflowError("复核人不能为空")
    t.reviewer = reviewer
    t.reviewed_at = utcnow()
    if approve:
        t.status = "closed"
        t.closed_at = t.reviewed_at
        _log(db, t, "approve", reviewer, "复核通过，工单关闭")
    else:
        reason = (reason or "").strip()
        if not reason:
            raise WorkflowError("复核退回必须填写退回原因")
        t.status = "processing"
        t.reject_count += 1
        t.reject_reason = reason
        # 退回后按等级重新计时，给处理人新的处理窗口
        t.due_at = t.reviewed_at + timedelta(hours=sla_hours(t.level))
        _log(db, t, "reject", reviewer, f"复核退回：{reason}")
    return t


# ---------- 风险统计回写 ----------
def refresh_mission_stats(db: Session, mission: Mission) -> None:
    """回写任务：未闭环工单数。"""
    mission.open_ticket_count = sum(
        1 for t in mission.tickets if t.status in OPEN_STATUSES)


def refresh_line_stats(db: Session, line: Line) -> None:
    """回写线路：未闭环工单数与风险等级。

    风险等级：存在未闭环重大缺陷→key；存在未闭环较大缺陷→suspect；否则 normal。
    """
    open_tickets = [t for m in line.missions for t in m.tickets
                    if t.status in OPEN_STATUSES]
    line.open_ticket_count = len(open_tickets)
    levels = {t.level for t in open_tickets}
    if "critical" in levels:
        line.risk_level = "key"
    elif "major" in levels:
        line.risk_level = "suspect"
    else:
        line.risk_level = "normal"


def refresh_stats(db: Session, ticket: RepairTicket) -> None:
    """工单状态变化后，回写其任务与线路的统计。"""
    mission = ticket.mission or db.get(Mission, ticket.mission_id)
    if mission is None:
        return
    refresh_mission_stats(db, mission)
    if mission.line is not None:
        refresh_line_stats(db, mission.line)


def refresh_all_stats(db: Session) -> None:
    """全量重算（迁移/修复用）。"""
    for m in db.query(Mission).all():
        refresh_mission_stats(db, m)
    for line in db.query(Line).all():
        refresh_line_stats(db, line)


def _log(db: Session, t: RepairTicket, action: str, actor: str, note: str) -> None:
    db.add(TicketEvent(ticket_id=t.id, action=action,
                       actor=actor or "系统", note=note))
