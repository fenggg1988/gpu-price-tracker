"""GPU 名称归一化、异常值过滤"""
import re
from config import TARGET_GPUS


def normalize_gpu_name(raw_name: str) -> str | None:
    """将各种 GPU 名称归一化为标准名称。

    例如:
        "NVIDIA H100 80GB HBM3" -> "H100"
        "RTX 4090" -> "RTX 4090"
        "Tesla V100" -> None (不在 TARGET_GPUS 中)
    """
    raw_upper = raw_name.upper().strip()

    for target in TARGET_GPUS:
        target_upper = target.upper()
        # RTX 4090 精确匹配优先
        if target_upper in raw_upper:
            return target
        # 子型号匹配: "H100" 匹配 "NVIDIA H100 80GB HBM3", "H100 SXM", "H100 PCIe"
        # 但要避免 "H100" 误匹配 "GH100" 等
        pattern = rf'\b{re.escape(target_upper)}\b'
        if re.search(pattern, raw_upper):
            return target

    return None


def extract_submodel(raw_name: str, gpu_model: str) -> str:
    """从原始名称提取子型号。"""
    raw_upper = raw_name.upper().strip()
    # 常见子型号关键词
    submodel_keywords = ["SXM", "PCIE", "NVL", "SUPER", "TI", "ADA"]
    found = []
    for kw in submodel_keywords:
        if kw in raw_upper:
            found.append(kw)
    if found:
        return " ".join(found)
    return raw_name


def normalize_provider_name(raw: str) -> str:
    """归一化提供商名称"""
    mapping = {
        "vast.ai": "vast.ai",
        "vastai": "vast.ai",
        "vast": "vast.ai",
        "runpod": "runpod",
        "runpod.io": "runpod",
    }
    return mapping.get(raw.lower(), raw.lower())


def filter_outliers_iqr(prices: list[float]) -> list[float]:
    """使用 IQR 方法过滤异常值"""
    if len(prices) < 4:
        return prices

    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    q1 = sorted_prices[n // 4]
    q3 = sorted_prices[3 * n // 4]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [p for p in prices if lower <= p <= upper]
