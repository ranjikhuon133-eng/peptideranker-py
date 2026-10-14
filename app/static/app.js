'use strict';
/* =============================================================================
 * PeptideRanker · 肽活性打分 —— 前端逻辑
 *
 * 纯原生 JavaScript：无构建步骤、无框架、无 CDN、无外部依赖。
 *
 * 冻结的 HTTP 接口契约（服务地址 http://127.0.0.1:8737）：
 *   GET  /api/status  -> {ready, engine, models:{short,long}, threshold, version} | {ready:false,error}
 *   POST /api/score   请求 {sequences:[{id,sequence}], length_handling:"auto"|"short"|"long"}
 *                     -> {results:[{rank,id,sequence,length,score,model}], warnings:[], summary:{}, histogram:[], elapsed_ms}
 *   POST /api/export  请求同 /api/score + {format:"csv"}
 *                     -> 200 text/csv; charset=utf-8 + Content-Disposition 附件
 *
 * 页面通过 URL 查询参数 ?api=<base> 可覆盖服务地址（便于用 mock 服务自测）；
 * 不传时：页面本身由 8737 端口提供则同源访问，否则按契约直连 127.0.0.1:8737。
 *
 * 多语言：i18n.js 必须在本文件之前加载，提供全局 PR_I18N；
 *         页面上出现的每一段文案都通过 t(key, params) 取，不留硬编码。
 * ========================================================================== */

/* ============================ 多语言接入 ================================== */

/* i18n.js 缺失时 t() 退化成返回键名：页面不会白屏，缺哪条文案一眼可见。 */
var I18N = (typeof PR_I18N !== 'undefined' && PR_I18N) ? PR_I18N : null;

function t(key, params) { return I18N ? I18N.t(key, params) : key; }

/* ============================ 常量与配置 ================================== */

var API_PORT = 8737;
var API_FALLBACK_BASE = 'http://127.0.0.1:' + API_PORT;

var DEFAULT_THRESHOLD = 0.5;
var DEFAULT_LENGTH_HANDLING = 'auto';

/* 非法行（含非 A-Z 字符）在前端直接跳过，不上送后端；
 * 后端 /api/score 本身也会校验并回传 warnings，两者不冲突。 */
var SEND_INVALID_LINES = false;

var MAX_FILE_BYTES = 5 * 1024 * 1024;
var ALLOWED_FILE_EXT = ['.txt', '.fasta', '.fa', '.fna', '.csv'];
var HIST_BUCKETS = 10;

var RE_LETTER = /[A-Za-z]/;
var RE_CLEAN_SEQ = /^[A-Za-z]{2,}$/;

/* 载入示例：15 条（与仓库 testfile.txt 一致） */
var EXAMPLE_SEQUENCES = [
  'ILPILSLIGGLL',
  'RPPGFSPFR',
  'FLPIVGKLLSGLSGLL',
  'LLPIVGKLLSGLL',
  'ALLHHGLNCAKGVLA',
  'AGIRRPPGFSPLRIA',
  'RENSLPAGLSPLR',
  'RVISLPAGLSPFR',
  'EEERDEDEVIEEEVKRGLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC',
  'GLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC',
  'EQERDADEDEVVEEVKRGLWESIKNLGKKFALNIMEKLKCKFGGGCLP',
  'GLWESIKNLGKKFALNIMEKLKCKFGGGCLP',
  'EEERNADEEERRDDLEERDVEVEKRFLSLALAALPKLFCLIFKKC',
  'FLSLALAALPKLFCLIFKKC',
  'EEERNVDEERRDDPEERAVEVEKRILPILSLIGGLLGK'
].join('\n');

/* ============================== 全局状态 ================================== */

var state = {
  apiBaseOverride: null,
  status: null,           // /api/status 响应
  statusError: '',        // 连接失败时的原始信息
  idleExitMinutes: null,  // 服务端配置的“无访问自动退出”分钟数（0 = 不自动退出）
  heartbeatTimer: null,   // 心跳定时器（页面关闭后心跳停止，服务端据此自动退出）
  threshold: DEFAULT_THRESHOLD,
  entries: [],            // 解析出的全部条目 {id,sequence,valid,badChars,line}
  lineFlags: [],          // 逐行标记，用于输入框镜像高亮
  parseWarnings: [],      // 前端本地解析提示
  serverWarnings: [],     // 后端 warnings
  formatLabel: '',        // 输入格式标签，由 parseSequences 按当前语言生成
  results: [],
  summary: null,
  histogram: [],
  elapsedMs: null,
  sortKey: 'score',
  sortDir: 'desc',
  filter: 'all',
  loading: false,
  hasScored: false,
  errorSource: ''
};

var el = {};

/* ============================== 小工具 ==================================== */

function $(id) { return document.getElementById(id); }

function escapeHtml(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function icon(name, cls) {
  return '<svg class="icon' + (cls ? ' ' + cls : '') + '" aria-hidden="true"><use href="#' + name + '"></use></svg>';
}

function clamp01(v) { return v < 0 ? 0 : (v > 1 ? 1 : v); }

function fmt4(value) {
  if (value === null || value === undefined || value === '') return '—';
  var n = Number(value);
  return isFinite(n) ? n.toFixed(4) : '—';
}

function fmtInt(value) {
  if (value === null || value === undefined || value === '') return '—';
  var n = Number(value);
  return isFinite(n) ? String(Math.round(n)) : '—';
}

/* 分数 -> 色相（0 红 -> 130 绿） */
function scoreHue(score) {
  return Math.round(clamp01(Number(score) || 0) * 130);
}
function scoreGradient(score) {
  var h = scoreHue(score);
  return 'linear-gradient(90deg, hsl(' + h + ' 82% 42%), hsl(' + h + ' 90% 62%))';
}
function scoreColor(score) {
  return 'hsl(' + scoreHue(score) + ' 88% 64%)';
}

function badgeModel(model) {
  var m = String(model === null || model === undefined ? '' : model).trim();
  var low = m.toLowerCase();
  if (low === 'short' || low.indexOf('短') >= 0) {
    return '<span class="tag tag--short">' + escapeHtml(t('model.short')) + '</span>';
  }
  if (low === 'long' || low.indexOf('长') >= 0) {
    return '<span class="tag tag--long">' + escapeHtml(t('model.long')) + '</span>';
  }
  if (!m) return '<span class="tag">—</span>';
  return '<span class="tag">' + escapeHtml(m) + '</span>';
}

function debounce(fn, wait) {
  var timer = null;
  return function () {
    var args = arguments, self = this;
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () { timer = null; fn.apply(self, args); }, wait);
  };
}

/* ========================= 服务地址解析 =================================== */

var _apiBase = null;

function apiBase() {
  if (_apiBase !== null) return _apiBase;
  var base = API_FALLBACK_BASE;
  try {
    if (typeof location !== 'undefined' && location) {
      var override = null;
      if (location.search) {
        try { override = new URLSearchParams(location.search).get('api'); } catch (e) { override = null; }
      }
      if (override === 'same') {
        base = '';
      } else if (override) {
        base = String(override).replace(/\/+$/, '');
      } else if ((location.protocol === 'http:' || location.protocol === 'https:') &&
                 (location.port === String(API_PORT) || !location.port)) {
        base = '';                       // 页面由后端同源提供
      }
    }
  } catch (e) {
    base = API_FALLBACK_BASE;
  }
  _apiBase = base;
  return base;
}

function apiUrl(path) { return apiBase() + path; }

function apiDisplay() {
  var b = apiBase();
  if (b) return b;
  try { return location.origin; } catch (e) { return t('footer.sameOrigin'); }
}

