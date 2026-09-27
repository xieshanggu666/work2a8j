import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'drone.db'}"

# 巡检规划参数
PLAN_CHUNK_KM = 2.0     # 每段航线的最大杆塔间隔（km）
SAFE_SOC = 0.20        # 返航安全电量阈值
AVG_SPEED_KPH = 36.0   # 巡航速度 km/h
KPH_TO_KMH = 1.0