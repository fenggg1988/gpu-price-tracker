"""CLI 入口：init-db | scrape | serve | export"""
import sys
import io

# 修复 Windows GBK 编码问题
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import click

from database import init_db, query_prices, query_daily_cheapest


@click.group()
def cli():
    """GPU 租赁价格追踪器"""


@cli.command()
def init_db_command():
    """初始化数据库"""
    init_db()
    click.echo("✓ 数据库初始化完成")


@cli.command()
@click.option("--source", default=None, help="只抓取指定数据源 (vastai / runpod)")
def scrape(source):
    """运行数据抓取"""
    from datetime import date
    import time as time_mod
    from database import insert_prices, insert_scrape_log

    today = date.today().isoformat()

    sources = []
    if source:
        if source == "vastai":
            from scraper.vastai import scrape_vastai
            sources.append(("vastai", scrape_vastai))
        elif source == "runpod":
            from scraper.runpod import scrape_runpod
            sources.append(("runpod", scrape_runpod))
        else:
            click.echo(f"未知数据源: {source}")
            return
    else:
        from scraper.vastai import scrape_vastai
        from scraper.runpod import scrape_runpod
        sources = [
            ("vastai", scrape_vastai),
            ("runpod", scrape_runpod),
        ]

    total_added = 0
    for name, scraper_func in sources:
        click.echo(f"[{name}] 开始抓取...")
        start = time_mod.time()
        try:
            records = scraper_func()
            elapsed = time_mod.time() - start
            added = insert_prices(records)
            total_added += added
            gpus = len(set(r["gpu_model"] for r in records))
            insert_scrape_log(name, "success", gpus, added, len(records),
                              duration_sec=round(elapsed, 2))
            click.echo(f"  ✓ {name}: {added} 条新增, {len(records)} 条总计, "
                       f"{gpus} 种GPU, 耗时 {elapsed:.1f}s")
        except Exception as e:
            elapsed = time_mod.time() - start
            insert_scrape_log(name, "failed", error_message=str(e),
                              duration_sec=round(elapsed, 2))
            click.echo(f"  ✗ {name}: 失败 — {e}")

    click.echo(f"\n总计新增 {total_added} 条记录 (日期: {today})")


@cli.command()
def serve():
    """启动 Web 服务"""
    from config import FLASK_HOST, FLASK_PORT
    from web.app import app
    click.echo(f"启动服务: http://{FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=True)


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["csv"]), default="csv")
@click.option("--output", default=None, help="输出文件路径")
def export(fmt, output):
    """导出数据"""
    import csv
    import sys

    rows = query_prices()
    if not rows:
        click.echo("无数据可导出")
        return

    if output:
        f = open(output, "w", newline="", encoding="utf-8")
    else:
        f = sys.stdout

    if fmt == "csv":
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        if output:
            click.echo(f"✓ 已导出 {len(rows)} 条记录到 {output}")

    if output:
        f.close()


if __name__ == "__main__":
    cli()
