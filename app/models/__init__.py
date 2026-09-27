# -*- coding: utf-8 -*-
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..core.database import Base


class Line(Base):
    """输电线路"""
    __tablename__ = "lines"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, index=True, nullable=False)
    name = Column(String(64), nullable=False)
    voltage_kv = Column(Integer, nullable=False, default=110)      # 电压等级
    total_km = Column(Float, nullable=False, default=0.0)         # 线路总长 km
    status = Column(String(16), nullable=False, default="in_service")  # in_service/maintenance
    # 缺陷工单回写的线路风险统计
    risk_level = Column(String(16), nullable=False, default="normal")  # normal/suspect/key
    open_ticket_count = Column(Integer, nullable=False, default=0)     # 未闭环工单数

    towers = relationship("Tower", back_populates="line", cascade="all, delete-orphan")
    missions = relationship("Mission", back_populates="line", cascade="all, delete-orphan")


class Tower(Base):
    """杆塔（巡检对象）"""
    __tablename__ = "towers"

    id = Column(Integer, primary_key=True, index=True)
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=False)
    seq = Column(Integer, nullable=False)          # 杆塔编号（沿线路顺序）
    code = Column(String(32), nullable=False)      # 如 T-001
    lat = Column(Float, nullable=False)            # 纬度
    lng = Column(Float, nullable=False)            # 经度
    cum_km = Column(Float, nullable=False, default=0.0)  # 距起点的累计里程
    risk_hint = Column(String(16), nullable=False, default="normal")  # normal/suspect/key

    line = relationship("Line", back_populates="towers")


class Drone(Base):
    """无人机（机队）"""
    __tablename__ = "drones"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, nullable=False)
    model = Column(String(32), nullable=False)
    battery_capacity = Column(Float, nullable=False)  # 满电续航 km（一次充电最大飞行里程）
    battery_soc = Column(Float, nullable=False, default=1.0)  # 当前电量 0-1
    status = Column(String(16), nullable=False, default="idle")  # idle/flying/charging/maintenance
    max_payload = Column(Float, nullable=False, default=1.0)     # 最大载荷 kg


class BatteryPack(Base):
    """电池包"""
    __tablename__ = "battery_packs"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, nullable=False)
    capacity_km = Column(Float, nullable=False)   # 单次满电续航 km
    soc = Column(Float, nullable=False, default=1.0)
    cycle_count = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="ready")  # ready/charging/use/depleted


class Mission(Base):
    """巡检任务"""
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=False)
    # 任务覆盖的杆塔区间 [start_tower_id, end_tower_id]
    start_tower_id = Column(Integer, nullable=False)
    end_tower_id = Column(Integer, nullable=False)
    plan_km = Column(Float, nullable=False, default=0.0)      # 规划航线总长
    estimated_battery_pct = Column(Float, nullable=False, default=0.0)  # 需消耗电量比例
    assigned_drone_id = Column(Integer, ForeignKey("drones.id"), nullable=True)
    assigned_battery_id = Column(Integer, ForeignKey("battery_packs.id"), nullable=True)
    priority = Column(String(16), nullable=False, default="normal")  # high/normal/low
    status = Column(String(16), nullable=False, default="planned")  # planned/in_progress/completed/canceled
    route = Column(JSON, nullable=True)            # 规划航线点列表 [{lat,lng,seq}]
    open_ticket_count = Column(Integer, nullable=False, default=0)  # 工单回写：未闭环工单数
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)

    line = relationship("Line", back_populates="missions")
    drone = relationship("Drone", foreign_keys=[assigned_drone_id])
    battery = relationship("BatteryPack", foreign_keys=[assigned_battery_id])
    images = relationship("InspectionImage", back_populates="mission", cascade="all, delete-orphan")
    tickets = relationship("RepairTicket", back_populates="mission", cascade="all, delete-orphan")


class InspectionImage(Base):
    """巡检影像"""
    __tablename__ = "inspection_images"

    id = Column(Integer, primary_key=True, index=True)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=False)
    tower_id = Column(Integer, nullable=True)
    filename = Column(String(128), nullable=False)
    shot_at = Column(DateTime, server_default=func.now())
    defect_type = Column(String(32), nullable=True)   # 标注缺陷类别
    confidence = Column(Float, nullable=True)         # AI 置信度
    defect_level = Column(String(16), nullable=True)  # minor/major/critical
    labeled = Column(Integer, nullable=False, default=0)  # 是否已人工复核

    mission = relationship("Mission", back_populates="images")


class RepairTicket(Base):
    """缺陷隐患工单（闭环状态流：open→processing→resolved→closed，支持复核退回与超时）"""
    __tablename__ = "repair_tickets"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, nullable=False)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=False)
    tower_id = Column(Integer, nullable=True)
    title = Column(String(64), nullable=False)
    level = Column(String(16), nullable=False, default="minor")  # minor/major/critical
    status = Column(String(16), nullable=False, default="open")  # open/processing/resolved/closed
    detail = Column(Text, nullable=False, default="")
    # 处理人 / 时限
    assignee = Column(String(32), nullable=True)        # 处理人
    assigned_at = Column(DateTime, nullable=True)       # 派单时间
    due_at = Column(DateTime, nullable=True)            # 处理时限（超时判定基准）
    # 处理与复核
    resolve_note = Column(Text, nullable=False, default="")   # 处理说明
    resolved_at = Column(DateTime, nullable=True)       # 提交处理时间
    reviewer = Column(String(32), nullable=True)        # 复核人
    reviewed_at = Column(DateTime, nullable=True)       # 复核时间
    closed_at = Column(DateTime, nullable=True)         # 关闭时间
    reject_reason = Column(Text, nullable=False, default="")  # 最近退回原因
    reject_count = Column(Integer, nullable=False, default=0)  # 被退回次数
    created_at = Column(DateTime, server_default=func.now())

    mission = relationship("Mission", back_populates="tickets")
    events = relationship("TicketEvent", back_populates="ticket",
                          cascade="all, delete-orphan", order_by="TicketEvent.id")


class TicketEvent(Base):
    """工单流转事件（创建/派单/提交/复核通过/复核退回）"""
    __tablename__ = "ticket_events"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("repair_tickets.id"), nullable=False)
    action = Column(String(16), nullable=False)   # create/assign/submit/approve/reject
    actor = Column(String(32), nullable=False, default="系统")
    note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now())

    ticket = relationship("RepairTicket", back_populates="events")


class FlightRecord(Base):
    """飞行合规记录"""
    __tablename__ = "flight_records"

    id = Column(Integer, primary_key=True, index=True)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=False)
    drone_id = Column(Integer, nullable=True)
    flight_km = Column(Float, nullable=False, default=0.0)
    soc_start = Column(Float, nullable=False)
    soc_end = Column(Float, nullable=False)
    weather_ok = Column(Integer, nullable=False, default=1)
    cleared_by = Column(String(32), nullable=False, default="民航监管")
    record_time = Column(DateTime, server_default=func.now())