# -*- coding: utf-8 -*-
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .core.database import Base, engine
from .core.migrate import run_migrations
from .api.router import router

BASE = Path(__file__).resolve().parent.parent
STATIC = BASE / "static"

app = FastAPI(title="无人机电力巡检任务规划系统", version="1.0.0")

Base.metadata.create_all(bind=engine)
run_migrations()  # 老库补列 + 回填时限与风险统计

app.include_router(router)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")