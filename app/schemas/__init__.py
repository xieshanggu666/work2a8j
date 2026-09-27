# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class LineOut(BaseModel):
    id: int
    code: str
    name: str
    voltage_kv: int
    total_km: float
    status: str
    tower_count: int = 0
    open_defects: int = 0       # 未闭环缺陷工单数
    overdue_defects: int = 0    # 超时未闭环工单数
    risk_level: str = "normal"  # 综合风险：normal/suspect/key

    class Config:
        from_attributes = True


class TowerOut(BaseModel):
    id: int
    seq: int
    code: str
    lat: float
    lng: float
    cum_km: float
    risk_hint: str

    class Config:
        from_attributes = True


class LineDetail(LineOut):
    towers: List[TowerOut] = []


class DroneOut(BaseModel):
    id: int
    code: str
    model: str
    battery_capacity: float
    battery_soc: float
    status: str
    max_payload: float

    class Config:
        from_attributes = True


class BatteryOut(BaseModel):
    id: int
    code: str
    capacity_km: float
    soc: float
    cycle_count: int
    status: str

    class Config:
        from_attributes = True


class MissionOut(BaseModel):
    id: int
    code: str
    name: str
    line_id: int
    line_code: Optional[str] = None
    start_tower_id: int
    end_tower_id: int
    plan_km: float
    estimated_battery_pct: float
    assigned_drone_id: Optional[int] = None
    drone_code: Optional[str] = None
    assigned_battery_id: Optional[int] = None
    battery_code: Optional[str] = None
    priority: str
    status: str
    created_at: Any = None
    completed_at: Any = None

    class Config:
        from_attributes = True


class MissionDetail(MissionOut):
    route: Optional[List[Dict[str, Any]]] = None
    images_count: int = 0
    tickets_count: int = 0
    ticket_stats: Dict[str, int] = {}   # 工单状态分布（含 overdue 超时数）


class MissionCreate(BaseModel):
    code: Optional[str] = None
    name: str
    line_id: int
    start_tower_id: int
    end_tower_id: int
    priority: str = "normal"
    return_km: float = 0.0


class ImageOut(BaseModel):
    id: int
    mission_id: int
    tower_id: Optional[int]
    filename: str
    defect_type: Optional[str]
    confidence: Optional[float]
    defect_level: Optional[str]
    labeled: int

    class Config:
        from_attributes = True


class TicketOut(BaseModel):
    id: int
    code: str
    mission_id: int
    tower_id: Optional[int]
    title: str
    level: str
    status: str
    detail: str
    assignee: Optional[str] = None
    assigned_at: Any = None
    due_at: Any = None
    resolution: str = ""
    resolved_at: Any = None
    reviewer: Optional[str] = None
    closed_at: Any = None
    return_reason: str = ""
    return_count: int = 0
    sla_hours: int = 0      # 该等级的闭环时限
    overdue: bool = False   # 是否已超时未闭环
    created_at: Any = None

    class Config:
        from_attributes = True


class TicketAssign(BaseModel):
    assignee: str                    # 处理人


class TicketSubmit(BaseModel):
    resolution: str = ""             # 处理结果说明


class TicketReview(BaseModel):
    approve: bool                    # True 通过闭环 / False 退回
    reviewer: str = ""               # 复核人
    reason: str = ""                 # 退回原因（退回时必填）


class ExecuteRequest(BaseModel):
    weather_ok: bool = True


class DefectIn(BaseModel):
    seq: int = 1
    tower_id: Optional[int] = None
    title: str
    level: str = "minor"
    detail: str = ""


class DefectBatch(BaseModel):
    defects: List[DefectIn] = []


class Message(BaseModel):
    detail: str = "ok"