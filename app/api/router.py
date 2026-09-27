# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Line, Tower, Drone, BatteryPack, Mission, FlightRecord, InspectionImage, RepairTicket
from ..services.engine import InspectionPlanner, PlanningError
from ..services import ticket_flow
from ..services.ticket_flow import TicketFlowError
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
    TicketAssign,
    TicketSubmit,
    TicketReview,
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
        # 回写线路风险统计（未闭环/超时缺陷、综合风险等级）
        for k, v in ticket_flow.line_risk_stats(l).items():
            setattr(d, k, v)
        out.append(d)
    return out


@router.get("/lines/{lid}", response_model=LineDetail)
def line_detail(lid: int, db: Session = Depends(get_db)):
    l = db.get(Line, lid)
    if not l:
        raise HTTPException(404, "线路不存在")
    d = LineDetail.model_validate(l)
    d.towers = [TowerOut.model_validate(t) for t in sorted(l.towers, key=lambda t: t.seq)]
    for k, v in ticket_flow.line_risk_stats(l).items():
        setattr(d, k, v)
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
    return _ser_mission(m, db)


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
        t = ticket_flow.make_ticket(
            mission_id=mid, seq=i, tower_id=d.tower_id,
            title=d.title, level=d.level, detail=d.detail,
        )
        db.add(t)
        db.flush()
        if t.tower_id:
            ticket_flow.sync_tower_risk(db, t.tower_id)
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


@router.post("/tickets/{tid}/assign", response_model=TicketOut)
def assign_ticket(tid: int, body: TicketAssign, db: Session = Depends(get_db)):
    """派单：open/returned -> processing，指定处理人。"""
    t = db.get(RepairTicket, tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    try:
        ticket_flow.assign(db, t, body.assignee)
        db.commit()
    except TicketFlowError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.refresh(t)
    return _ser_ticket(t)


@router.post("/tickets/{tid}/submit", response_model=TicketOut)
def submit_ticket(tid: int, body: TicketSubmit, db: Session = Depends(get_db)):
    """提交处理结果：processing -> resolved（待复核）。"""
    t = db.get(RepairTicket, tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    try:
        ticket_flow.submit(db, t, body.resolution)
        db.commit()
    except TicketFlowError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.refresh(t)
    return _ser_ticket(t)


@router.post("/tickets/{tid}/review", response_model=TicketOut)
def review_ticket(tid: int, body: TicketReview, db: Session = Depends(get_db)):
    """复核：resolved -> closed（通过）或 returned（退回，须填原因）。"""
    t = db.get(RepairTicket, tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    try:
        ticket_flow.review(db, t, body.approve, body.reviewer, body.reason)
        db.commit()
    except TicketFlowError as e:
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
    open_cnt = sum(1 for t in tickets if t.status in ticket_flow.OPEN_STATES)
    processing = sum(1 for t in tickets if t.status == "processing")
    pending_review = sum(1 for t in tickets if t.status == "resolved")
    returned = sum(1 for t in tickets if t.status == "returned")
    overdue = sum(1 for t in tickets if ticket_flow.is_overdue(t))
    critical = sum(1 for t in tickets if t.level == "critical" and t.status != "closed")
    total_flight = db.query(FlightRecord).count()
    return {
        "lines": lines, "towers": towers, "drones": drones,
        "missions": missions, "completed": completed, "planned": planned,
        "open_tickets": open_cnt, "processing_tickets": processing,
        "pending_review": pending_review, "returned_tickets": returned,
        "overdue_tickets": overdue, "critical": critical, "flights": total_flight,
    }


def _ser_mission(m, db):
    o = MissionDetail.model_validate(m)
    o.line_code = m.line.code if m.line else None
    o.drone_code = m.drone.code if m.drone else None
    o.battery_code = m.battery.code if m.battery else None
    o.images_count = len(m.images)
    o.tickets_count = len(m.tickets)
    o.ticket_stats = ticket_flow.mission_ticket_stats(m)
    return o


def _ser_ticket(t):
    o = TicketOut.model_validate(t)
    o.sla_hours = ticket_flow.sla_hours(t.level)
    o.overdue = ticket_flow.is_overdue(t)
    return o