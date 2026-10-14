"""临时桩引擎：仅用于在真实模型就绪前联调服务层。

会被 scripts/selftest.py 注入；不属于产品代码路径。
"""
import hashlib


def score_sequence(seq: str, models: str = "auto") -> float:
    digest = hashlib.md5(seq.encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def model_info() -> dict:
    return {"short": 15, "long": 15}
