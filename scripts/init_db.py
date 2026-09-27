# -*- coding: utf-8 -*-
"""初始化数据库：建表 + 演示数据（线路/杆塔/机队/电池）。幂等。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base, engine, SessionLocal
from app.models import Line, Tower, Drone, BatteryPack


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Line).first():
            print("已有线路数据，跳过演示数据。")
            return

        # 线路 A：110kV 环城一线，10 基杆塔，约 12km
        la = Line(code="L-110-01", name="110kV 环城一线", voltage_kv=110, total_km=12.0, status="in_service")
        db.add(la)
        db.flush()
        lat0, lng0 = 30.5700, 104.0600
        for i in range(1, 11):
            db.add(Tower(
                line_id=la.id, seq=i, code=f"T-{i:03d}",
                lat=round(lat0 + 0.012 * (i - 1), 5),
                lng=round(lng0 + 0.008 * (i - 1), 5),
                cum_km=round(1.2 * (i - 1), 2),
                risk_hint="normal" if i not in (3, 8) else ("suspect" if i == 3 else "key"),
            ))

        # 线路 B：220kV 滨江双回，8 基杆塔，约 10km
        lb = Line(code="L-220-02", name="220kV 滨江双回", voltage_kv=220, total_km=10.0, status="in_service")
        db.add(lb)
        db.flush()
        lat1, lng1 = 30.6200, 104.0800
        for i in range(1, 9):
            db.add(Tower(
                line_id=lb.id, seq=i, code=f"B-{i:03d}",
                lat=round(lat1 + 0.010 * (i - 1), 5),
                lng=round(lng1 + 0.010 * (i - 1), 5),
                cum_km=round(1.4 * (i - 1), 2),
                risk_hint="normal",
            ))

        # 机队
        db.add_all([
            Drone(code="UAV-001", model="大疆 M300RTK", battery_capacity=0.0, battery_soc=1.0, status="idle", max_payload=2.7),
            Drone(code="UAV-002", model="大疆 M30T", battery_capacity=0.0, battery_soc=1.0, status="idle", max_payload=0.6),
            Drone(code="UAV-003", model="纵横 CW-15", battery_capacity=0.0, battery_soc=0.8, status="idle", max_payload=3.0),
        ])

        # 电池包（续航按不同机型）
        db.add_all([
            BatteryPack(code="BAT-001", capacity_km=8.0, soc=1.0, cycle_count=3, status="ready"),
            BatteryPack(code="BAT-002", capacity_km=8.0, soc=0.92, cycle_count=7, status="ready"),
            BatteryPack(code="BAT-003", capacity_km=10.0, soc=0.66, cycle_count=12, status="ready"),
            BatteryPack(code="BAT-004", capacity_km=5.0, soc=0.5, cycle_count=20, status="ready"),
        ])

        db.commit()
        print("演示数据创建完成。启动：uvicorn app.main:app --reload")
    finally:
        db.close()


if __name__ == "__main__":
    main()