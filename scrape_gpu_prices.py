#!/usr/bin/env python3
"""
GPU Rental Price Tracker — daily time-series collector.

Tracks H100 SXM 80GB / A100 SXM 80GB / H200 SXM 141GB / B200 SXM 180GB across
live spot markets (Vast.ai, RunPod) plus a curated reference set for the major
hyperscalers / managed clouds (AWS, Azure, GCP, Lambda Labs, CoreWeave, ...).

Each record carries a `source` flag:
  - "live"      : pulled from a vendor public API on each run
  - "reference" : human-curated list price, dated via `as_of`

Output:
  gpu_prices.json   — full history keyed by YYYY-MM-DD
  gpu_prices.html   — self-contained dashboard (embedded data block updated in place)
  scrape.log        — appended on every run

Designed to be safe to run repeatedly per day: later runs overwrite the
day's bucket so a manual re-run will not duplicate entries.
"""

import io
import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Windows UTF-8 ──
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "gpu_prices.json"
HTML_FILE = SCRIPT_DIR / "gpu_prices.html"
INDEX_FILE = SCRIPT_DIR / "index.html"  # mirror of HTML_FILE for GitHub Pages root landing
LOG_FILE = SCRIPT_DIR / "scrape.log"

NOW = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")
ISO_TIME = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; gpu-price-tracker/2.0)",
    "Accept": "application/json",
}

# ── Target GPU canonical names (what we display) ──
TARGETS = [
    {"key": "H100 SXM 80GB",  "category": "current",  "vast": "H100 SXM",  "vast_min_ram": 80,  "runpod_id": "NVIDIA H100 80GB HBM3"},
    {"key": "A100 SXM 80GB",  "category": "previous", "vast": "A100 SXM4", "vast_min_ram": 80,  "runpod_id": "NVIDIA A100-SXM4-80GB"},
    {"key": "H200 SXM 141GB", "category": "next-gen", "vast": "H200",      "vast_min_ram": 140, "runpod_id": "NVIDIA H200"},
    {"key": "B200 SXM 180GB", "category": "next-gen", "vast": "B200",      "vast_min_ram": 170, "runpod_id": "NVIDIA B200"},
]

# ── Reference (curated) prices for vendors without a public price API.
#    Format: (provider, gpu_key, $/hr, as_of_date YYYY-MM-DD)
#    Bump `as_of` when you re-verify these from vendor pricing pages.
REFERENCE = [
    # H100 SXM 80GB
    ("AWS",          "H100 SXM 80GB",  6.88,  "2026-06-23"),
    ("Azure",        "H100 SXM 80GB", 12.29,  "2026-06-23"),
    ("GCP",          "H100 SXM 80GB", 10.98,  "2026-06-23"),
    ("Lambda Labs",  "H100 SXM 80GB",  3.99,  "2026-06-23"),
    ("CoreWeave",    "H100 SXM 80GB",  4.25,  "2026-06-23"),
    ("Modal",        "H100 SXM 80GB",  3.95,  "2026-06-23"),
    ("Baseten",      "H100 SXM 80GB",  6.50,  "2026-06-23"),
    ("Hyperstack",   "H100 SXM 80GB",  2.40,  "2026-06-23"),
    ("TensorDock",   "H100 SXM 80GB",  2.25,  "2026-06-23"),
    ("HPC-AI",       "H100 SXM 80GB",  1.99,  "2026-06-23"),
    ("Thunder Compute","H100 SXM 80GB",1.38,  "2026-06-23"),

    # A100 SXM 80GB
    ("AWS",          "A100 SXM 80GB",  3.43,  "2026-06-23"),
    ("Azure",        "A100 SXM 80GB",  3.67,  "2026-06-23"),
    ("GCP",          "A100 SXM 80GB",  5.78,  "2026-06-23"),
    ("Lambda Labs",  "A100 SXM 80GB",  2.79,  "2026-06-23"),
    ("CoreWeave",    "A100 SXM 80GB",  2.21,  "2026-06-23"),
    ("Modal",        "A100 SXM 80GB",  2.50,  "2026-06-23"),
    ("Baseten",      "A100 SXM 80GB",  4.00,  "2026-06-23"),
    ("Hyperstack",   "A100 SXM 80GB",  1.60,  "2026-06-23"),
    ("Thunder Compute","A100 SXM 80GB",0.78,  "2026-06-23"),

    # H200 SXM 141GB
    ("Lambda Labs",  "H200 SXM 141GB", 3.79,  "2026-06-23"),
    ("HPC-AI",       "H200 SXM 141GB", 2.50,  "2026-06-23"),
    ("Yotta Labs",   "H200 SXM 141GB", 3.75,  "2026-06-23"),

    # B200 SXM 180GB
    ("Lambda Labs",  "B200 SXM 180GB", 6.69,  "2026-06-23"),
    ("Modal",        "B200 SXM 180GB", 6.25,  "2026-06-23"),
    ("Baseten",      "B200 SXM 180GB", 9.98,  "2026-06-23"),
    ("HPC-AI",       "B200 SXM 180GB", 4.00,  "2026-06-23"),
    ("Yotta Labs",   "B200 SXM 180GB", 5.37,  "2026-06-23"),
]


