# -*- coding: utf-8 -*-
"""无人机巡检规划引擎测试。"""
import pytest
from sqlalchemy.orm import Session

from app.core.database import Base, engine, SessionLocal
from app.models import Line, Tower, Drone, BatteryPack, Mission
from app.services.engine import InspectionPlanner, PlanningError, SAFE_SOC


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()
    Base.metadata.drop_all(bind=engine)


def make_line(db, tower_count=6, target_total_km=6.0):
    line = Line(code="L-T", name="测试线路", voltage_kv=110, total_km=target_total_km, status="in_service")
    db.add(line)
    db.flush()
    for i in range(1, tower_count + 1):
        db.add(Tower(
            line_id=line.id, seq=i, code=f"T-{i:03d}",
            lat=30.5 + 0.01 * (i - 1), lng=104.0 + 0.005 * (i - 1),
            cum_km=round((target_total_km / (tower_count - 1)) * (i - 1), 2),
            risk_hint="normal",
        ))
    db.commit()
    db.refresh(line)
    return line


def make_fleet(db):
    d = Drone(code="UAV-T", model="M300", battery_capacity=0, battery_soc=1.0, status="idle", max_payload=2.7)
    b = BatteryPack(code="BAT-T", capacity_km=8.0, soc=1.0, cycle_count=0, status="ready")
    b2 = BatteryPack(code="BAT-T2", capacity_km=8.0, soc=0.5, cycle_count=1, status="ready")
    db.add_all([d, b, b2])
    db.commit()
    return d, b, b2


def towers(line):
    return sorted(line.towers, key=lambda t: t.seq)


def test_plan_route_full(db):
    line = make_line(db)
    ts = towers(line)
    p = InspectionPlanner(db)
    plan = p.plan_route(line, ts[0].id, ts[-1].id)
    assert len(plan["route"]) == len(ts)
    assert plan["skipped"] == 0


def test_plan_route_reversed_order(db):
    line = make_line(db)
    ts = towers(line)
    p = InspectionPlanner(db)
    plan = p.plan_route(line, ts[-1].id, ts[0].id)  # 反向区间
    assert len(plan["route"]) == len(ts)


def test_plan_route_skips_obstacle(db):
    line = make_line(db)
    ts = towers(line)
    p = InspectionPlanner(db)
    plan = p.plan_route(line, ts[0].id, ts[-1].id, obstacles=[ts[2].id])
    assert plan["skipped"] == 1
    assert ts[2].id not in [r["id"] for r in plan["route"]]


def test_plan_route_all_blocked_raises(db):
    line = make_line(db)
    ts = towers(line)
    p = InspectionPlanner(db)
    with pytest.raises(PlanningError):
        p.plan_route(line, ts[0].id, ts[-1].id, obstacles=[t.id for t in ts])


def test_route_distance(db):
    line = make_line(db, target_total_km=6.0)
    ts = towers(line)
    p = InspectionPlanner(db)
    plan = p.plan_route(line, ts[0].id, ts[-1].id)
    dist = p.route_distance_km(plan["route"])
    assert dist == pytest.approx(6.0, abs=1e-2)


def test_estimate_battery_feasible(db):
    line = make_line(db)
    d, b, b2 = make_fleet(db)
    p = InspectionPlanner(db)
    est = p.estimate_battery(6.0, d, b, 0.0)
    # need = 6/8 = 0.75, safe = 0.95, soc 1.0 >= 0.95 => feasible
    assert est["feasible"] is True
    assert est["need_pct"] == pytest.approx(0.75, abs=0.01)


def test_estimate_battery_infeasible(db):
    d, b, b2 = make_fleet(db)
    p = InspectionPlanner(db)
    est = p.estimate_battery(6.0, d, b2, 0.0)  # b2 soc 0.5 < 0.95
    assert est["feasible"] is False


def test_assign_fleet_prefers_low_reserve(db):
    line = make_line(db)
    d, b, b2 = make_fleet(db)
    p = InspectionPlanner(db)
    # b(1.0) 与 b2(0.5)，need 0.3：both feasible，应选 reserve 更小的 b2
    drone, bat, drain = p.assign_fleet(None, 0.3, 0.0)
    assert bat.id == b2.id
    assert drain == pytest.approx(0.3 + SAFE_SOC, abs=0.01)


def test_assign_fleet_insufficient(db):
    d, b, b2 = make_fleet(db)
    # 让两块电池都极低
    b.soc = 0.1
    b2.soc = 0.1
    p = InspectionPlanner(db)
    with pytest.raises(PlanningError):
        p.assign_fleet(None, 0.8, 0.0)


def test_execute_mission_drains_battery_and_creates_data(db):
    line = make_line(db)
    ts = towers(line)
    d, b, b2 = make_fleet(db)
    p = InspectionPlanner(db)
    plan = p.plan_route(line, ts[0].id, ts[-1].id)
    km = p.route_distance_km(plan["route"])
    drone, bat, drain = p.assign_fleet(None, 0.4, 0.0)

    m = Mission(
        code="MSN-T-001", name="测试任务", line_id=line.id,
        start_tower_id=ts[0].id, end_tower_id=ts[-1].id,
        plan_km=round(km, 2), estimated_battery_pct=drain,
        assigned_drone_id=drone.id, assigned_battery_id=bat.id,
        priority="normal", status="planned", route=plan["route"],
    )
    db.add(m)
    db.commit()
    db.refresh(m)

    soc_before = bat.soc
    result = p.execute_mission(m, weather_ok=True)
    db.commit()
    db.refresh(bat)
    assert m.status == "completed"
    assert bat.soc < soc_before
    assert result["images"] >= 2
    assert m.images


def test_execute_mission_requires_assignment(db):
    line = make_line(db)
    ts = towers(line)
    make_fleet(db)
    m = Mission(
        code="MSN-T-002", name="未分配任务", line_id=line.id,
        start_tower_id=ts[0].id, end_tower_id=ts[-1].id,
        plan_km=1.0, estimated_battery_pct=0.3,
        assigned_drone_id=None, assigned_battery_id=None,
        priority="normal", status="planned",
    )
    db.add(m)
    db.commit()
    p = InspectionPlanner(db)
    with pytest.raises(PlanningError):
        p.execute_mission(m)