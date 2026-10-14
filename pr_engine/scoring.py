"""PeptideRanker 打分引擎 —— 本应用的唯一对外打分 API。

设计目标：把"难用"的部分全部收敛掉
  1. 不再需要 Linux 二进制、不再需要 Perl、不再解析 5 行文本输出；
  2. 不再写入 peptide.dataset 这类固定临时文件（因此天然支持并发）；
  3. 一次调用可以打分任意多条序列，自动按长度选择短肽/长肽模型（与原 .pl 一致）；
  4. 输出结构化数据（含统计量、直方图、警告），供网页 / CLI / 导出共用。

真实数值来自 pr_engine.reference.oracle —— 该模块由对原 ELF 二进制的逆向得到，
逐位复刻其前向推理（含 15 个模型的平均与 argmax 语义）。
"""

from __future__ import annotations

import math
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from pr_engine import i18n as _i18n

# 原二进制 .rodata 中的字母表（21 个），X 为未知残基
ALPHABET = "ACDEFGHIKLMNPQRSTVWYX"
# 标准氨基酸
STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")
# 歧义/非标准残基：在字母表之外，原程序查表失败 → 该位点整列留空 →
# 归一化时出现 0/0 → **整条序列的分数变成 NaN**。
AMBIGUOUS_AA = set("XBZJUO")
# 需要映射到 X 通道（索引 20）才能算出分数的歧义残基
TO_X: dict[str, str] = {ch: "X" for ch in "BZJUO"}
ALLOWED_AA = STANDARD_AA | AMBIGUOUS_AA

# 与原 PeptideRanker.pl 第 30-35 行完全一致的分界：长度 <= 20 用短肽模型
SHORT_MAX_LEN = 20

# 原 PeptideRanker 以 0.5 作为"可能具有生物活性"的判定阈值
DEFAULT_THRESHOLD = 0.5

# 单条序列长度上限：用于保护本机内存与响应时间（原程序对此没有保护）
MAX_SEQUENCE_LENGTH = 4000

# 一次请求的序列条数上限
MAX_BATCH_SIZE = 20000

HISTOGRAM_BINS = 10


class EngineNotReady(RuntimeError):
    """参考实现在导入时不可用（缺文件、缺依赖等）。"""


class SequenceError(ValueError):
    """单条序列不可打分（空、超长、非法字符过多等）。"""


@dataclass
class SequenceItem:
    """一条待打分的序列。"""

    id: str
    sequence: str


@dataclass
class ScoreResult:
    rank: int
    id: str
    sequence: str
    length: int
    score: float
    model: str  # "short" | "long"

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "id": self.id,
            "sequence": self.sequence,
            "length": self.length,
            "score": round(float(self.score), 6),
            "model": self.model,
        }