/* ====================== HTTP 请求与错误归一化 ============================= */

function httpErrorFrom(status, statusText, text, payload) {
  var msg = '';
  if (payload && typeof payload.error === 'string' && payload.error) {
    msg = payload.error;                       // 错误文本优先取后端 error 字段
  } else if (payload && typeof payload.message === 'string' && payload.message) {
    msg = payload.message;
  } else {
    msg = t('err.http', { status: status, statusText: statusText ? ' ' + statusText : '' });
    if (text) msg += t('err.httpBody', { text: String(text).slice(0, 400) });
  }
  var err = new Error(String(msg).trim());
  err.httpStatus = status;
  err.payload = payload || null;
  return err;
}

async function requestJson(url, options) {
  var res;
  try {
    res = await fetch(url, options);
  } catch (e) {
    throw new Error(t('err.network', {
      url: url,
      msg: (e && e.message) ? e.message : t('err.networkReason'),
      port: API_PORT
    }));
  }
  var text = '';
  try { text = await res.text(); } catch (e) { text = ''; }
  var payload = null;
  if (text) { try { payload = JSON.parse(text); } catch (e) { payload = null; } }
  if (!res.ok) throw httpErrorFrom(res.status, res.statusText, text, payload);
  if (payload === null) {
    throw new Error(t('err.badJson', { status: res.status, text: String(text).slice(0, 200) }));
  }
  return payload;
}

/* ========================== 序列解析（纯函数） ============================ */

