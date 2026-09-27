# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Line, Tower, Drone, BatteryPack, Mission, FlightRecord, InspectionImage, RepairTicket
from ..services.engine import InspectionPlanner, PlanningError
from ..services.tickets import (
    WorkflowError,
    is_overdue,
    new_ticket,
    assign as ticket_assign,
    submit as ticket_submit,
    review as ticket_review,
    refresh_stats,
)
from ..schemas import (
    LineOut,
    LineDetail,
    TowerOut,
    DroneOut,
    BatteryOut,
    MissionOut,
    MissionDetail,
    MissionCreate,
    ImageOut,
    TicketOut,
    TicketDetail,
    TicketEventOut,
    TicketAssignIn,
    TicketSubmitIn,
    TicketReviewIn,
    ExecuteRequest,
    DefectBatch,
    Message,
)

router = APIRouter(prefix="/api")


# ---------- 线路 ----------
@router.get("/lines", response_model=list)
def list_lines(db: Session = Depends(get_db)):
    lines = db.query(Line).order_by(Line.id).all()
    out = []
    for l in lines:
        d = LineOut.model_validate(l)
        d.tower_count = len(l.towers)
        out.append(d)
    return out


@router.get("/lines/{lid}", response_model=LineDetail)
def line_detail(lid: int, db: Session = Depends(get_db)):
    l = db.get(Line, lid)
    if not l:
        raise HTTPException(404, "线路不存在")
    d = LineDetail.model_validate(l)
    d.towers = [TowerOut.model_validate(t) for t in sorted(l.towers, key=lambda t: t.seq)]
    return d


# ---------- 机队 ----------
@router.get("/drones", response_model=list)
def list_drones(db: Session = Depends(get_db)):
    return [DroneOut.model_validate(d) for d in db.query(Drone).order_by(Drone.id).all()]


@router.get("/batteries", response_model=list)
def list_batteries(db: Session = Depends(get_db)):
    return [BatteryOut.model_validate(b) for b in db.query(BatteryPack).order_by(BatteryPack.id).all()]


# ---------- 任务 ----------
@router.get("/missions", response_model=list)
def list_missions(db: Session = Depends(get_db)):
    ms = db.query(Mission).order_by(Mission.id.desc()).all()
    out = []
    for m in ms:
        o = MissionOut.model_validate(m)
        o.line_code = m.line.code if m.line else None
        o.drone_code = m.drone.code if m.drone else None
        o.battery_code = m.battery.code if m.battery else None
        out.append(o)
    return out


@router.get("/missions/{mid}", response_model=MissionDetail)
def mission_detail(mid: int, db: Session = Depends(get_db)):
    m = db.get(Mission, mid)
    if not m:
        raise HTTPException(404, "任务不存在")
    o = MissionDetail.model_validate(m)
    o.line_code = m.line.code if m.line else None
    o.drone_code = m.drone.code if m.drone else None
    o.battery_code = m.battery.code if m.battery else None
    o.images_count = len(m.images)
    o.tickets_count = len(m.tickets)
    return o


