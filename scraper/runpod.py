"""RunPod GraphQL API 抓取器"""
from datetime import date

import requests

from config import RUNPOD_GQL_URL, SCRAPE_TIMEOUT_SEC, TARGET_GPUS
from scraper.utils import normalize_gpu_name, extract_submodel


def scrape_runpod() -> list[dict]:
    """抓取 RunPod 上所有目标 GPU 的价格。

    Returns:
        list[dict]: 标准化后的价格记录
    """
    today = date.today().isoformat()
    records = []

    query = """
    query GpuTypes {
        gpuTypes {
            id
            displayName
            securePrice
            communityPrice
            memoryInGb
        }
    }
    """

    try:
        resp = requests.post(
            RUNPOD_GQL_URL,
            json={"query": query},
            timeout=SCRAPE_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        data = resp.json()
        gpu_types = data.get("data", {}).get("gpuTypes", [])
    except Exception as e:
        raise RuntimeError(f"RunPod API 请求失败: {e}")

    for gpu_type in gpu_types:
        gpu_id = gpu_type.get("id", "")
        normalized = normalize_gpu_name(gpu_id)
        if not normalized:
            # 也尝试用 displayName 匹配
            normalized = normalize_gpu_name(gpu_type.get("displayName", ""))
        if not normalized:
            continue

        # RunPod 有 secure 和 community 两种价格层级
        for tier_key, tier_label in [("securePrice", "secure"), ("communityPrice", "community")]:
            price = gpu_type.get(tier_key)
            if price and price > 0:
                records.append({
                    "gpu_model": normalized,
                    "gpu_submodel": extract_submodel(gpu_id, normalized),
                    "provider": "runpod",
                    "price_per_hour": round(price, 6),
                    "tier": tier_label,
                    "vram_gb": gpu_type.get("memoryInGb"),
                    "location": None,
                    "reliability": None,
                    "scrape_date": today,
                })

    return records
