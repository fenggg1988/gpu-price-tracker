import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "gpu_prices.db"
LOG_DIR = BASE_DIR / "logs"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 跟踪的 GPU 型号
TARGET_GPUS = [
    "H100", "H200", "B200",
    "A100", "A6000", "L40S",
    "RTX 4090", "RTX 6000 Ada",
]

# Vast.ai 配置
VASTAI_API_KEY = os.getenv("VASTAI_API_KEY", "")
VASTAI_BASE_URL = "https://cloud.vast.ai/api/v0/bundles/"

# RunPod 配置
RUNPOD_GQL_URL = "https://api.runpod.io/graphql"

# 抓取设置
REQUEST_DELAY_SEC = 2.0
MAX_RETRIES = 3
SCRAPE_TIMEOUT_SEC = 30

# Flask 设置
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5080
