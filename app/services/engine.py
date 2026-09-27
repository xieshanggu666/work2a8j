# -*- coding: utf-8 -*-
"""无人机电力巡检规划引擎。

核心能力：
  1. 航线规划：沿线路杆塔序列生成航线点，支持规避禁飞区（障碍）重排。
  2. 电量核算：根据航线总长 + 返航距离 + 安全阈值，计算所需用电比例与是否可飞。
  3. 机队调度：从可用机队/电池包中选出满足续航余量最长者，利用贪心策略分配。
  4. 任务闭环：完成任务时消耗电量、生成影像与缺陷工单。
"""

from sqlalchemy.orm import Session

from ..models import (
    Line,
    Tower,
    Drone,
    BatteryPack,
    Mission,
    InspectionImage,
    RepairTicket,
    FlightRecord,
)
from ..core.config import SAFE_SOC

AVG_SPEED_KPH = 36.0


class PlanningError(Exception):
    pass


class InspectionPlanner:
    def __init__(self, db: Session):
        self.db = db

    # ---------- 航线规划 ----------
    def plan_route(self, line: Line, start_tower_id: int, end_tower_id: int,
                   obstacles=None):
        """沿线路方向生成从 start_tower 到 end_tower 的航线点序列。

        obstacles: 禁止巡检的杆塔 id 集合（如施工、禁飞），规划时跳过并在其邻近重排。
        """
        towers = [t for t in line.towers]
        towers.sort(key=lambda t: t.seq)
        ids = [t.id for t in towers]
        if start_tower_id not in ids or end_tower_id not in ids:
            raise PlanningError("杆塔区间不在当前线路内")
        si = ids.index(start_tower_id)
        ei = ids.index(end_tower_id)
        if si > ei:
            si, ei = ei, si
        obst = set(obstacles or [])

        route = []
        skipped = 0
        for idx in range(si, ei + 1):
            t = towers[idx]
            if t.id in obst:
                skipped += 1
                continue  # 跳过禁飞塔，航线在其间直线过渡
            route.append({"seq": t.seq, "id": t.id, "code": t.code,
                          "lat": t.lat, "lng": t.lng, "cum_km": t.cum_km})
        if not route:
            raise PlanningError("区间内全部为禁飞杆塔，无法规划")
        # 若因跳点导致上一塔到下一塔距离过长，插入补点（简化：记录 skipped 供调度提示）
        return {"route": route, "tower_count": len(route), "skipped": skipped}

    @staticmethod
    def route_distance_km(route):
        """根据航线点累计里程差求总长（取末点到起点累计里程差）。"""
        if len(route) < 2:
            return 0.0
        km = route[-1]["cum_km"] - route[0]["cum_km"]
        return max(0.0, km)

    # ---------- 电量核算 ----------
    def estimate_battery(self, line_km: float, drone: Drone, battery: BatteryPack,
                         return_to_base_km: float = 0.0):
        """核算单程巡检 + 返航所需电池比例。

        逻辑：总里程 = 航线里程 + 返航里程(默认基地在端外，取给定值)。
        所需电比例 = (航线 + 返航) / 电池续航；必须至少留 SAFE_SOC 安全余量。
        """
        capacity = battery.capacity_km
        if capacity <= 0:
            raise PlanningError("电池续航异常")
        total = line_km + return_to_base_km
        need = total / capacity
        # 电池当前电量需 >= need + SAFE_SOC 才可飞
        safe_drain = need + SAFE_SOC
        feasible = battery.soc >= safe_drain
        return {
            "need_pct": round(need, 3),
            "safe_pct": round(safe_drain, 3),
            "feasible": feasible,
            "total_km": round(total, 2),
        }

    # ---------- 机队调度 ----------
    def assign_fleet(self, mission: Mission, need_pct: float, return_km: float = 0.0):
        """贪心分配：在满足安全余量的机队中，选出最合适（电能余量最小但足够）
        的无人机 + 电池组合，把高电量电池留给更远任务。

        返回 (drone, battery, drain_pct)；无可飞则 raise PlanningError。
        """
        drones = [d for d in self.db.query(Drone).all() if d.status == "idle"]
        batteries = [b for b in self.db.query(BatteryPack).all()
                     if b.status not in ("use", "depleted")]

        need = need_pct + SAFE_SOC
        best = None
        for d in drones:
            for b in batteries:
                if b.soc < need:
                    continue
                reserve = round(b.soc - need, 3)
                if best is None or reserve < best[0]:
                    best = (reserve, d, b)
        if best is None:
            raise PlanningError("当前机队/电池电量不足，无法执行该任务")
        reserve, drone, battery = best
        drain = need
        return drone, battery, drain

    # ---------- 任务执行/闭环 ----------
    def execute_mission(self, mission: Mission, weather_ok: bool = True,
                        defects=None):
        """执行任务：扣除电量、写飞行记录、生成影像、按缺陷生成工单。"""
        if mission.status != "planned":
            raise PlanningError("任务非待执行状态")
        drone = mission.drone
        battery = mission.battery
        if drone is None or battery is None:
            raise PlanningError("任务未分配机队")

        # 结算电量
        drain = mission.estimated_battery_pct
        battery.soc = round(max(0.0, battery.soc - drain), 3)
        battery.cycle_count += 1
        if battery.soc < 0.1:
            battery.status = "charging"
        drone.battery_soc = battery.soc
        drone.status = "idle"

        # 飞行合规记录
        self.db.add(FlightRecord(
            mission_id=mission.id,
            drone_id=drone.id,
            flight_km=mission.plan_km,
            soc_start=round(battery.soc + drain, 3),
            soc_end=battery.soc,
            weather_ok=1 if weather_ok else 0,
            cleared_by="民航监管自动放行",
        ))

        # 影像（沿航线每座塔一拍）
        for wp in (mission.route or []):
            self.db.add(InspectionImage(
                mission_id=mission.id,
                tower_id=wp.get("id"),
                filename=f"{mission.code}_{wp.get('code','T')}.jpg",
                defect_type=None,
                confidence=None,
                defect_level=None,
                labeled=0,
            ))

        # 缺陷工单（简化演示：传入缺陷集合）
        for def_ in (defects or []):
            self.db.add(RepairTicket(
                code=f"WO-{mission.id}-{def_.get('seq', 1):02d}",
                mission_id=mission.id,
                tower_id=def_.get("tower_id"),
                title=def_.get("title", "巡检缺陷"),
                level=def_.get("level", "minor"),
                status="open",
                detail=def_.get("detail", ""),
            ))

        mission.status = "completed"
        return {"flight_km": mission.plan_km, "images": len(mission.route or []),
                "tickets": len(defects or [])}


# 禁飞区/障碍模拟数据（用于演示与测试）
SAMPLE_OBSTACLES = []