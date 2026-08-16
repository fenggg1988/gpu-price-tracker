"""Flask Web 应用 + API 路由"""
import csv
import io
from datetime import date

from flask import Flask, jsonify, render_template, request, Response

from database import (
    init_db, query_prices, query_daily_cheapest,
    query_stats, query_source_status, get_available_gpus, get_date_range
)

app = Flask(__name__)

# 确保数据库已初始化
init_db()


@app.route("/")
def index():
    """仪表盘主页"""
    return render_template("index.html")


@app.route("/api/prices")
def api_prices():
    """查询价格数据"""
    gpu = request.args.get("gpu")
    provider = request.args.get("provider")
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    tier = request.args.get("tier")

    rows = query_prices(
        gpu=gpu, provider=provider,
        start_date=start_date, end_date=end_date,
        tier=tier,
    )
    return jsonify(rows)


@app.route("/api/prices/daily")
def api_prices_daily():
    """查询每日最低价（用于趋势图）"""
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    rows = query_daily_cheapest(start_date=start_date, end_date=end_date)
    return jsonify(rows)


@app.route("/api/prices/latest")
def api_prices_latest():
    """查询最新一天的数据"""
    date_range = get_date_range()
    if not date_range["max_date"]:
        return jsonify([])
    rows = query_prices(end_date=date_range["max_date"])
    return jsonify(rows)


@app.route("/api/stats")
def api_stats():
    """获取摘要统计"""
    return jsonify(query_stats())


@app.route("/api/sources/status")
def api_sources_status():
    """获取数据源状态"""
    return jsonify(query_source_status())


@app.route("/api/gpus")
def api_gpus():
    """获取可用的 GPU 列表"""
    return jsonify(get_available_gpus())


@app.route("/api/daterange")
def api_daterange():
    """获取数据日期范围"""
    return jsonify(get_date_range())


@app.route("/api/export/csv")
def api_export_csv():
    """导出 CSV"""
    gpu = request.args.get("gpu")
    start_date = request.args.get("start")
    end_date = request.args.get("end")
    rows = query_prices(gpu=gpu, start_date=start_date, end_date=end_date)

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=gpu_prices_{date.today()}.csv"}
    )