function splitCsvLine(line) {
  var out = [], cur = '', quoted = false;
  for (var i = 0; i < line.length; i++) {
    var ch = line[i];
    if (quoted) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else { quoted = false; }
      } else { cur += ch; }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ',') {
      out.push(cur); cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function badCharsOf(text) {
  var seen = Object.create(null), out = [];
  for (var i = 0; i < text.length; i++) {
    var ch = text[i];
    if (!RE_LETTER.test(ch) && !seen[ch]) { seen[ch] = 1; out.push(ch); }
  }
  return out;
}

function isCleanSequence(text) { return RE_CLEAN_SEQ.test(String(text).trim()); }

function warnSkipped(lineNo, ch) {
  return t('warn.lineBad', { line: lineNo, char: ch });
}

/**
 * 解析输入文本 -> {entries, warnings, lineFlags, formatLabel}
 * entries: [{id, sequence, valid, badChars, line, source}]
 * lineFlags: 与原始行一一对应的 {bad, chars} | null
 */
function parseSequences(text) {
  var raw = String(text === null || text === undefined ? '' : text).replace(/\r\n?/g, '\n').split('\n');
  var warnings = [];
  var entries = [];
  var lineFlags = new Array(raw.length).fill(null);
  var usedIds = Object.create(null);
  var autoCounter = 0;

  function blank(s) { return String(s).trim() === ''; }
  function firstToken(s) { return String(s).trim().split(/\s+/)[0] || ''; }

  function autoId() { autoCounter += 1; return 'seq' + autoCounter; }

  function uniqueId(candidate) {
    var base = candidate || autoId();
    if (!usedIds[base]) { usedIds[base] = 1; return base; }
    var n = usedIds[base] + 1;
    while (usedIds[base + '-' + n]) n++;
    usedIds[base] = n;
    usedIds[base + '-' + n] = 1;
    return base + '-' + n;
  }

  function pushEntry(opts) {
    var seq = String(opts.sequence || '');
    var bad = opts.badChars || [];
    if (!seq) return null;
    var entry = {
      id: opts.id || autoId(),
      sequence: seq.toUpperCase(),
      valid: bad.length === 0,
      badChars: bad,
      line: opts.line,
      source: opts.source || t('fmt.line')
    };
    if (!entry.id) entry.id = autoId();
    entries.push(entry);
    return entry;
  }

  /* ---------- 判断输入格式 ---------- */
  var nonEmpty = [];
  for (var i = 0; i < raw.length; i++) if (!blank(raw[i])) nonEmpty.push(i);
  var hasFasta = nonEmpty.some(function (i) { return String(raw[i]).trim().charAt(0) === '>'; });
  var commaRows = nonEmpty.filter(function (i) { return String(raw[i]).indexOf(',') >= 0; }).length;
  /* 单列 CSV 没有逗号，靠首行表头关键字识别（sequence / seq / peptide ...） */
  var CSV_SINGLE_HEAD = ['sequence', 'sequences', 'seq', 'peptide', 'peptides',
                         'peptide_sequence', 'peptides_sequence'];
  var firstLineWord = nonEmpty.length ? String(raw[nonEmpty[0]]).trim().toLowerCase() : '';
  var isCsv = !hasFasta && nonEmpty.length > 0 &&
              (commaRows >= Math.max(1, Math.ceil(nonEmpty.length * 0.6)) ||
               (nonEmpty.length > 1 && CSV_SINGLE_HEAD.indexOf(firstLineWord) >= 0));

  /* ---------- CSV / TSV 风格 ---------- */
  if (isCsv) {
    var rows = nonEmpty.map(function (i) { return { line: i, fields: splitCsvLine(String(raw[i])) }; });
    var SEQ_HEAD = { sequence: 1, sequences: 1, seq: 1, peptide: 1, peptides: 1, peptide_sequence: 1, peptides_sequence: 1 };
    var ID_HEAD = { id: 1, identifier: 1, name: 1, seq_id: 1, seqid: 1, label: 1, uniprot: 1, uniprot_id: 1, accession: 1 };

    var head = rows[0].fields.map(function (f) { return String(f).trim().toLowerCase(); });
    var hasSeqHead = head.some(function (h) { return SEQ_HEAD[h]; });
    var hasIdHead = head.some(function (h) { return ID_HEAD[h]; });
    var seqIdx = 0, idIdx = -1, startRow = 0;

    if (hasSeqHead || hasIdHead) {
      startRow = 1;
      seqIdx = hasSeqHead ? head.findIndex(function (h) { return SEQ_HEAD[h]; }) : (rows[0].fields.length > 1 ? 1 : 0);
      idIdx = hasIdHead ? head.findIndex(function (h) { return ID_HEAD[h]; }) : -1;
      if (idIdx === seqIdx) idIdx = -1;
    } else {
      // 无表头：默认首列；若首列不像序列而某后续列像序列，则把首个像序列的列当序列列
      var f0 = rows[0].fields;
      if (f0.length > 1 && !isCleanSequence(f0[0])) {
        var k = f0.findIndex(function (f) { return isCleanSequence(f); });
        if (k > 0) { seqIdx = k; idIdx = 0; }
      }
    }

    for (var r = startRow; r < rows.length; r++) {
      var fields = rows[r].fields;
      var cell = fields[seqIdx] === undefined ? '' : String(fields[seqIdx]).trim();
      if (cell === '') continue;
      var idCell = (idIdx >= 0 && fields[idIdx] !== undefined) ? String(fields[idIdx]).trim() : '';
      var badCell = badCharsOf(cell);
      if (badCell.length) {
        lineFlags[rows[r].line] = { bad: true, chars: badCell };
        warnings.push({ text: warnSkipped(rows[r].line + 1, badCell[0]), source: 'local' });
        pushEntry({ id: uniqueId(idCell), sequence: cell, badChars: badCell, line: rows[r].line + 1, source: 'CSV' });
      } else {
        pushEntry({ id: uniqueId(idCell), sequence: cell, badChars: [], line: rows[r].line + 1, source: 'CSV' });
      }
    }
    return { entries: entries, warnings: warnings, lineFlags: lineFlags, formatLabel: t('fmt.csv') };
  }

  /* ---------- 逐行 / FASTA ---------- */
  var header = null;      // 当前 FASTA 头
  var block = null;       // 当前 FASTA 块 {header, parts:[{line,text}]}

  function flushBlock() {
    if (!block) return;
    var hdr = block.header;
    var parts = block.parts;
    block = null;
    if (!parts.length) return;

    var bad = [], firstBadLine = -1, firstBadChar = '';
    for (var p = 0; p < parts.length; p++) {
      var chars = badCharsOf(parts[p].text);
      if (chars.length) {
        lineFlags[parts[p].line] = { bad: true, chars: chars };
        if (firstBadLine < 0) { firstBadLine = parts[p].line; firstBadChar = chars[0]; }
        bad = bad.concat(chars);
      }
    }
    var joined = parts.map(function (p) { return p.text; }).join('');
    if (firstBadLine >= 0) warnings.push({ text: warnSkipped(firstBadLine + 1, firstBadChar), source: 'local' });
    pushEntry({
      id: uniqueId(hdr ? firstToken(hdr) : ''),
      sequence: joined,
      badChars: bad,
      line: (firstBadLine >= 0 ? firstBadLine : parts[0].line) + 1,
      source: t('fmt.fasta')
    });
  }

  for (var li = 0; li < raw.length; li++) {
    var line = String(raw[li]);
    var trimmed = line.trim();
    if (trimmed === '') { flushBlock(); continue; }
    if (trimmed.charAt(0) === '>') {
      flushBlock();
      header = trimmed.slice(1).trim();
      lineFlags[li] = { bad: false, chars: [], fasta: true };
      continue;
    }
    if (header !== null) {
      if (!block) block = { header: header, parts: [] };
      block.parts.push({ line: li, text: trimmed });
    } else {
      var badLine = badCharsOf(trimmed);
      if (badLine.length) {
        lineFlags[li] = { bad: true, chars: badLine };
        warnings.push({ text: warnSkipped(li + 1, badLine[0]), source: 'local' });
      }
      pushEntry({ id: '', sequence: trimmed, badChars: badLine, line: li + 1, source: t('fmt.line') });
    }
  }
  flushBlock();

  return {
    entries: entries,
    warnings: warnings,
    lineFlags: lineFlags,
    formatLabel: hasFasta ? t('fmt.fasta') : t('fmt.line')
  };
}

function validEntries() {
  return state.entries.filter(function (e) { return e.valid; });
}

function buildPayload() {
  var list = SEND_INVALID_LINES ? state.entries : validEntries();
  return {
    sequences: list.map(function (e) { return { id: e.id, sequence: e.sequence }; }),
    length_handling: el.lengthHandling ? el.lengthHandling.value : DEFAULT_LENGTH_HANDLING,
    // 让后端用它来生成同语言的逐条提示（服务端 warnings 直接显示在提示框里）
    lang: currentLang()
  };
}

/* ========================== 结果归一化 / 统计 ============================= */

function normalizeResult(r, index) {
  var item = r || {};
  var score = Number(item.score);
  if (!isFinite(score)) score = null;
  var length = Number(item.length);
  if (!isFinite(length)) length = item.sequence ? String(item.sequence).length : 0;
  var rank = Number(item.rank);
  if (!isFinite(rank)) rank = index + 1;
  return {
    rank: rank,
    id: item.id === null || item.id === undefined ? '' : String(item.id),
    sequence: item.sequence === null || item.sequence === undefined ? '' : String(item.sequence),
    length: length,
    score: score,
    model: item.model === null || item.model === undefined ? '' : String(item.model)
  };
}

function computeSummary(results, threshold) {
  var scores = results.map(function (r) { return r.score; })
    .filter(function (v) { return typeof v === 'number' && isFinite(v); })
    .sort(function (a, b) { return a - b; });
  if (!scores.length) {
    return { count: results.length, mean: null, median: null, min: null, max: null, n_above_threshold: 0 };
  }
  var sum = scores.reduce(function (a, b) { return a + b; }, 0);
  var mid = Math.floor(scores.length / 2);
  var median = scores.length % 2 ? scores[mid] : (scores[mid - 1] + scores[mid]) / 2;
  return {
    count: results.length,
    mean: sum / scores.length,
    median: median,
    min: scores[0],
    max: scores[scores.length - 1],
    n_above_threshold: scores.filter(function (v) { return v >= threshold; }).length
  };
}

function computeHistogram(results, buckets) {
  var n = buckets || HIST_BUCKETS;
  var bins = [];
  for (var i = 0; i < n; i++) {
    bins.push({ lo: i / n, hi: (i + 1) / n, count: 0 });
  }
  results.forEach(function (r) {
    if (typeof r.score !== 'number' || !isFinite(r.score)) return;
    var s = clamp01(r.score);
    var idx = Math.min(n - 1, Math.floor(s * n));
    bins[idx].count += 1;
  });
  return bins;
}

/* ============================= 渲染：状态 ================================= */

function setStatusBadge(stateName, title, meta) {
  if (!el.statusBadge) return;
  el.statusBadge.setAttribute('data-state', stateName);
  el.statusTitle.textContent = title;
  el.statusMeta.textContent = meta || '';
  el.statusMeta.title = meta || '';
}

function renderStatus() {
  var s = state.status;
  if (state.statusError) {
    setStatusBadge('error', t('status.unreachable'), state.statusError);
    return;
  }
  if (!s) {
    setStatusBadge('loading', t('status.checking'), 'GET /api/status');
    return;
  }
  if (s.ready === true) {
    var models = s.models || {};
    var meta = [];
    meta.push(String(s.engine || 'engine'));
    if (s.version !== undefined && s.version !== null) meta.push('v' + s.version);
    if (models.short !== undefined) meta.push(t('status.modelsShort', { n: models.short }));
    if (models.long !== undefined) meta.push(t('status.modelsLong', { n: models.long }));
    meta.push(t('status.threshold', { th: Number(state.threshold).toFixed(2) }));
    setStatusBadge('ready', t('status.ready'), meta.join(' · '));
  } else {
    setStatusBadge('error', t('status.notReady'), String(s.error || t('status.readyFalse')));
  }
}

function setError(title, message, source) {
  state.errorSource = source || 'local';
  if (!el.errorBar) return;
  el.errorTitle.textContent = title;
  el.errorText.textContent = message || t('error.unknown');
  el.errorBar.hidden = false;
}

function clearError(source) {
  // 只清除同一来源的错误，避免状态轮询覆盖打分/导出错误
  if (source && state.errorSource && state.errorSource !== source) return;
  state.errorSource = '';
  if (el.errorBar) el.errorBar.hidden = true;
}

function showToast(message, kind, iconName) {
  if (!el.toast) return;
  el.toast.className = 'toast toast--' + (kind || 'info') + ' is-on';
  el.toast.innerHTML = icon(iconName || (kind === 'err' ? 'i-alert' : (kind === 'ok' ? 'i-check' : 'i-spark'))) +
    '<span>' + escapeHtml(message) + '</span>';
  el.toast.hidden = false;
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(function () {
    el.toast.classList.remove('is-on');
    setTimeout(function () { if (!el.toast.classList.contains('is-on')) el.toast.hidden = true; }, 260);
  }, 3200);
}

function setLoading(on) {
  state.loading = !!on;
  if (document.body) document.body.classList.toggle('is-loading', state.loading);
  if (el.scoreLabel) el.scoreLabel.textContent = t(state.loading ? 'input.starting' : 'input.start');
  updateButtons();
}

/* =========================== 渲染：输入区 ================================= */

function renderMirror(text) {
  if (!el.editorMirror) return;
  var lines = String(text === null || text === undefined ? '' : text).replace(/\r\n?/g, '\n').split('\n');
  var html = '';
  for (var i = 0; i < lines.length; i++) {
    var flag = state.lineFlags[i];
    var cls = 'ln';
    if (flag && flag.bad) cls += ' ln--bad';
    else if (flag && flag.fasta) cls += ' ln--fasta';
    var content = lines[i] === '' ? '\u200b' : escapeHtml(lines[i]);
    html += '<span class="' + cls + '">' + content + '</span>';
  }
  el.editorMirror.innerHTML = html;
  syncMirrorScroll();
}

function syncMirrorScroll() {
  if (!el.editorMirror || !el.seqInput) return;
  el.editorMirror.scrollTop = el.seqInput.scrollTop;
  el.editorMirror.scrollLeft = el.seqInput.scrollLeft;
}

function renderInputMeta() {
  var entries = state.entries;
  var total = entries.length;
  var valid = entries.filter(function (e) { return e.valid; }).length;
  var maxLen = entries.reduce(function (m, e) { return Math.max(m, e.sequence.length); }, 0);
  var badLines = state.lineFlags.filter(function (f) { return f && f.bad; }).length;

  if (el.statCount) el.statCount.textContent = t('stats.count', { n: total, max: maxLen });
  if (el.statValid) el.statValid.textContent = t('stats.valid', { n: valid });
  if (el.statInvalid) {
    el.statInvalid.hidden = badLines === 0;
    el.statInvalid.textContent = t('stats.invalid', { n: badLines });
  }
  if (el.statFormat) el.statFormat.textContent = t('stats.format', { fmt: state.formatLabel });
}

function renderWarnings() {
  if (!el.warnBox) return;
  var local = state.parseWarnings || [];
  var server = state.serverWarnings || [];
  var all = local.concat(server);
  if (!all.length) {
    el.warnBox.hidden = true;
    el.warnList.innerHTML = '';
    el.warnCount.textContent = '';
    return;
  }
  el.warnBox.hidden = false;
  el.warnCount.textContent = t('warn.count', { n: all.length });
  el.warnList.innerHTML = all.map(function (w) {
    var isServer = w.source === 'server';
    return '<li><span class="tag ' + (isServer ? 'tag--server' : 'tag--local') + '">' +
      escapeHtml(t(isServer ? 'warn.server' : 'warn.local')) + '</span>' +
      '<span>' + escapeHtml(w.text) + '</span></li>';
  }).join('');
}

function renderThresholdLabels() {
  var th = Number(state.threshold);
  var label = th.toFixed(2);
  if (el.sumAboveLabel) el.sumAboveLabel.textContent = t('overview.above', { th: label });
  if (el.segAbove) el.segAbove.textContent = '≥ ' + label;
  if (el.segBelow) el.segBelow.textContent = '< ' + label;
}

/* =========================== 渲染：概览 =================================== */

function renderSummary() {
  var ids = ['sumCount', 'sumMean', 'sumMedian', 'sumMax', 'sumMin', 'sumAbove'];
  if (!state.hasScored || !state.summary) {
    ids.forEach(function (id) { if (el[id]) el[id].textContent = '—'; });
    if (el.overviewMeta) el.overviewMeta.textContent = '—';
    if (el.sumCountHint) el.sumCountHint.textContent = '\u00a0';
    return;
  }
  var s = state.summary;
  if (el.sumCount) el.sumCount.textContent = fmtInt(s.count);
  if (el.sumCountHint) {
    el.sumCountHint.textContent = state.elapsedMs === null || state.elapsedMs === undefined
      ? '\u00a0' : t('overview.elapsed', { n: fmtInt(state.elapsedMs) });
  }
  if (el.sumMean) el.sumMean.textContent = fmt4(s.mean);
  if (el.sumMedian) el.sumMedian.textContent = fmt4(s.median);
  if (el.sumMax) el.sumMax.textContent = fmt4(s.max);
  if (el.sumMin) el.sumMin.textContent = fmt4(s.min);
  if (el.sumAbove) el.sumAbove.textContent = fmtInt(s.n_above_threshold);

  var shortN = state.results.filter(function (r) { return String(r.model).toLowerCase() === 'short'; }).length;
  var longN = state.results.filter(function (r) { return String(r.model).toLowerCase() === 'long'; }).length;
  if (el.overviewMeta) {
    el.overviewMeta.textContent = t('overview.shortLong', { short: shortN, long: longN }) +
      (state.elapsedMs === null || state.elapsedMs === undefined
        ? '' : ' · ' + t('overview.elapsed', { n: fmtInt(state.elapsedMs) }));
  }
}

/* ========================== 渲染：直方图 ================================== */

function renderHistogram() {
  if (!el.histogram) return;
  var bins = Array.isArray(state.histogram) ? state.histogram : [];
  bins = bins.filter(function (b) { return b && isFinite(Number(b.count)); });

  if (!state.hasScored || !bins.length) {
    el.histogram.innerHTML = '';
    el.histogram.hidden = true;
    if (el.histEmpty) el.histEmpty.hidden = false;
    if (el.histMeta) el.histMeta.textContent = '—';
    return;
  }
  el.histogram.hidden = false;
  if (el.histEmpty) el.histEmpty.hidden = true;

  var max = 1;
  bins.forEach(function (b) { max = Math.max(max, Number(b.count) || 0); });

  var th = Number(state.threshold);
  var cols = bins.map(function (b) {
    var count = Number(b.count) || 0;
    var lo = Number(b.lo), hi = Number(b.hi);
    var pct = Math.max(count > 0 ? 4 : 1.5, (count / max) * 100);
    var above = isFinite(hi) && hi > th && (isFinite(lo) ? lo >= th - 1e-9 : true);
    var cls = 'hist__bar' + (count === 0 ? ' hist__bar--zero' : (above ? ' hist__bar--above' : ''));
    var range = (isFinite(lo) ? lo.toFixed(1) : '?') + '–' + (isFinite(hi) ? hi.toFixed(1) : '?');
    return '<div class="hist__col" title="' + escapeHtml(t('hist.tip', { range: range, count: count })) + '">' +
      '<div class="hist__stack">' +
      '<span class="hist__count">' + count + '</span>' +
      '<span class="' + cls + '" style="height:' + pct.toFixed(1) + '%"></span>' +
      '</div>' +
      '<span class="hist__label">' + escapeHtml(isFinite(hi) ? hi.toFixed(1) : '') + '</span>' +
      '</div>';
  }).join('');

  var html = '<div class="hist__plot">' + cols + '</div>' +
    '<div class="hist__legend">' +
    '<i></i><span>' + escapeHtml(t('hist.legendBelow')) + '</span>' +
    '<i></i><span>' + escapeHtml(t('hist.legendAbove', { th: th.toFixed(2) })) + '</span>' +
    '</div>';
  el.histogram.innerHTML = html;
  if (el.histMeta) {
    el.histMeta.textContent = t('hist.binsPeakMeta', { n: bins.length, max: max });
  }
}

/* =========================== 渲染：结果表 ================================= */

function cmpValue(a, b, key) {
  switch (key) {
    case 'rank': return Number(a.rank) - Number(b.rank);
    case 'length': return Number(a.length) - Number(b.length);
    case 'score': {
      var x = (typeof a.score === 'number') ? a.score : -Infinity;
      var y = (typeof b.score === 'number') ? b.score : -Infinity;
      return x - y;
    }
    case 'id': return String(a.id).localeCompare(String(b.id), 'zh-Hans-CN', { numeric: true });
    case 'sequence': return String(a.sequence).localeCompare(String(b.sequence));
    case 'model': return String(a.model).localeCompare(String(b.model));
    default: return 0;
  }
}

function visibleResults() {
  var th = Number(state.threshold);
  var rows = state.results.slice();
  if (state.filter === 'above') rows = rows.filter(function (r) { return typeof r.score === 'number' && r.score >= th; });
  else if (state.filter === 'below') rows = rows.filter(function (r) { return !(typeof r.score === 'number' && r.score >= th); });

  var key = state.sortKey, sign = state.sortDir === 'asc' ? 1 : -1;
  rows.sort(function (a, b) {
    var d = cmpValue(a, b, key) * sign;
    if (d !== 0) return d;
    return Number(a.rank) - Number(b.rank);       // 稳定兜底：按原始排名
  });
  return rows;
}

function renderTable() {
  var rows = visibleResults();
  var th = Number(state.threshold);

  // 表头排序指示
  if (el.resultTable) {
    var ths = el.resultTable.querySelectorAll('th[data-sort]');
    for (var i = 0; i < ths.length; i++) {
      var key = ths[i].getAttribute('data-sort');
      if (key === state.sortKey) ths[i].setAttribute('aria-sort', state.sortDir === 'asc' ? 'ascending' : 'descending');
      else ths[i].removeAttribute('aria-sort');
    }
  }

  // 筛选标签计数
  if (el.segAbove || el.segBelow) {
    var aboveN = state.results.filter(function (r) { return typeof r.score === 'number' && r.score >= th; }).length;
    var belowN = state.results.length - aboveN;
    if (el.segAbove) el.segAbove.textContent = '≥ ' + th.toFixed(2) + ' (' + aboveN + ')';
    if (el.segBelow) el.segBelow.textContent = '< ' + th.toFixed(2) + ' (' + belowN + ')';
  }

  // 元信息
  if (el.resultMeta) {
    if (!state.hasScored) {
      el.resultMeta.innerHTML = escapeHtml(t('results.metaNone'));
    } else {
      var parts = [];
      parts.push(t('results.metaTotal', { n: state.results.length }));
      parts.push(t('results.metaShown', { n: rows.length }));
      parts.push(t('results.metaThreshold', { th: th.toFixed(2) }));
      if (state.elapsedMs !== null && state.elapsedMs !== undefined) {
        parts.push(t('results.metaElapsed', { n: fmtInt(state.elapsedMs) }));
      }
      if (state.serverWarnings.length) {
        parts.push(t('results.metaWarnings', { n: state.serverWarnings.length }));
      }
      el.resultMeta.innerHTML = parts.join('<span class="dot"> · </span>');
    }
  }

  // 空态
  if (!state.hasScored || !state.results.length) {
    if (el.tableWrap) el.tableWrap.hidden = true;
    if (el.resultBody) el.resultBody.innerHTML = '';
    if (el.resultsEmpty) {
      el.resultsEmpty.hidden = false;
      if (state.hasScored) {
        el.resultsEmpty.innerHTML = icon('i-alert', 'icon--xl') +
          '<strong>' + escapeHtml(t('results.emptyNoDataTitle')) + '</strong>' +
          '<span>' + escapeHtml(t('results.emptyNoDataBody')) + '</span>';
      } else {
        el.resultsEmpty.innerHTML = icon('i-spark', 'icon--xl') +
          '<strong>' + escapeHtml(t('results.emptyInitialTitle')) + '</strong>' +
          '<span>' + escapeHtml(t('results.emptyInitialBody')) + '</span>';
      }
    }
    updateButtons();
    return;
  }

  if (el.tableWrap) el.tableWrap.hidden = false;
  if (el.resultsEmpty) el.resultsEmpty.hidden = rows.length > 0;
  if (!rows.length) {
    el.resultBody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-mute);padding:26px">' +
      escapeHtml(t('results.emptyFiltered')) + '</td></tr>';
    updateButtons();
    return;
  }

  el.resultBody.innerHTML = rows.map(function (r) {
    var hasScore = typeof r.score === 'number';
    var pct = hasScore ? clamp01(r.score) * 100 : 0;
    var above = hasScore && r.score >= th;
    var rankCls = (r.rank >= 1 && r.rank <= 3) ? ' rank--' + r.rank : '';
    var svgColor = hasScore ? scoreColor(r.score) : 'var(--text-mute)';
    var grad = hasScore ? scoreGradient(r.score) : 'rgba(255,255,255,.15)';
    return '<tr' + (above ? ' class="row--above"' : '') + '>' +
      '<td><span class="rank' + rankCls + '">' + escapeHtml(r.rank) + '</span></td>' +
      '<td class="cell-id" title="' + escapeHtml(r.id) + '">' + escapeHtml(r.id || '—') + '</td>' +
      '<td class="cell-seq">' + escapeHtml(r.sequence) + '</td>' +
      '<td class="cell-num">' + escapeHtml(fmtInt(r.length)) + '</td>' +
      '<td><div class="score">' +
        '<span class="score__num" style="color:' + svgColor + '">' + fmt4(r.score) + '</span>' +
        '<span class="score__bar"><i style="width:' + pct.toFixed(2) + '%;background:' + grad + '"></i></span>' +
        (above ? '<span class="tag tag--threshold score__flag">≥' + th.toFixed(2) + '</span>' : '') +
      '</div></td>' +
      '<td>' + badgeModel(r.model) + '</td>' +
      '</tr>';
  }).join('');

  updateButtons();
}