@dataclass
class BatchReport:
    results: list[ScoreResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: int = 0
    elapsed_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        scores = [r.score for r in self.results]
        if scores:
            summary = {
                "count": len(scores),
                "mean": round(statistics.fmean(scores), 4),
                "median": round(statistics.median(scores), 4),
                "min": round(min(scores), 4),
                "max": round(max(scores), 4),
                "n_above_threshold": sum(1 for s in scores if s >= DEFAULT_THRESHOLD),
                "threshold": DEFAULT_THRESHOLD,
            }
            hist = _histogram(scores)
        else:
            summary = {
                "count": 0,
                "mean": 0.0,
                "median": 0.0,
                "min": 0.0,
                "max": 0.0,
                "n_above_threshold": 0,
                "threshold": DEFAULT_THRESHOLD,
            }
            hist = [{"lo": i / HISTOGRAM_BINS, "hi": (i + 1) / HISTOGRAM_BINS, "count": 0}
                    for i in range(HISTOGRAM_BINS)]
        return {
            "results": [r.as_dict() for r in self.results],
            "warnings": list(self.warnings),
            "skipped": self.skipped,
            "summary": summary,
            "histogram": hist,
            "elapsed_ms": self.elapsed_ms,
        }


def _histogram(scores: Sequence[float]) -> list[dict[str, float]]:
    bins = [{"lo": i / HISTOGRAM_BINS, "hi": (i + 1) / HISTOGRAM_BINS, "count": 0}
            for i in range(HISTOGRAM_BINS)]
    for s in scores:
        idx = int(s * HISTOGRAM_BINS)
        if idx >= HISTOGRAM_BINS:
            idx = HISTOGRAM_BINS - 1
        if idx < 0:
            idx = 0
        bins[idx]["count"] += 1
    return bins


# --------------------------------------------------------------------------- #
# 参考实现（逆向所得）的加载与适配
# --------------------------------------------------------------------------- #

_ORACLE: Any = None
_ORACLE_ERROR: str | None = None


def _load_oracle():
    """惰性导入参考实现。返回 (module, error)。"""
    global _ORACLE, _ORACLE_ERROR
    if _ORACLE is not None or _ORACLE_ERROR is not None:
        return _ORACLE, _ORACLE_ERROR
    try:
        from .reference import oracle  # type: ignore

        if not (hasattr(oracle, "score_sequence") or hasattr(oracle, "predict")):
            raise EngineNotReady(
                "pr_engine/reference/oracle.py 里找不到 score_sequence()/predict() 入口"
            )
        _ORACLE = oracle
        _ORACLE_ERROR = None
    except Exception as exc:  # noqa: BLE001 - 需要把任何加载失败都如实报给用户
        _ORACLE = None
        _ORACLE_ERROR = f"{type(exc).__name__}: {exc}"
    return _ORACLE, _ORACLE_ERROR


def _count_models_in_list(list_path) -> int:
    """从模型清单文件第一行读模型个数（N）。"""
    try:
        with open(list_path, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline().strip()
        return max(0, int(first.split()[0]))
    except Exception:  # noqa: BLE001
        return 0


def _model_counts() -> dict[str, int]:
    """统计每组可用模型个数。

    优先用参考实现自己的 model_info()；若它返回全 0（例如路径解析差异），
    退回直接读 Models_Short.txt / Models_Long.txt 的第一行。
    """
    root = Path(__file__).resolve().parent.parent
    fallback = {
        "short": _count_models_in_list(root / "Models_Short.txt"),
        "long": _count_models_in_list(root / "Models_Long.txt"),
    }
    oracle, _ = _load_oracle()
    if oracle is not None and hasattr(oracle, "model_info"):
        try:
            info = oracle.model_info()
            if isinstance(info, dict):
                short = int(info.get("short", 0) or 0)
                long_ = int(info.get("long", 0) or 0)
                if short > 0 or long_ > 0:
                    return {"short": short, "long": long_}
        except Exception:  # noqa: BLE001
            pass
    return fallback


def engine_status(lang: str = _i18n.DEFAULT_LANG) -> dict[str, Any]:
    """供 /api/status 使用：引擎是否可用、模型数量等。lang 决定 error 文案语言。"""
    lang = _i18n.normalize(lang)
    oracle, err = _load_oracle()
    counts = _model_counts()
    status: dict[str, Any] = {
        "ready": oracle is not None,
        "engine": "python-port",
        "version": "1.0",
        "threshold": DEFAULT_THRESHOLD,
        "short_max_len": SHORT_MAX_LEN,
        "max_batch_size": MAX_BATCH_SIZE,
        "max_sequence_length": MAX_SEQUENCE_LENGTH,
        "models": counts,
    }
    if oracle is None:
        status["error"] = _i18n.msg(lang, "err.engine_not_ready", error=err)
    return status


def _call_oracle(oracle: Any, sequence: str, model_kind: str) -> float:
    """调用参考实现，兼容几种可能的方法签名。"""
    fn: Callable[..., Any] | None = getattr(oracle, "score_sequence", None)
    if fn is not None:
        # 依次尝试带 models 关键字、带位置参数、只传序列三种签名
        try:
            return float(fn(sequence, models=model_kind))
        except TypeError:
            pass
        try:
            return float(fn(sequence, model_kind))
        except TypeError:
            pass
        return float(fn(sequence))

    fn = getattr(oracle, "predict", None)
    if fn is not None:
        try:
            out = fn(sequence, model_kind)
        except TypeError:
            out = fn(sequence)
        return _coerce_score(out)
    raise EngineNotReady("参考实现没有可用的打分入口")


def _coerce_score(out: Any) -> float:
    """把参考实现的返回值归一化成 0~1 的标量分数。"""
    if isinstance(out, (int, float)):
        return float(out)
    if isinstance(out, dict):
        for key in ("score", "probability", "prob", "bioactivity"):
            if key in out:
                return float(out[key])
        if "output" in out:  # 输出向量：按 argmax 取对应分量作为概率
            vec = [float(x) for x in out["output"]]
            if vec:
                return float(max(vec))
        raise EngineNotReady(f"无法从参考实现返回的字典里取分数：{sorted(out)[:8]}")
    if isinstance(out, (list, tuple)) and out:
        vec = [float(x) for x in out]
        return float(max(vec))
    raise EngineNotReady(f"无法识别的参考实现返回值类型：{type(out).__name__}")


# --------------------------------------------------------------------------- #
# 输入清洗
# --------------------------------------------------------------------------- #

def normalize_sequence(raw: str, strict: bool = False) -> str:
    """把序列规整为大写字母串（去掉空白与不影响语义的分隔符）。

    strict=False（默认，推荐）做两件"善意修正"，都会产生警告、绝不静默：
      1. 小写字母视同对应的大写氨基酸。原程序对任意非法残基会在归一化时
         产生 `0/0`，整条序列的分数变成 **NaN**——所以 `rppgfspfr` 在原程序里
         是没有结果的，并不是"另一个分数"。
      2. `B/J/O/U/Z` 映射到 `X` 通道（索引 20）。这些是真实存在的歧义/非标准
         残基（Asx/Glx/硒代半胱氨酸/吡咯赖氨酸），当作未知残基比整条拒分更有用。
    strict=True：完全不改大小写、不做任何映射，**逐字复刻原二进制行为**
        （此时含小写或 B/J/O/U/Z 的序列会因 NaN 被上层跳过），用于严格比对。

    无论哪种模式，都**不会**丢弃数字或标点——那些字符由 _check_sequence 判定为
    非法并报错，避免把 "ILP1LS" 悄悄变成 "ILPLS" 这种"数据被改坏却看不出来"的问题。
    """
    if raw is None:
        return ""
    text = str(raw).replace("\ufeff", "")
    if not strict:
        text = text.upper()
        text = "".join(TO_X.get(ch, ch) for ch in text)
    for sep in (" ", "\t", "\r", "\n", "-", ".", "*", "_", "'"):
        text = text.replace(sep, "")
    return text


def _strict_sequence(raw: str, strict: bool = False) -> str | None:
    """严格校验一条**已经是单条序列**的输入；不合法返回 None。

    只看内容是否合法，不产生警告——警告由 _check_sequence 统一生成。
    """
    seq = normalize_sequence(raw, strict=strict).strip()
    if not seq or len(seq) > MAX_SEQUENCE_LENGTH:
        return None
    if any(not ch.isalpha() for ch in seq):
        return None
    return seq


def _is_sequence_cell(text: str) -> bool:
    """判断一段文本是否"看起来就是一条序列"（用于 CSV/表格里挑选序列列）。

    要求：至少 2 个字符、全是字母、长度不超过上限。
    这样 "ILP1LS" 不会被当成序列列，而 "PEPTIDE" 这种蛋白名会被选中后由
    _check_sequence 按"未知字母"如实警告。
    """
    t = str(text).strip()
    return 2 <= len(t) <= MAX_SEQUENCE_LENGTH and t.replace(" ", "").isalpha()


CSV_HEADER_WORDS = {
    "id", "no", "num", "index", "sequence", "sequences", "seq", "peptide", "peptides",
    "name", "label", "protein", "note", "notes", "remark", "comment", "description",
    "score", "length", "len", "source", "type", "category", "uniprot", "accession",
}
# 表头里明确表示"这一列是序列"的词
SEQ_COLUMN_WORDS = {"sequence", "sequences", "seq", "peptide", "peptides", "protein"}
# 表头里明确表示"这一列是标识符"的词
ID_COLUMN_WORDS = {"id", "no", "num", "index", "name", "label", "accession", "uniprot", "entry"}

_SPLIT_RE = re.compile(r"[,\t;]")


def _split_header(line: str) -> list[str]:
    return [f.strip().strip('"\'') for f in _SPLIT_RE.split(line) if f.strip()]


def _is_header_row(line: str) -> bool:
    """判断首行是否是表头：至少 2 个字段，且至少一个字段是已知表头词。"""
    fields = _split_header(line)
    return len(fields) >= 2 and any(f.lower() in CSV_HEADER_WORDS for f in fields)


def _header_columns(line: str) -> tuple[int | None, int | None]:
    """从表头解析出 (序列列下标, 标识符列下标)。"""
    seq_idx = id_idx = None
    for i, f in enumerate(_split_header(line)):
        low = f.lower().strip()
        if seq_idx is None and low in SEQ_COLUMN_WORDS:
            seq_idx = i
        elif id_idx is None and low in ID_COLUMN_WORDS:
            id_idx = i
    return seq_idx, id_idx


def _check_sequence(
    raw: str,
    label: str,
    warnings: list[str],
    strict: bool = False,
    lang: str = _i18n.DEFAULT_LANG,
) -> str | None:
    """校验单条序列并生成面向用户的警告；非法则返回 None（跳过）。

    非法字符一律报错跳过，绝不静默删除后继续打分。
    lang 决定警告文案的语言（zh / en），缺省中文。
    """
    seq = normalize_sequence(raw, strict=strict).strip()
    if not seq:
        warnings.append(_i18n.msg(lang, "warn.empty", label=label))
        return None
    if len(seq) > MAX_SEQUENCE_LENGTH:
        warnings.append(_i18n.msg(
            lang, "warn.too_long", label=label, length=len(seq), limit=MAX_SEQUENCE_LENGTH
        ))
        return None
    illegal = sorted({ch for ch in seq if not ch.isalpha()})
    if illegal:
        bad = "".join(illegal)[:20]
        warnings.append(_i18n.msg(lang, "warn.illegal_chars", label=label, chars=repr(bad)))
        return None

    # 以下警告都基于"用户原始输入"，而不是已经修正过的序列
    original = str(raw or "")
    if not strict:
        lowered = sorted({ch for ch in original if ch.islower()})
        if lowered:
            warnings.append(_i18n.msg(
                lang, "warn.lowercase", label=label, chars=repr("".join(lowered)[:20])
            ))
        mapped = sorted({ch for ch in original.upper() if ch in TO_X})
        if mapped:
            warnings.append(_i18n.msg(
                lang, "warn.ambiguous", label=label, chars=repr("".join(mapped))
            ))
    else:
        # strict 模式：凡是会让原程序得到 NaN 的字符都如实提示
        risky = sorted({ch for ch in original if ch.islower() or ch in TO_X})
        if risky:
            warnings.append(_i18n.msg(
                lang, "warn.risky_strict", label=label, chars=repr("".join(risky)[:20])
            ))
    if seq and all(ch == "X" for ch in seq):
        warnings.append(_i18n.msg(lang, "warn.all_x", label=label))
    return seq


# 行首"序号/标签"前缀：只有当剩余部分仍是一条合法序列时才会被去掉，
# 例如 "1  ILPILSLIGGLL" / "seq3: RPPGFSPFR"。绝不先删字符再打分。
LEADING_LABEL = re.compile(
    r"^\s*(?:(?:seq|sequence|pep|peptide|id|no|num|entry)\s*[:#.\-]?\s*)?\d+\s*[).:,\-]?\s+",
    re.IGNORECASE,
)


def parse_sequences(
    text: str,
    strict: bool = False,
    lang: str = _i18n.DEFAULT_LANG,
) -> tuple[list[SequenceItem], list[str]]:
    """解析多行文本 / FASTA / CSV（含表头）为序列列表。

    原则：**先解析结构，再严格校验**。任何情况下都不会"先删掉看不见的字符、
    再拿去打分"——含非法字符的行一律如实报错并跳过。
    支持的行形态：
      - 纯序列行                      ILPILSLIGGLL
      - FASTA 记录                    >pep1 描述 / RPPGFSPFR（同一条可跨多行）
      - 带序号/标签的前缀             1  ILPILSLIGGLL、seq3: RPPGFSPFR
      - CSV/TSV                       id,sequence,note / p1,RPPGFSPFR,test
    lang 决定警告文案语言（zh / en）。
    """
    lang = _i18n.normalize(lang)
    items: list[SequenceItem] = []
    warnings: list[str] = []
    pending_header: str | None = None
    header_checked = False
    seq_col: int | None = None      # 表头声明的序列列
    id_col: int | None = None       # 表头声明的标识符列
    part_buffer: list[str] = []     # FASTA 同一条记录的多行序列
    buffer_line = 0
    buffer_from_fasta = False       # 只有 FASTA 记录才允许多行拼接

    def flush_buffer() -> None:
        nonlocal part_buffer, buffer_line, buffer_from_fasta
        if not part_buffer:
            return
        merged = "".join(part_buffer)
        label = _i18n.msg(lang, "label.line", line=buffer_line)
        if pending_header:
            label = _i18n.msg(lang, "label.line_named", label=label, name=pending_header)
        checked = _check_sequence(merged, label, warnings, strict=strict, lang=lang)
        if checked is not None:
            items.append(
                SequenceItem(id=pending_header or f"seq{len(items) + 1}", sequence=checked)
            )
        part_buffer = []
        buffer_from_fasta = False

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue

        # CSV/TSV 表头（只可能在第一条有效行上）：解析出序列列/标识符列后跳过
        if not header_checked:
            header_checked = True
            if _is_header_row(line):
                seq_col, id_col = _header_columns(line)
                continue
            # 单列文本也可能以 "sequence" 之类的表头开头
            if _split_header(line)[0].lower() in SEQ_COLUMN_WORDS:
                continue

        # 兼容 "1  ILPILSLIGGLL" / "seq3: RPPGFSPFR" 这类带序号/标签的前缀：
        # 仅当去掉前缀后剩下的部分确实是一条合法序列时才采用
        stripped = line
        m = LEADING_LABEL.match(line)
        if m:
            rest = line[m.end():].strip()
            if _strict_sequence(rest, strict) is not None:
                stripped = rest

        # 按分隔符取字段（CSV / TSV / 表格）
        line_id: str | None = None
        if any(d in stripped for d in (",", "\t", ";")):
            fields = [f.strip().strip('"\'') for f in _SPLIT_RE.split(stripped) if f.strip()]
            if not fields:
                continue
            if seq_col is not None and seq_col < len(fields):
                candidate = fields[seq_col]
            else:
                # 没有表头时：优先挑"像序列"的字段；挑不到就退回第一个字段
                candidate = next((f for f in fields if _is_sequence_cell(f)), fields[0])
            if id_col is not None and id_col < len(fields):
                line_id = fields[id_col]
            elif not _is_sequence_cell(fields[0]) and fields[0] is not candidate:
                line_id = fields[0]
        else:
            candidate = stripped

        # FASTA 头
        if candidate.startswith(">"):
            flush_buffer()
            pending_header = candidate[1:].strip() or None
            continue

        if not candidate:
            continue

        # 纯序列行 / FASTA 序列分段
        seq = _strict_sequence(candidate, strict)
        if seq is not None and any(ch.isalpha() for ch in candidate):
            if pending_header is not None or part_buffer:
                # 只有 FASTA 记录允许多行拼接；CSV 每行都是独立记录
                if part_buffer and (not buffer_from_fasta or line_id is not None):
                    flush_buffer()
                if not part_buffer:
                    buffer_line = lineno
                if pending_header is None and line_id is not None:
                    pending_header = line_id
                part_buffer.append(candidate)
                buffer_from_fasta = buffer_from_fasta or (line_id is None)
                continue
            label = _i18n.msg(lang, "label.line", line=lineno)
            checked = _check_sequence(candidate, label, warnings, strict=strict, lang=lang)
            if checked is not None:
                seq_id = line_id or f"seq{len(items) + 1}"
                items.append(SequenceItem(id=seq_id, sequence=checked))
            continue

        # 落到这里说明这一行不合法：如实报错，绝不删字符后继续
        label = _i18n.msg(lang, "label.line", line=lineno)
        if pending_header:
            label = _i18n.msg(lang, "label.line_named", label=label, name=pending_header)
        if _check_sequence(candidate, label, warnings, strict=strict, lang=lang) is not None:
            # 理论上不会走到（上面已判定不合法），保险起见仍接受
            items.append(SequenceItem(id=pending_header or f"seq{len(items) + 1}", sequence=candidate))

    flush_buffer()
    return items, warnings


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #

def infer_model_kind(length: int, length_handling: str = "auto") -> str:
    if length_handling == "short":
        return "short"
    if length_handling == "long":
        return "long"
    return "short" if length <= SHORT_MAX_LEN else "long"


def score_sequences(
    items: Iterable[SequenceItem | dict[str, Any]],
    length_handling: str = "auto",
    threshold: float = DEFAULT_THRESHOLD,
    strict_case: bool = False,
    lang: str = _i18n.DEFAULT_LANG,
) -> BatchReport:
    """批量打分并按分数降序返回。

    strict_case=False（默认）：小写字母按大写处理（对用户更友好）。
    strict_case=True：逐字复刻原程序的大小写行为，用于严格比对。
    lang 决定逐条警告与错误文案的语言（zh / en）。
    """
    lang = _i18n.normalize(lang)
    started = time.perf_counter()
    report = BatchReport()

    oracle, err = _load_oracle()
    if oracle is None:
        raise EngineNotReady(_i18n.msg(lang, "err.engine_not_ready", error=err))

    normalized: list[SequenceItem] = []
    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict):
            seq_raw = item.get("sequence", "")
            sid = str(item.get("id") or f"seq{idx}")
        else:
            seq_raw = item.sequence
            sid = item.id or f"seq{idx}"
        label = f"{sid}"
        checked = _check_sequence(seq_raw, label, report.warnings, strict=strict_case, lang=lang)
        if checked is None:
            report.skipped += 1
            continue
        normalized.append(SequenceItem(id=sid, sequence=checked))

    if len(normalized) > MAX_BATCH_SIZE:
        raise SequenceError(_i18n.msg(
            lang, "err.too_many", limit=MAX_BATCH_SIZE, count=len(normalized)
        ))

    if not normalized:
        detail = report.warnings[0] if report.warnings else _i18n.msg(lang, "err.no_recognisable")
        raise SequenceError(_i18n.msg(lang, "err.no_sequences", detail=detail))

    scored: list[ScoreResult] = []
    for item in normalized:
        kind = infer_model_kind(len(item.sequence), length_handling)
        try:
            score = _call_oracle(oracle, item.sequence, kind)
        except Exception as exc:  # noqa: BLE001 - 单条失败不应中断整批
            report.warnings.append(_i18n.msg(
                lang, "warn.score_failed", label=item.id,
                error=f"{type(exc).__name__}: {exc}",
            ))
            report.skipped += 1
            continue
        if not math.isfinite(score):
            report.warnings.append(_i18n.msg(lang, "warn.not_finite", label=item.id))
            report.skipped += 1
            continue
        scored.append(
            ScoreResult(
                rank=0,
                id=item.id,
                sequence=item.sequence,
                length=len(item.sequence),
                score=score,
                model=kind,
            )
        )

    scored.sort(key=lambda r: (-r.score, r.id))
    for pos, res in enumerate(scored, start=1):
        res.rank = pos
    report.results = scored
    report.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return report


def results_to_csv(report: BatchReport) -> str:
    """导出 CSV（带 UTF-8 BOM，便于 Excel 直接打开）。"""
    import csv
    import io

    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(["rank", "id", "sequence", "length", "score", "model"])
    for r in report.results:
        writer.writerow([r.rank, r.id, r.sequence, r.length, f"{r.score:.4f}", r.model])
    return buf.getvalue()


def results_to_tsv(report: BatchReport) -> str:
    """复制到剪贴板用的 TSV。"""
    lines = ["rank\tid\tsequence\tlength\tscore\tmodel"]
    for r in report.results:
        lines.append(f"{r.rank}\t{r.id}\t{r.sequence}\t{r.length}\t{r.score:.4f}\t{r.model}")
    return "\n".join(lines)
