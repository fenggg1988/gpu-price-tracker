"""Vast.ai API 抓取器"""
import json
import time
import urllib.parse
from datetime import date

import requests

from config import VASTAI_BASE_URL, REQUEST_DELAY_SEC, MAX_RETRIES, SCRAPE_TIMEOUT_SEC, TARGET_GPUS
from scraper.utils import normalize_gpu_name, extract_submodel


def _fetch_all_offers() -> list[dict]:
    """从 Vast.ai API 获取所有可租用的 GPU 报价（不分页，一次拉取）"""
    filter_dict = {"rentable": {"eq": True}}
    filter_json = json.dumps(filter_dict)
    url = f"{VASTAI_BASE_URL}?q={urllib.parse.quote(filter_json)}"

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=SCRAPE_TIMEOUT_SEC)
            if resp.status_code == 429:
                wait = (attempt + 1) * 10
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("offers", [])
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY_SEC * (attempt + 1))
            else:
                raise
    return []


def scrape_vastai() -> list[dict]:
    """抓取 Vast.ai 上所有目标 GPU 的价格。

    一次性拉取全部可租用报价，再按 TARGET_GPUS 客户端过滤。

    Returns:
        list[dict]: 标准化后的价格记录
    """
    today = date.today().isoformat()
    records = []

    try:
        offers = _fetch_all_offers()
    except Exception as e:
        raise RuntimeError(f"Vast.ai API 请求失败: {e}")

    for offer in offers:
        gpu_name = offer.get("gpu_name", "")
        normalized = normalize_gpu_name(gpu_name)
        if not normalized:
            continue

        records.append({
            "gpu_model": normalized,
            "gpu_submodel": extract_submodel(gpu_name, normalized),
            "provider": "vast.ai",
            "price_per_hour": round(offer.get("dph_total", 0), 6),
            "tier": "verified" if offer.get("verification") == "verified" else "on-demand",
            "vram_gb": round(offer.get("gpu_ram", 0) / 1024, 1) if offer.get("gpu_ram") else None,
            "location": offer.get("geolocation", ""),
            "reliability": round(offer.get("reliability", 0), 4) if offer.get("reliability") else None,
            "scrape_date": today,
        })

    return records
