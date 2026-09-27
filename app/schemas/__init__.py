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
    risk_level: str = "normal"
    open_ticket_count: int = 0
    tower_count: int = 0

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
    open_ticket_count: int = 0
    created_at: Any = None
    completed_at: Any = None

    class Config:
        from_attributes = True


class MissionDetail(MissionOut):
    route: Optional[List[Dict[str, Any]]] = None
    images_count: int = 0
    tickets_count: int = 0
    overdue_ticket_count: int = 0


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
    mission_code: Optional[str] = None
    tower_id: Optional[int]
    title: str
    level: str
    status: str
    detail: str
    assignee: Optional[str] = None
    assigned_at: Any = None
    due_at: Any = None
    resolve_note: str = ""
    resolved_at: Any = None
    reviewer: Optional[str] = None
    reviewed_at: Any = None
    closed_at: Any = None
    reject_reason: str = ""
    reject_count: int = 0
    overdue: bool = False
    created_at: Any = None

    class Config:
        from_attributes = True


class TicketEventOut(BaseModel):
    id: int
    action: str
    actor: str
    note: str
    created_at: Any = None

    class Config:
        from_attributes = True


class TicketDetail(TicketOut):
    events: List[TicketEventOut] = []


class TicketAssignIn(BaseModel):
    assignee: str
    due_hours: Optional[float] = None   # 不传则按缺陷等级默认时限
    actor: Optional[str] = None


class TicketSubmitIn(BaseModel):
    note: str = ""
    actor: Optional[str] = None


class TicketReviewIn(BaseModel):
    reviewer: str
    approve: bool = True
    reason: str = ""                    # 退回时必填


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