function renderAll() {
  renderThresholdLabels();
  renderStatus();
  renderInputMeta();
  renderWarnings();
  renderSummary();
  renderHistogram();
  renderTable();
}

function updateButtons() {
  var ready = !!(state.status && state.status.ready === true);
  var hasValid = validEntries().length > 0;
  var hasResults = state.results.length > 0;

  if (el.scoreBtn) {
    el.scoreBtn.disabled = state.loading || !ready || !hasValid;
    el.scoreBtn.title = !ready ? t('btn.scoreDisabledTitle')
      : (!hasValid ? t('btn.scoreNeedsInputTitle') : 'POST /api/score（Ctrl + Enter）');
  }
  if (el.copyBtn) el.copyBtn.disabled = state.loading || !hasResults;
  if (el.exportBtn) {
    el.exportBtn.disabled = state.loading || !hasValid;
    el.exportBtn.title = hasValid ? t('btn.exportReadyTitle') : t('btn.exportNeedsInputTitle');
  }
  ['sampleBtn', 'fileBtn', 'clearInputBtn', 'clearBtn', 'recheckBtn', 'lengthHandling'].forEach(function (k) {
    if (el[k]) el[k].disabled = state.loading;
  });
}

/* ============================ 业务动作 ==================================== */

var readInputNow = function () {
  var text = el.seqInput ? el.seqInput.value : '';
  var parsed = parseSequences(text);
  state.entries = parsed.entries;
  state.parseWarnings = parsed.warnings;
  state.lineFlags = parsed.lineFlags;
  state.formatLabel = parsed.formatLabel;
  renderMirror(text);
  renderInputMeta();
  renderWarnings();
  updateButtons();
};
var scheduleReadInput = debounce(readInputNow, 70);