@router.post("/missions", response_model=MissionDetail, status_code=201)
def create_mission(body: MissionCreate, db: Session = Depends(get_db)):
    line = db.get(Line, body.line_id)
    if not line:
        raise HTTPException(404, "线路不存在")
    planner = InspectionPlanner(db)
    try:
        plan = planner.plan_route(line, body.start_tower_id, body.end_tower_id)
        km = planner.route_distance_km(plan["route"])
    except PlanningError as e:
        raise HTTPException(400, str(e))

    # 用一块代表电池预估所需电比例
    any_batt = db.query(BatteryPack).first()
    if any_batt:
        est_pct = planner.estimate_battery(km, AnyDrone(), any_batt, body.return_km)["need_pct"]
    else:
        est_pct = round((km / 8.0) + 0.1, 3)

    # 机队分配（电量不足时仍建任务，交由执行阶段提示）
    drone = battery = None
    try:
        drone, battery, drain = planner.assign_fleet(None, est_pct, body.return_km)
    except PlanningError:
        drone = battery = None
        drain = est_pct

    m = Mission(
        code=body.code or f"MSN-{line.code}-{len(line.missions)+1:03d}",
        name=body.name,
        line_id=body.line_id,
        start_tower_id=body.start_tower_id,
        end_tower_id=body.end_tower_id,
        plan_km=round(km, 2),
        estimated_battery_pct=drain,
        assigned_drone_id=drone.id if drone else None,
        assigned_battery_id=battery.id if battery else None,
        priority=body.priority,
        status="planned",
        route=plan["route"],
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _ser_mission(m, db)


class AnyDrone:
    """占位无人机：estimate_battery 仅用到电池，不接触无人机字段。"""
    id = None


@router.post("/missions/{mid}/execute", response_model=MissionDetail)
def execute_mission(mid: int, body: ExecuteRequest, db: Session = Depends(get_db)):
    m = db.get(Mission, mid)
    if not m:
        raise HTTPException(404, "任务不存在")
    planner = InspectionPlanner(db)
    try:
        planner.execute_mission(m, weather_ok=body.weather_ok)
        db.commit()
        db.refresh(m)
    except PlanningError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _ser_mission(m, db)


@router.post("/missions/{mid}/defects", response_model=MissionDetail)
def add_defects(mid: int, body: DefectBatch, db: Session = Depends(get_db)):
    m = db.get(Mission, mid)
    if not m:
        raise HTTPException(404, "任务不存在")
    for i, d in enumerate(body.defects, 1):
        new_ticket(
            db,
            mission_id=mid,
            code=f"WO-{mid}-{i:02d}",
            tower_id=d.tower_id,
            title=d.title,
            level=d.level,
            detail=d.detail,
            actor="人工补录",
        )
    db.flush()
    for t in m.tickets:
        refresh_stats(db, t)
    db.commit()
    db.refresh(m)
    return _ser_mission(m, db)


@router.delete("/missions/{mid}", response_model=Message)
def delete_mission(mid: int, db: Session = Depends(get_db)):
    m = db.get(Mission, mid)
    if not m:
        raise HTTPException(404, "任务不存在")
    db.delete(m)
    db.commit()
    return Message(detail="已删除")


# ---------- 影像 & 工单 ----------
@router.get("/missions/{mid}/images", response_model=list)
def mission_images(mid: int, db: Session = Depends(get_db)):
    imgs = db.query(InspectionImage).filter(InspectionImage.mission_id == mid).order_by(InspectionImage.id).all()
    return [ImageOut.model_validate(i) for i in imgs]


@router.get("/missions/{mid}/tickets", response_model=list)
def mission_tickets(mid: int, db: Session = Depends(get_db)):
    ts = db.query(RepairTicket).filter(RepairTicket.mission_id == mid).order_by(RepairTicket.level.desc(), RepairTicket.id).all()
    return [_ser_ticket(t) for t in ts]


@router.get("/tickets", response_model=list)
def all_tickets(db: Session = Depends(get_db)):
    ts = db.query(RepairTicket).order_by(RepairTicket.level.desc(), RepairTicket.id).all()
    return [_ser_ticket(t) for t in ts]


@router.get("/tickets/{tid}", response_model=TicketDetail)
def ticket_detail(tid: int, db: Session = Depends(get_db)):
    t = db.get(RepairTicket, tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    o = _ser_ticket(t, detail=True)
    o.events = [TicketEventOut.model_validate(e) for e in t.events]
    return o


@router.post("/tickets/{tid}/assign", response_model=TicketOut)
def assign_ticket(tid: int, body: TicketAssignIn, db: Session = Depends(get_db)):
    """派单/改派：指定处理人并启动（或重计）处理时限。"""
    t = db.get(RepairTicket, tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    try:
        ticket_assign(db, t, body.assignee, body.due_hours, body.actor)
        refresh_stats(db, t)
        db.commit()
    except WorkflowError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.refresh(t)
    return _ser_ticket(t)


@router.post("/tickets/{tid}/submit", response_model=TicketOut)
def submit_ticket(tid: int, body: TicketSubmitIn, db: Session = Depends(get_db)):
    """提交处理结果：处理中 → 待复核。"""
    t = db.get(RepairTicket, tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    try:
        ticket_submit(db, t, body.note, body.actor)
        refresh_stats(db, t)
        db.commit()
    except WorkflowError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.refresh(t)
    return _ser_ticket(t)


@router.post("/tickets/{tid}/review", response_model=TicketOut)
def review_ticket(tid: int, body: TicketReviewIn, db: Session = Depends(get_db)):
    """复核：通过则关闭；退回则回到处理中并记录原因。"""
    t = db.get(RepairTicket, tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    try:
        ticket_review(db, t, body.reviewer, body.approve, body.reason)
        refresh_stats(db, t)
        db.commit()
    except WorkflowError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.refresh(t)
    return _ser_ticket(t)


# ---------- 飞行记录 ----------
@router.get("/flights")
def flights(db: Session = Depends(get_db)):
    fs = db.query(FlightRecord).order_by(FlightRecord.id.desc()).all()
    return [
        {
            "id": f.id,
            "mission_id": f.mission_id,
            "drone_id": f.drone_id,
            "flight_km": f.flight_km,
            "soc_start": f.soc_start,
            "soc_end": f.soc_end,
            "weather_ok": f.weather_ok,
            "cleared_by": f.cleared_by,
            "record_time": f.record_time.isoformat() if f.record_time else None,
        }
        for f in fs
    ]


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    lines = db.query(Line).count()
    towers = db.query(Tower).count()
    drones = db.query(Drone).count()
    missions = db.query(Mission).count()
    completed = db.query(Mission).filter(Mission.status == "completed").count()
    planned = db.query(Mission).filter(Mission.status == "planned").count()
    tickets = db.query(RepairTicket).all()
    open_tickets = sum(1 for t in tickets if t.status == "open")
    processing = sum(1 for t in tickets if t.status == "processing")
    resolved = sum(1 for t in tickets if t.status == "resolved")
    overdue = sum(1 for t in tickets if is_overdue(t))
    critical = sum(1 for t in tickets if t.level == "critical" and t.status != "closed")
    total_flight = db.query(FlightRecord).count()
    line_risks = [
        {
            "id": l.id,
            "code": l.code,
            "name": l.name,
            "risk_level": l.risk_level,
            "open_ticket_count": l.open_ticket_count,
            "overdue": sum(1 for m in l.missions for t in m.tickets if is_overdue(t)),
        }
        for l in db.query(Line).order_by(Line.id).all()
    ]
    return {
        "lines": lines, "towers": towers, "drones": drones,
        "missions": missions, "completed": completed, "planned": planned,
        "open_tickets": open_tickets, "processing": processing,
        "resolved": resolved, "overdue": overdue,
        "critical": critical, "flights": total_flight,
        "line_risks": line_risks,
    }


def _ser_mission(m, db):
    o = MissionDetail.model_validate(m)
    o.line_code = m.line.code if m.line else None
    o.drone_code = m.drone.code if m.drone else None
    o.battery_code = m.battery.code if m.battery else None
    o.images_count = len(m.images)
    o.tickets_count = len(m.tickets)
    o.overdue_ticket_count = sum(1 for t in m.tickets if is_overdue(t))
    return o


def _ser_ticket(t, detail=False):
    cls = TicketDetail if detail else TicketOut
    o = cls.model_validate(t)
    o.mission_code = t.mission.code if t.mission else None
    o.overdue = is_overdue(t)
    return o