def log(msg: str) -> None:
    line = f"[{ISO_TIME}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except IOError:
        pass


# ── Live fetchers ──────────────────────────────────────────────────────────

def fetch_vastai(gpu_name: str, min_ram_gb: int):
    """Return (median_price, min_price, sample_size) for cheapest rentable offers."""
    url = "https://console.vast.ai/api/v0/bundles"
    q = {
        "gpu_name": {"eq": gpu_name},
        "rentable": {"eq": True},
        "num_gpus": {"eq": 1},
        "gpu_ram": {"gte": min_ram_gb * 1024 * 0.95},  # 5% slack for vendor rounding
        "order": [["dph_total", "asc"]],
        "limit": 25,
    }
    r = requests.get(url, params={"q": json.dumps(q)}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    offers = r.json().get("offers", [])
    prices = sorted(float(o["dph_total"]) for o in offers if o.get("dph_total"))
    if not prices:
        return None
    # Trim top 10% to avoid one-off outliers, then take min + median of the rest
    keep = prices[: max(1, int(len(prices) * 0.9))]
    median = keep[len(keep) // 2]
    return {"min": round(prices[0], 3), "median": round(median, 3), "n": len(prices)}


def fetch_runpod():
    """Return {gpu_id: {secure, community, lowest}} for all RunPod GPUs."""
    url = "https://api.runpod.io/graphql"
    query = """
    query { gpuTypes {
      id displayName memoryInGb
      securePrice communityPrice
      lowestPrice(input:{gpuCount:1}){uninterruptablePrice minimumBidPrice}
    }}
    """
    r = requests.post(url, json={"query": query}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    out = {}
    for g in r.json().get("data", {}).get("gpuTypes", []):
        lp = g.get("lowestPrice") or {}
        out[g["id"]] = {
            "name": g.get("displayName"),
            "memory_gb": g.get("memoryInGb"),
            "secure": g.get("securePrice"),
            "community": g.get("communityPrice"),
            "lowest": lp.get("uninterruptablePrice"),
            "spot": lp.get("minimumBidPrice"),
        }
    return out


# ── Collection ────────────────────────────────────────────────────────────

def collect():
    records = []
    runpod_data = {}

    try:
        runpod_data = fetch_runpod()
        log(f"RunPod: {len(runpod_data)} GPU types loaded")
    except Exception as e:
        log(f"RunPod fetch failed: {e}")

    for t in TARGETS:
        gpu_key = t["key"]

        # Vast.ai — emit both the cheapest offer and a "median" provider entry
        try:
            v = fetch_vastai(t["vast"], t["vast_min_ram"])
            if v:
                records.append({
                    "provider": "Vast.ai (min)",
                    "gpu_model": gpu_key,
                    "price_per_hour_usd": v["min"],
                    "category": t["category"],
                    "source": "live",
                    "extra": {"sample_size": v["n"]},
                    "scrape_time": ISO_TIME,
                })
                records.append({
                    "provider": "Vast.ai (median)",
                    "gpu_model": gpu_key,
                    "price_per_hour_usd": v["median"],
                    "category": t["category"],
                    "source": "live",
                    "extra": {"sample_size": v["n"]},
                    "scrape_time": ISO_TIME,
                })
                log(f"Vast.ai {gpu_key}: min=${v['min']} median=${v['median']} n={v['n']}")
            else:
                log(f"Vast.ai {gpu_key}: no offers")
        except Exception as e:
            log(f"Vast.ai {gpu_key} failed: {e}")

        # RunPod — Secure & Community as two providers (lowestPrice is the truth)
        rp = runpod_data.get(t["runpod_id"])
        if rp:
            sec = rp.get("secure")
            com = rp.get("community")
            if sec and sec > 0:
                records.append({
                    "provider": "RunPod (Secure)",
                    "gpu_model": gpu_key,
                    "price_per_hour_usd": round(float(sec), 3),
                    "category": t["category"],
                    "source": "live",
                    "scrape_time": ISO_TIME,
                })
            if com and com > 0:
                records.append({
                    "provider": "RunPod (Community)",
                    "gpu_model": gpu_key,
                    "price_per_hour_usd": round(float(com), 3),
                    "category": t["category"],
                    "source": "live",
                    "scrape_time": ISO_TIME,
                })
            log(f"RunPod {gpu_key}: secure=${sec} community=${com}")
        else:
            log(f"RunPod {gpu_key}: id {t['runpod_id']!r} not in response")

    # Reference (curated) — always emit; marked with source/as_of
    for provider, gpu_key, price, as_of in REFERENCE:
        cat = next((t["category"] for t in TARGETS if t["key"] == gpu_key), "other")
        records.append({
            "provider": provider,
            "gpu_model": gpu_key,
            "price_per_hour_usd": price,
            "category": cat,
            "source": "reference",
            "as_of": as_of,
            "scrape_time": ISO_TIME,
        })

    return records


# ── Persistence ───────────────────────────────────────────────────────────

def load_existing():
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            log("WARN: existing JSON unreadable, starting fresh")
    return {"last_updated": None, "history": {}}


def save(data):
    import shutil

    data["last_updated"] = ISO_TIME
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"Saved {OUTPUT_FILE.name}")
    embed_in_html(data)
    # Mirror to index.html so GitHub Pages has a clean root landing page.
    try:
        shutil.copyfile(HTML_FILE, INDEX_FILE)
        log(f"Mirrored dashboard to {INDEX_FILE.name}")
    except OSError as e:
        log(f"WARN: could not mirror index.html: {e}")


def embed_in_html(data):
    """Replace the EMBEDDED_DATA literal in gpu_prices.html in place."""
    if not HTML_FILE.exists():
        log(f"WARN: {HTML_FILE.name} missing; skipping embed")
        return
    html = HTML_FILE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False)
    pattern = re.compile(r"const\s+EMBEDDED_DATA\s*=\s*\{.*?\};", re.DOTALL)
    if not pattern.search(html):
        log(f"WARN: EMBEDDED_DATA marker not found in {HTML_FILE.name}")
        return
    new_html = pattern.sub(f"const EMBEDDED_DATA = {payload};", html, count=1)
    if new_html != html:
        HTML_FILE.write_text(new_html, encoding="utf-8")
        log(f"Updated {HTML_FILE.name}")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    log(f"=== GPU Price Tracker run ===")
    try:
        records = collect()
    except Exception:
        log("FATAL during collect():\n" + traceback.format_exc())
        sys.exit(1)

    providers = sorted({r["provider"] for r in records})
    log(f"Collected {len(records)} records across {len(providers)} providers")

    data = load_existing()
    data["history"][TODAY] = records

    # Cap at 365 days
    dates = sorted(data["history"].keys())
    while len(dates) > 365:
        del data["history"][dates.pop(0)]

    save(data)

    # Daily summary
    print("\n=== Today's Prices (min — max) ===")
    for t in TARGETS:
        prices = [r for r in records if r["gpu_model"] == t["key"]]
        if not prices:
            continue
        prices.sort(key=lambda x: x["price_per_hour_usd"])
        lo, hi = prices[0], prices[-1]
        print(f"  {t['key']:18}  ${lo['price_per_hour_usd']:6.2f} ({lo['provider']})  →  ${hi['price_per_hour_usd']:6.2f} ({hi['provider']})")


if __name__ == "__main__":
    main()