async function loadStatus(options) {
  var opts = options || {};
  if (!state.status) setStatusBadge('loading', t('status.checking'), 'GET /api/status');
  try {
    var data = await requestJson(apiUrl('/api/status'), { method: 'GET', cache: 'no-store' });
    state.status = data || {};
    state.statusError = '';
    if (typeof data.threshold === 'number' && isFinite(data.threshold)) state.threshold = data.threshold;
    if (typeof data.idle_exit_minutes === 'number' && isFinite(data.idle_exit_minutes)) {
      state.idleExitMinutes = data.idle_exit_minutes;
    }
    if (data.ready === true) {
      clearError('status');
      if (!opts.silent) { /* 静默刷新 */ }
    } else {
      setError(t('err.engineNotReady'), String(data.error || t('status.readyFalseDetail')), 'status');
    }
  } catch (e) {
    var payload = e && e.payload;
    if (payload && payload.ready === false) {
      // 后端以 503 + {ready:false,error} 表达“引擎未就绪”，按契约语义展示
      state.status = payload;
      state.statusError = '';
      setError(t('err.engineNotReady'), String(payload.error || e.message || t('status.readyFalse')), 'status');
    } else {
      state.status = { ready: false };
      state.statusError = e.message;
      setError(t('err.cannotConnect'), e.message, 'status');
    }
  }
  renderStatus();
  renderThresholdLabels();
  renderHistogram();
  renderTable();
  renderFooter();
  updateButtons();
}

