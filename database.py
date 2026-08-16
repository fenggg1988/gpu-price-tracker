"""数据库操作：建表、插入、查询"""
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional
from config import DB_PATH


def get_conn():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """创建数据库表"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gpu_prices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            gpu_model       TEXT NOT NULL,
            gpu_submodel    TEXT,
            provider        TEXT NOT NULL,
            price_per_hour  REAL NOT NULL,
            price_currency  TEXT DEFAULT 'USD',
            tier            TEXT DEFAULT 'on-demand',
            vram_gb         REAL,
            location        TEXT,
            reliability     REAL,
            scrape_date     DATE NOT NULL,
            scrape_time     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(gpu_model, gpu_submodel, provider, tier, scrape_date)
        );

        CREATE INDEX IF NOT EXISTS idx_gpu_date
            ON gpu_prices(gpu_model, scrape_date);
        CREATE INDEX IF NOT EXISTS idx_provider
            ON gpu_prices(provider, scrape_date);
        CREATE INDEX IF NOT EXISTS idx_date
            ON gpu_prices(scrape_date);

        CREATE TABLE IF NOT EXISTS scrape_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source          TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'failed',
            gpus_found      INTEGER DEFAULT 0,
            records_added   INTEGER DEFAULT 0,
            records_total   INTEGER DEFAULT 0,
            error_message   TEXT,
            duration_sec    REAL,
            scrape_time     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_log_time ON scrape_log(scrape_time);
    """)
    conn.commit()
    conn.close()


def insert_prices(records: list[dict]) -> int:
    """批量插入价格记录，返回新增条数。重复记录 (same unique key) 被忽略。"""
    if not records:
        return 0

    conn = get_conn()
    added = 0
    for r in records:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO gpu_prices
                    (gpu_model, gpu_submodel, provider, price_per_hour, tier,
                     vram_gb, location, reliability, scrape_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.get("gpu_model"),
                r.get("gpu_submodel"),
                r.get("provider"),
                r.get("price_per_hour"),
                r.get("tier", "on-demand"),
                r.get("vram_gb"),
                r.get("location"),
                r.get("reliability"),
                r.get("scrape_date"),
            ))
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                added += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return added


def insert_scrape_log(source: str, status: str, gpus_found: int = 0,
                      records_added: int = 0, records_total: int = 0,
                      error_message: str = None, duration_sec: float = None):
    """记录抓取日志"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO scrape_log (source, status, gpus_found, records_added,
                                records_total, error_message, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (source, status, gpus_found, records_added, records_total,
          error_message, duration_sec))
    conn.commit()
    conn.close()


def query_prices(gpu: str = None, provider: str = None,
                 start_date: str = None, end_date: str = None,
                 tier: str = None, aggregate: bool = False) -> list[dict]:
    """查询价格数据"""
    conn = get_conn()
    conditions = []
    params = []

    if gpu:
        conditions.append("gpu_model = ?")
        params.append(gpu)
    if provider:
        conditions.append("provider = ?")
        params.append(provider)
    if start_date:
        conditions.append("scrape_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("scrape_date <= ?")
        params.append(end_date)
    if tier:
        conditions.append("tier = ?")
        params.append(tier)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    if aggregate:
        sql = f"""
            SELECT gpu_model, scrape_date,
                   MIN(price_per_hour) as min_price,
                   AVG(price_per_hour) as avg_price,
                   MEDIAN(price_per_hour) as median_price,
                   MAX(price_per_hour) as max_price,
                   COUNT(*) as offer_count
            FROM gpu_prices
            {where}
            GROUP BY gpu_model, scrape_date
            ORDER BY scrape_date DESC, gpu_model
        """
    else:
        sql = f"""
            SELECT * FROM gpu_prices
            {where}
            ORDER BY scrape_date DESC, gpu_model
        """

    # SQLite 没有内置 MEDIAN，aggregate 模式下回退到 AVG
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_daily_cheapest(start_date: str = None, end_date: str = None) -> list[dict]:
    """查询每日每种 GPU 的最低价（用于趋势图）"""
    conn = get_conn()
    conditions = []
    params = []

    if start_date:
        conditions.append("scrape_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("scrape_date <= ?")
        params.append(end_date)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    sql = f"""
        SELECT gpu_model, scrape_date,
               MIN(price_per_hour) as price_per_hour,
               provider
        FROM gpu_prices
        {where}
        GROUP BY gpu_model, scrape_date
        ORDER BY scrape_date, gpu_model
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_stats() -> dict:
    """获取每种 GPU 的摘要统计（最新价格、涨跌幅）"""
    conn = get_conn()

    # 获取所有数据日期范围
    dates = conn.execute(
        "SELECT DISTINCT scrape_date FROM gpu_prices ORDER BY scrape_date"
    ).fetchall()

    if not dates:
        conn.close()
        return {}

    latest_date = dates[-1][0]
    # 7天前和30天前（最近的数据点）
    all_dates = [d[0] for d in dates]

    def closest_date(target_date: str) -> str:
        """找到最接近 target_date 的已有数据日期"""
        target = datetime.strptime(target_date, "%Y-%m-%d")
        best = all_dates[0]
        for d in all_dates:
            dt = datetime.strptime(d, "%Y-%m-%d")
            if dt <= target:
                best = d
            else:
                break
        return best

    date_7d = closest_date((datetime.strptime(latest_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d"))
    date_30d = closest_date((datetime.strptime(latest_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d"))

    # 每种 GPU 最新价格
    rows = conn.execute("""
        SELECT gpu_model, MIN(price_per_hour) as price, provider
        FROM gpu_prices WHERE scrape_date = ?
        GROUP BY gpu_model
    """, (latest_date,)).fetchall()

    stats = {}
    for r in rows:
        gpu = r[0]
        stats[gpu] = {
            "latest_price": round(r[1], 4),
            "latest_provider": r[2],
            "change_7d_pct": None,
            "change_30d_pct": None,
        }

        # 7天前价格
        r7 = conn.execute(
            "SELECT MIN(price_per_hour) FROM gpu_prices WHERE gpu_model=? AND scrape_date=?",
            (gpu, date_7d)
        ).fetchone()
        if r7 and r7[0]:
            old = r7[0]
            new = r[1]
            stats[gpu]["change_7d_pct"] = round((new - old) / old * 100, 1)

        # 30天前价格
        r30 = conn.execute(
            "SELECT MIN(price_per_hour) FROM gpu_prices WHERE gpu_model=? AND scrape_date=?",
            (gpu, date_30d)
        ).fetchone()
        if r30 and r30[0]:
            old = r30[0]
            new = r[1]
            stats[gpu]["change_30d_pct"] = round((new - old) / old * 100, 1)

    conn.close()
    return stats


def query_source_status() -> list[dict]:
    """获取各数据源最新抓取状态"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT source, status, gpus_found, records_added, scrape_time
        FROM scrape_log
        WHERE id IN (
            SELECT MAX(id) FROM scrape_log GROUP BY source
        )
        ORDER BY source
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_available_gpus() -> list[str]:
    """获取数据库中已有的 GPU 型号"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT gpu_model FROM gpu_prices ORDER BY gpu_model"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_date_range() -> dict:
    """获取数据的日期范围"""
    conn = get_conn()
    row = conn.execute(
        "SELECT MIN(scrape_date), MAX(scrape_date), COUNT(DISTINCT scrape_date) FROM gpu_prices"
    ).fetchone()
    conn.close()
    return {
        "min_date": row[0],
        "max_date": row[1],
        "days": row[2],
    }
