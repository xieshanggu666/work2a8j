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
    created_at: Any = None
    resolved_at: Any = None

    class Config:
        from_attributes = True


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