function statusBlockReason() {
  if (state.statusError) return state.statusError;
  if (state.status && state.status.ready !== true) {
    return String(state.status.error || t('status.notReadyStatus'));
  }
  return t('err.engineNotReady');
}

async function runScore() {
  clearError();
  if (state.loading) return;

  if (!state.entries.length) {
    setError(t('err.noSequences'), t('err.noSequencesHint'), 'local');
    return;
  }
  var valid = validEntries();
  if (!valid.length) {
    setError(t('err.noValid'), t('err.noValidHint'), 'local');
    return;
  }
  if (!(state.status && state.status.ready === true)) {
    await loadStatus({ silent: true });
    if (!(state.status && state.status.ready === true)) {
      setError(t('err.engineNotReady'), statusBlockReason(), 'local');
      return;
    }
  }

  setLoading(true);
  try {
    var data = await requestJson(apiUrl('/api/score'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload())
    });

    var results = Array.isArray(data.results) ? data.results : [];
    state.results = results.map(normalizeResult);
    state.hasScored = true;
    state.elapsedMs = (typeof data.elapsed_ms === 'number') ? data.elapsed_ms : null;
    state.threshold = (state.status && typeof state.status.threshold === 'number') ? state.status.threshold : state.threshold;

    state.serverWarnings = (Array.isArray(data.warnings) ? data.warnings : []).map(function (w) {
      return { text: String(w), source: 'server' };
    });
    state.summary = (data.summary && typeof data.summary === 'object')
      ? data.summary : computeSummary(state.results, Number(state.threshold));
    var bins = Array.isArray(data.histogram) ? data.histogram : null;
    state.histogram = (bins && bins.length) ? bins : computeHistogram(state.results, HIST_BUCKETS);

    state.filter = 'all';
    state.sortKey = 'score';
    state.sortDir = 'desc';
    setActiveSeg('all');

    clearError('score');
    renderAll();
    showToast(state.serverWarnings.length
      ? t('toast.scoredWithWarn', { n: state.results.length, w: state.serverWarnings.length })
      : t('toast.scored', { n: state.results.length }), 'ok');
  } catch (e) {
    setError(t('err.scoreFailed'), e.message, 'score');
    showToast(t('toast.scoreFailed', { msg: e.message }), 'err');
    renderTable();
  } finally {
    setLoading(false);
  }
}

function csvEscape(value) {
  var s = String(value === null || value === undefined ? '' : value);
  if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

function withBom(buffer) {
  var bytes = new Uint8Array(buffer);
  if (bytes.length >= 3 && bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF) return bytes;
  var out = new Uint8Array(bytes.length + 3);
  out[0] = 0xEF; out[1] = 0xBB; out[2] = 0xBF;
  out.set(bytes, 3);
  return out;
}

function localCsvText() {
  var rows = state.results.slice().sort(function (a, b) { return Number(a.rank) - Number(b.rank); });
  var head = 'rank,id,sequence,length,score,model';
  var body = rows.map(function (r) {
    return [r.rank, csvEscape(r.id), csvEscape(r.sequence), r.length,
      (typeof r.score === 'number' ? r.score.toFixed(4) : ''), csvEscape(r.model)].join(',');
  });
  return head + '\n' + body.join('\n') + '\n';
}

function filenameFromDisposition(header) {
  if (!header) return '';
  var m = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (m) { try { return decodeURIComponent(m[1].trim().replace(/^"|"$/g, '')); } catch (e) { /* ignore */ } }
  m = /filename\s*=\s*"([^"]+)"/i.exec(header);
  if (m) return m[1].trim();
  m = /filename\s*=\s*([^;]+)/i.exec(header);
  if (m) return m[1].trim().replace(/^"|"$/g, '');
  return '';
}

function downloadBlob(blob, filename) {
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = filename || 'peptideranker_scores.csv';
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
}

