# GPU Cloud Price Tracker

每天自动抓取主流 H100 / A100 / H200 / B200 SXM 卡的云租赁价格，累积时序数据，生成自包含的可视化仪表盘。

## 在线看板（GitHub Pages，云端自动更新）

**https://fenggg1988.github.io/gpu-price-tracker/**

数据由 GitHub Actions 每天在云端自动抓取并提交，GitHub Pages 随之自动重建，因此
**不需要本地电脑开机、也不需要打开任何软件**。本页数据随时是最新的。

## 数据来源

| 供应商 | 类型 | 接口 |
|---|---|---|
| Vast.ai | 实时（live） | 公开 bundles 搜索 API（min + median） |
| RunPod  | 实时（live） | 公开 GraphQL（Secure + Community 双价） |
| AWS / Azure / GCP / Lambda Labs / CoreWeave / Modal / Baseten / Hyperstack / TensorDock / Thunder Compute / HPC-AI / Yotta Labs | 参考价（reference） | 人工校准的官方挂牌价，带 `as_of` 日期 |

每条记录都有 `source` 字段，仪表盘上用 `LIVE` / `REF` 标签区分。

## 快速开始

```bash
# 立即抓取一次
python scrape_gpu_prices.py

# 双击打开仪表盘（数据已嵌入 HTML，不需要本地服务器）
start gpu_prices.html
```

## 每日自动抓取

通过 **GitHub Actions** 云端运行（`.github/workflows/daily.yml`），每天 01:00 UTC（**北京时间 09:00**）
自动执行 `scrape_gpu_prices.py`，把结果提交回 `gpu_prices.json` 与 `gpu_prices.html`，GitHub Pages 随之自动更新
—— 不需要本地电脑开机。

工作流同时支持手动触发；它与另外几个价格项目组成了**跨仓库链式自调度**（memory → gpu → agri → openrouter → purr），
任一环节被触发即可自动接力跑完全链。

> 历史方案：早期用本地 Windows Task Scheduler（`run_scraper.bat` / `scrape.log` / `scheduler/`）在每天 09:00 触发，
> 现已由云端 Actions 取代；本地脚本仅保留作手动兜底。

## 文件结构

```
gpu-price-tracker/
├── scrape_gpu_prices.py    # 主抓取脚本（live API + 参考价兜底）
├── gpu_prices.json         # 时序数据，{last_updated, history: {YYYY-MM-DD: [...]}}
├── gpu_prices.html         # 自包含 ECharts 仪表盘
├── run_scraper.bat         # Task Scheduler 入口
├── scrape.log              # 每次运行的日志（追加）
└── scheduler/              # PowerShell 注册脚本（备用，schtasks 已生效）
```

## 仪表盘功能

- **顶部卡片**：每张 GPU 的当前最低价、最低价供应商、价格区间、7 天涨跌幅
- **趋势折线图**：每日 min/median/mean 时序（多于 14 天自动加缩放条）
- **箱线图**：当日各供应商价格分布（min · Q1 · median · Q3 · max）
- **柱状对比**：超大规模云厂商 vs 现货市场 vs Tier-2 GPU 云
- **数据表**：可排序、按 GPU 过滤；显示 LIVE/REF 来源标签 + 7 天涨跌
- **CSV 导出**：所有历史数据一键下载

## 维护

- 参考价 `as_of` 日期写在 `scrape_gpu_prices.py` 的 `REFERENCE` 列表里，建议每季度校准一次（去各家定价页查实际挂牌价）
- 想加新的 GPU：在 `TARGETS` 列表追加一条，填好 Vast.ai `gpu_name` 和 RunPod `id`（运行一次脚本会在日志中打印所有 50 个 RunPod GPU id 供参考）
- 历史数据自动保留最近 365 天

## 环境

- Python 3.14（`C:\Users\fengz\AppData\Local\Programs\Python\Python314\python.exe`）
- 依赖：`requests`（见 `requirements.txt`）
