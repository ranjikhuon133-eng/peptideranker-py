"""PeptideRanker 本地打分应用 —— Python 包入口。

原程序是 2010 年编译的 Linux x86-64 二进制（PeptideRanker + 30 个 .model 权重），
在 Windows 上无法运行，且需要手工解析文本输出。本包用纯 Python/NumPy 复刻其
前向推理，并提供统一的打分接口。

模块分工：
  pr_engine.scoring  对外唯一的打分 API（批量、阈值、统计）
  pr_engine.reference.oracle  逐位复刻原二进制数值行为的参考实现（逆向所得）
"""

__version__ = "1.0.0"
