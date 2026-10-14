"""pr_engine 的界面文案多语言表（简体中文 / English）。

只有**会显示给最终用户**的文案放在这里（逐条警告、批量错误、服务端错误）；
面向开发者的内部诊断文本（异常类型名、文件路径等）仍保持原样，不在此表中。

用法：
    from pr_engine import i18n
    i18n.msg("en", "warn.empty", label="pep1")
    i18n.normalize("zh-Hans-CN")   # -> "zh"

设计要点：
  · 缺键/缺语言时回退到默认语言（zh），绝不抛异常——文案问题不应该让打分失败；
  · 占位符用 str.format，调用方给多少填多少；
  · 键集合在两种语言之间必须一致（tests 会核对）。
"""

from __future__ import annotations

SUPPORTED: tuple[str, ...] = ("zh", "en")
DEFAULT_LANG = "zh"

MESSAGES: dict[str, dict[str, str]] = {
    # ---------------- 位置标签 ----------------
    "label.line": {
        "zh": "第 {line} 行",
        "en": "line {line}",
    },
    "label.line_named": {
        "zh": "{label}（{name}）",
        "en": "{label} ({name})",
    },
    # ---------------- 逐条警告（_check_sequence） ----------------
    "warn.empty": {
        "zh": "{label}：序列为空，已跳过",
        "en": "{label}: empty sequence, skipped",
    },
    "warn.too_long": {
        "zh": "{label}：长度 {length} 超过上限 {limit}，已跳过",
        "en": "{label}: length {length} exceeds the limit of {limit}, skipped",
    },
    "warn.illegal_chars": {
        "zh": "{label}：含非法字符 {chars}，已跳过"
              "（序列只能包含氨基酸字母；该行内容未被改动，请修正后重试）",
        "en": "{label}: contains invalid character(s) {chars}, skipped "
              "(a sequence may only contain amino-acid letters; the line was NOT modified, "
              "please fix it and retry)",
    },
    "warn.lowercase": {
        "zh": "{label}：含小写字母 {chars}，已按对应大写氨基酸处理"
              "（原程序对这类输入会得到 NaN，即无结果）",
        "en": "{label}: contains lowercase letter(s) {chars}, treated as the corresponding "
              "uppercase residues (the original program yields NaN, i.e. no result, for such input)",
    },
    "warn.ambiguous": {
        "zh": "{label}：歧义残基 {chars} 已按未知残基 X 处理"
              "（原程序会因 0/0 得到 NaN，即无结果）",
        "en": "{label}: ambiguous residue(s) {chars} treated as the unknown residue X "
              "(the original program gets 0/0 → NaN, i.e. no result)",
    },
    "warn.risky_strict": {
        "zh": "{label}：含 {chars}，原程序会得到 NaN，本条已跳过",
        "en": "{label}: contains {chars}; the original program yields NaN, so this entry was skipped",
    },
    "warn.all_x": {
        "zh": "{label}：整条序列都是未知残基 X，分数仅供参考",
        "en": "{label}: the whole sequence is the unknown residue X; the score is indicative only",
    },
    "warn.score_failed": {
        "zh": "{label}：打分失败（{error}），已跳过",
        "en": "{label}: scoring failed ({error}), skipped",
    },
    "warn.not_finite": {
        "zh": "{label}：得到非有限分数，已跳过",
        "en": "{label}: produced a non-finite score, skipped",
    },
    # ---------------- 批量错误 ----------------
    "err.no_sequences": {
        "zh": "没有任何可打分的序列：{detail}",
        "en": "No scorable sequences: {detail}",
    },
    "err.no_recognisable": {
        "zh": "没有可识别的氨基酸序列",
        "en": "no recognisable amino-acid sequence",
    },
    "err.too_many": {
        "zh": "一次最多打分 {limit} 条，当前 {count} 条",
        "en": "At most {limit} sequences per request; got {count}",
    },
    "err.engine_not_ready": {
        "zh": "推理引擎未就绪：{error}",
        "en": "Inference engine not ready: {error}",
    },
    # ---------------- 服务端（app/server.py） ----------------
    "srv.body_not_utf8": {
        "zh": "请求体不是合法 UTF-8：{error}",
        "en": "Request body is not valid UTF-8: {error}",
    },
    "srv.body_not_json": {
        "zh": "请求体不是合法 JSON：{error}",
        "en": "Request body is not valid JSON: {error}",
    },
    "srv.body_must_be_object": {
        "zh": "请求体必须是 JSON 对象",
        "en": "Request body must be a JSON object",
    },
    "srv.content_length_invalid": {
        "zh": "Content-Length 非法",
        "en": "Invalid Content-Length",
    },
    "srv.body_too_large": {
        "zh": "请求体过大（{length} 字节，上限 {limit}）",
        "en": "Request body too large ({length} bytes; limit {limit})",
    },
    "srv.unknown_api": {
        "zh": "未知接口：{path}",
        "en": "Unknown endpoint: {path}",
    },
    "srv.bad_length_handling": {
        "zh": "length_handling 只能是 auto / short / long",
        "en": "length_handling must be auto / short / long",
    },
    "srv.no_sequences": {
        "zh": "没有可打分的序列：请至少提供一条只含氨基酸字母的序列",
        "en": "No scorable sequences: provide at least one sequence made of amino-acid letters only",
    },
    "srv.sequences_type": {
        "zh": "sequences 必须是数组，或提供 text 字段",
        "en": "sequences must be an array, or supply a text field",
    },
    "srv.item_missing_sequence": {
        "zh": "sequences[{index}] 缺少 sequence 字段",
        "en": "sequences[{index}] is missing the sequence field",
    },
    "srv.item_bad_type": {
        "zh": "sequences[{index}] 类型不支持：{type}",
        "en": "sequences[{index}] has an unsupported type: {type}",
    },
    "srv.score_failed": {
        "zh": "打分过程出错：{error}",
        "en": "Scoring failed: {error}",
    },
    "srv.export_format": {
        "zh": "目前只支持 format=csv",
        "en": "Only format=csv is supported",
    },
    "srv.static_not_found": {
        "zh": "静态文件不存在：{path}",
        "en": "Static file not found: {path}",
    },
    "srv.path_forbidden": {
        "zh": "禁止访问该路径",
        "en": "Access to this path is forbidden",
    },
    "srv.stopping": {
        "zh": "服务正在停止，现在可以关闭此页面了",
        "en": "The service is shutting down; you can close this page now",
    },
}


def normalize(value: object) -> str:
    """把任意语言标签归一化成受支持的语言码；无法判断时返回默认语言。

    >>> normalize("zh-CN"), normalize("en-US"), normalize("ja"), normalize(None)
    ('zh', 'en', 'en', 'zh')
    """
    text = str(value or "").strip().lower()
    if not text:
        return DEFAULT_LANG
    if text == "zh" or text.startswith("zh-") or text.startswith("zh_"):
        return "zh"
    if text.startswith("zh"):
        return "zh"
    return "en"


def msg(lang: str, key: str, **kwargs: object) -> str:
    """取一条本地化文案。任何缺失（语言或键）都回退到默认语言，绝不抛异常。"""
    table = MESSAGES.get(key)
    if not table:
        return key
    template = table.get(lang) or table.get(DEFAULT_LANG) or key
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        # 占位符没给全时原样返回，避免因为文案问题打断打分
        return template


def key_diff() -> dict[str, list[str]]:
    """两种语言缺失的键（供自测核对；正常应为空）。"""
    return {
        "missing_en": sorted(k for k, v in MESSAGES.items() if "en" not in v),
        "missing_zh": sorted(k for k, v in MESSAGES.items() if "zh" not in v),
        "keys": sorted(MESSAGES),
    }