async function runExport() {
  clearError();
  var valid = validEntries();
  if (!valid.length) {
    setError(t('err.exportNoSequences'), t('err.exportNoValidHint'), 'local');
    return;
  }
  setLoading(true);
  var payload = buildPayload();
  payload.format = 'csv';

  var res = null, networkError = null;
  try {
    res = await fetch(apiUrl('/api/export'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  } catch (e) {
    networkError = e;
  }

  try {
    if (res && res.ok) {
      var ctype = String(res.headers.get('Content-Type') || '').toLowerCase();
      if (ctype === '' || ctype.indexOf('csv') >= 0 || ctype.indexOf('text/plain') >= 0) {
        var buf = await res.arrayBuffer();
        var name = filenameFromDisposition(res.headers.get('Content-Disposition')) || 'peptideranker_scores.csv';
        downloadBlob(new Blob([withBom(buf)], { type: 'text/csv;charset=utf-8' }), name);
        clearError('export');
        showToast(t('toast.exportApi', { name: name }), 'ok');
        return;
      }
      // 200 但不是 CSV：退回本地生成
      showToast(t('toast.exportNotCsv'), 'info');
    } else if (res) {
      var text = '';
      try { text = await res.text(); } catch (e) { text = ''; }
      var payloadErr = null;
      try { payloadErr = JSON.parse(text); } catch (e) { payloadErr = null; }
      var err = httpErrorFrom(res.status, res.statusText, text, payloadErr);
      showToast(t('toast.exportApiError', { msg: err.message }), 'info');
    } else {
      showToast(t('toast.exportOffline'), 'info');
    }

    // 本地兜底：列与契约一致（rank,id,sequence,length,score,model），UTF-8 BOM
    var csvText = localCsvText();
    downloadBlob(new Blob([csvText], { type: 'text/csv;charset=utf-8' }), 'peptideranker_scores.csv');
    if (networkError) {
      setError(t('err.exportUnreachable'),
        t('err.exportUnreachableDetail', { msg: networkError.message }), 'export');
    }
  } catch (e) {
    setError(t('err.exportFailed'), e.message, 'export');
  } finally {
    setLoading(false);
  }
}

function fallbackCopy(text) {
  try {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', 'readonly');
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, text.length);
    var ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch (e) {
    return false;
  }
}

async function copyTsv() {
  var rows = visibleResults();
  if (!rows.length) {
    showToast(t('toast.noCopy'), 'info');
    return;
  }
  var lines = ['rank\tid\tsequence\tlength\tscore\tmodel'];
  rows.forEach(function (r) {
    lines.push([r.rank, r.id, r.sequence, r.length,
      (typeof r.score === 'number' ? r.score.toFixed(4) : ''), r.model].join('\t'));
  });
  var text = lines.join('\n');

  var copied = false;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try { await navigator.clipboard.writeText(text); copied = true; } catch (e) { copied = false; }
  }
  if (!copied) copied = fallbackCopy(text);

  if (copied) showToast(t('toast.copied', { n: rows.length }), 'ok');
  else setError(t('err.copyFailed'), t('err.copyFailedHint'), 'local');
}

function clearAll() {
  clearError();
  if (el.seqInput) el.seqInput.value = '';
  state.entries = [];
  state.parseWarnings = [];
  state.lineFlags = [];
  state.serverWarnings = [];
  state.results = [];
  state.summary = null;
  state.histogram = [];
  state.elapsedMs = null;
  state.hasScored = false;
  state.filter = 'all';
  state.sortKey = 'score';
  state.sortDir = 'desc';
  setActiveSeg('all');
  readInputNow();
  renderAll();
  showToast(t('toast.cleared'), 'info');
}

/* 整体替换输入（示例 / 文件）时丢弃上一轮结果，避免表格与当前输入不一致 */
function resetResults() {
  state.results = [];
  state.summary = null;
  state.histogram = [];
  state.elapsedMs = null;
  state.serverWarnings = [];
  state.hasScored = false;
  state.filter = 'all';
  setActiveSeg('all');
}

function loadSample() {
  clearError();
  if (!el.seqInput) return;
  el.seqInput.value = EXAMPLE_SEQUENCES;
  resetResults();
  readInputNow();
  renderAll();
  showToast(t('toast.sampleLoaded', { n: EXAMPLE_SEQUENCES.split('\n').length }), 'ok');
  el.seqInput.focus();
}

async function loadFile(file) {
  clearError();
  if (!file) return;
  var name = file.name || t('file.unnamed');
  var extMatch = /\.[^.\\/]+$/.exec(name);
  var ext = extMatch ? extMatch[0].toLowerCase() : '';
  var isText = String(file.type || '').indexOf('text/') === 0;
  if (ALLOWED_FILE_EXT.indexOf(ext) < 0 && !isText) {
    setError(t('err.fileType'),
      t('err.fileTypeDetail', { exts: ALLOWED_FILE_EXT.join(' / '), name: name }), 'local');
    return;
  }
  if (file.size > MAX_FILE_BYTES) {
    setError(t('err.fileTooLarge'),
      t('err.fileTooLargeDetail', { name: name, size: (file.size / 1048576).toFixed(1) }), 'local');
    return;
  }
  try {
    var text = await file.text();
    el.seqInput.value = String(text).replace(/\r\n?/g, '\n');
    resetResults();
    readInputNow();
    renderAll();
    showToast(t('toast.fileLoaded', { name: name, n: state.entries.length }), 'ok');
  } catch (e) {
    setError(t('err.fileRead'),
      t('err.fileReadDetail', { name: name, msg: (e && e.message) ? e.message : e }), 'local');
  }
}

function setActiveSeg(filter) {
  state.filter = filter;
  if (!el.filterGroup) return;
  var segs = el.filterGroup.querySelectorAll('.seg');
  for (var i = 0; i < segs.length; i++) {
    segs[i].classList.toggle('is-active', segs[i].getAttribute('data-filter') === filter);
  }
}

function setSort(key) {
  if (state.sortKey === key) {
    state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    state.sortKey = key;
    state.sortDir = (key === 'rank' || key === 'id' || key === 'sequence' || key === 'model') ? 'asc' : 'desc';
  }
  renderTable();
}

/* ============================== 事件绑定 ================================== */

function cacheEls() {
  el.progressBar = $('progressBar');
  el.langSwitch = $('langSwitch');
  el.statusBadge = $('statusBadge');
  el.statusTitle = $('statusTitle');
  el.statusMeta = $('statusMeta');
  el.recheckBtn = $('recheckBtn');
  el.errorBar = $('errorBar');
  el.errorTitle = $('errorTitle');
  el.errorText = $('errorText');
  el.errorCloseBtn = $('errorCloseBtn');
  el.inputCard = $('inputCard');
  el.dropZone = $('dropZone');
  el.dropHint = $('dropHint');
  el.editorMirror = $('editorMirror');
  el.seqInput = $('seqInput');
  el.fileInput = $('fileInput');
  el.fileBtn = $('fileBtn');
  el.sampleBtn = $('sampleBtn');
  el.clearInputBtn = $('clearInputBtn');
  el.statCount = $('statCount');
  el.statValid = $('statValid');
  el.statInvalid = $('statInvalid');
  el.statFormat = $('statFormat');
  el.warnBox = $('warnBox');
  el.warnCount = $('warnCount');
  el.warnList = $('warnList');
  el.lengthHandling = $('lengthHandling');
  el.scoreBtn = $('scoreBtn');
  el.scoreLabel = el.scoreBtn ? el.scoreBtn.querySelector('.btn__label') : null;
  el.overviewMeta = $('overviewMeta');
  el.sumCount = $('sumCount');
  el.sumCountHint = $('sumCountHint');
  el.sumMean = $('sumMean');
  el.sumMedian = $('sumMedian');
  el.sumMax = $('sumMax');
  el.sumMin = $('sumMin');
  el.sumAbove = $('sumAbove');
  el.sumAboveLabel = $('sumAboveLabel');
  el.histogram = $('histogram');
  el.histEmpty = $('histEmpty');
  el.histMeta = $('histMeta');
  el.filterGroup = $('filterGroup');
  el.segAbove = $('segAbove');
  el.segBelow = $('segBelow');
  el.copyBtn = $('copyBtn');
  el.exportBtn = $('exportBtn');
  el.clearBtn = $('clearBtn');
  el.resultMeta = $('resultMeta');
  el.tableWrap = $('tableWrap');
  el.resultTable = $('resultTable');
  el.resultBody = $('resultBody');
  el.resultsEmpty = $('resultsEmpty');
  el.footerApi = $('footerApi');
  el.toast = $('toast');
  el.quitBtn = $('quitBtn');
  el.quitModal = $('quitModal');
  el.quitConfirmBtn = $('quitConfirmBtn');
  el.quitCancelBtn = $('quitCancelBtn');
  el.quitCancelMask = $('quitCancelMask');
}

/* ============================ 界面语言切换 ================================ */

function currentLang() { return I18N ? I18N.lang() : 'zh'; }

/* 切换语言后必须重跑的东西：静态文案 -> 标题/页脚 -> 输入解析（格式标签与
   非法行警告是按语言生成的）-> 全部渲染。已算好的分数不需要重新打分。 */
function applyLanguage() {
  if (I18N) I18N.applyStatic(document);
  try { document.title = t('app.title'); } catch (e) { /* 无 document 时忽略 */ }
  syncLangSwitch();
  renderFooter();
  readInputNow();
  renderAll();
}

function syncLangSwitch() {
  if (!el.langSwitch) return;
  var segs = el.langSwitch.querySelectorAll('.seg');
  for (var i = 0; i < segs.length; i++) {
    segs[i].classList.toggle('is-active', segs[i].getAttribute('data-lang') === currentLang());
  }
}

function renderFooter() {
  if (!el.footerApi) return;
  var parts = [t('footer.api', { url: apiDisplay() })];
  if (typeof state.idleExitMinutes === 'number' && state.idleExitMinutes > 0) {
    parts.push(t('footer.idle', { n: state.idleExitMinutes }));
  }
  el.footerApi.textContent = parts.join(' · ');
}

/* ------------------------------------------------------------------ *
 * 退出程序 & 心跳
 *
 * 关掉浏览器**不会**自动关掉本机服务（服务是启动脚本那个窗口里的进程），
 * 所以这里做两件事：
 *   1. 提供「退出程序」按钮 -> 调 /api/shutdown，服务端停止并释放端口
 *   2. 页面开着时每 20 秒发一次心跳；页面关闭后心跳停止，服务端在
 *      idle_exit_minutes 分钟后自动退出（页脚会显示这个时间）
 * ------------------------------------------------------------------ */
function startHeartbeat() {
  function beat() {
    try {
      fetch(apiUrl('/api/heartbeat'), { cache: 'no-store' }).catch(function () {
        /* 服务已停止时忽略报错 */
      });
    } catch (e) { /* 忽略：心跳失败不应该影响页面 */ }
  }
  beat();
  state.heartbeatTimer = setInterval(beat, 20000);
}

function openQuitModal() {
  if (!el.quitModal) {
    // 没有弹层时退化为直接确认
    if (window.confirm(t('quit.confirmFallback'))) { doQuit(); }
    return;
  }
  el.quitModal.hidden = false;
  if (el.quitConfirmBtn) el.quitConfirmBtn.focus();
}

function closeQuitModal() {
  if (el.quitModal) el.quitModal.hidden = true;
}

function doQuit() {
  closeQuitModal();
  if (el.quitConfirmBtn) {
    el.quitConfirmBtn.disabled = true;
    el.quitConfirmBtn.textContent = t('quit.busy');
  }
  fetch(apiUrl('/api/shutdown'), { method: 'POST' })
    .then(function () { showQuitScreen(); })
    .catch(function () { showQuitScreen(); });
}

function showQuitScreen() {
  if (state.heartbeatTimer) { clearInterval(state.heartbeatTimer); state.heartbeatTimer = null; }
  var box = document.createElement('div');
  box.className = 'modal';
  box.innerHTML =
    '<div class="modal__mask"></div>' +
    '<div class="modal__box" role="dialog" aria-modal="true">' +
    '<svg class="icon icon--lg modal__icon"><use href="#i-check"></use></svg>' +
    '<h2>' + escapeHtml(t('quit.doneTitle')) + '</h2>' +
    '<p>' + escapeHtml(t('quit.doneBody')) + '</p>' +
    '<p class="modal__hint">' + t('quit.doneHintHtml') + '</p>' +
    '</div>';
  document.body.appendChild(box);
  if (el.quitBtn) el.quitBtn.disabled = true;
}

function bindEvents() {
  if (el.langSwitch) {
    el.langSwitch.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('.seg') : null;
      if (!btn) return;
      var code = btn.getAttribute('data-lang');
      if (!code || !I18N || code === currentLang()) { syncLangSwitch(); return; }
      I18N.setLang(code);                       // 触发 onChange -> applyLanguage()
      showToast(t('lang.switched', { lang: I18N.label() }), 'info');
    });
  }
  if (el.seqInput) {
    el.seqInput.addEventListener('input', scheduleReadInput);
    el.seqInput.addEventListener('scroll', syncMirrorScroll);
  }
  if (el.lengthHandling) {
    el.lengthHandling.addEventListener('change', function () {
      showToast(t('toast.lengthHandling', { value: el.lengthHandling.value }), 'info');
    });
  }
  if (el.scoreBtn) el.scoreBtn.addEventListener('click', runScore);
  if (el.sampleBtn) el.sampleBtn.addEventListener('click', loadSample);
  if (el.clearInputBtn) el.clearInputBtn.addEventListener('click', function () {
    if (!el.seqInput || el.seqInput.value === '') { showToast(t('toast.inputEmpty'), 'info'); return; }
    el.seqInput.value = '';
    readInputNow();
    el.seqInput.focus();
    showToast(t('toast.inputCleared'), 'info');
  });
  if (el.clearBtn) el.clearBtn.addEventListener('click', clearAll);
  if (el.copyBtn) el.copyBtn.addEventListener('click', copyTsv);
  if (el.exportBtn) el.exportBtn.addEventListener('click', runExport);
  if (el.recheckBtn) el.recheckBtn.addEventListener('click', function () {
    state.status = null;
    loadStatus();
  });
  if (el.errorCloseBtn) el.errorCloseBtn.addEventListener('click', function () { clearError(); });
  if (el.quitBtn) el.quitBtn.addEventListener('click', openQuitModal);
  if (el.quitConfirmBtn) el.quitConfirmBtn.addEventListener('click', doQuit);
  if (el.quitCancelBtn) el.quitCancelBtn.addEventListener('click', closeQuitModal);
  if (el.quitCancelMask) el.quitCancelMask.addEventListener('click', closeQuitModal);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && el.quitModal && !el.quitModal.hidden) closeQuitModal();
  });
  if (el.fileBtn && el.fileInput) {
    el.fileBtn.addEventListener('click', function () { el.fileInput.click(); });
    el.fileInput.addEventListener('change', function () {
      var f = el.fileInput.files && el.fileInput.files[0];
      if (f) loadFile(f);
      el.fileInput.value = '';
    });
  }

  // 拖拽
  if (el.dropZone) {
    ['dragenter', 'dragover'].forEach(function (ev) {
      el.dropZone.addEventListener(ev, function (e) {
        e.preventDefault(); e.stopPropagation();
        el.dropZone.classList.add('is-dragging');
      });
    });
    el.dropZone.addEventListener('dragleave', function (e) {
      if (!el.dropZone.contains(e.relatedTarget)) el.dropZone.classList.remove('is-dragging');
    });
    el.dropZone.addEventListener('drop', function (e) {
      e.preventDefault(); e.stopPropagation();
      el.dropZone.classList.remove('is-dragging');
      var dt = e.dataTransfer;
      var f = dt && dt.files && dt.files[0];
      if (f) loadFile(f);
      else showToast(t('toast.dropNotFile'), 'info');
    });
  }
  // 避免整页拖放把文件当页面打开
  window.addEventListener('dragover', function (e) { e.preventDefault(); });
  window.addEventListener('drop', function (e) { e.preventDefault(); });

  // 筛选
  if (el.filterGroup) {
    el.filterGroup.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('.seg') : null;
      if (!btn) return;
      setActiveSeg(btn.getAttribute('data-filter'));
      renderTable();
    });
  }
  // 表头排序
  if (el.resultTable) {
    el.resultTable.querySelector('thead').addEventListener('click', function (e) {
      var th = e.target && e.target.closest ? e.target.closest('th[data-sort]') : null;
      if (!th) return;
      setSort(th.getAttribute('data-sort'));
    });
  }
  // 全局快捷键
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      runScore();
    }
  });
}

/* ================================ 启动 ==================================== */

function init() {
  cacheEls();
  if (I18N) {
    I18N.onChange(function () { applyLanguage(); });
    /* 首次访问的语言：URL 显式指定（?lang=，仅本次）> localStorage 记忆值
       > 浏览器语言 > 项目原始语言 */
    var forced = I18N.queryLang();
    I18N.setLang(forced || I18N.detect(), { transient: !!forced });
  }
  bindEvents();
  renderMirror('');
  applyLanguage();          // 静态文案 + 标题/页脚 + 首轮解析与渲染
  loadStatus();
  startHeartbeat();
}

if (typeof document !== 'undefined' && document) {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}
