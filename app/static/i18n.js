'use strict';
/* =============================================================================
 * PeptideRanker · 网页界面多语言（简体中文 / English）
 *
 * 纯原生 JavaScript：无构建步骤、无框架、无 CDN、无外部依赖。
 * 由 index.html 在 app.js 之前以普通 <script> 引入，对外暴露全局对象 PR_I18N。
 *
 * 语言选择优先级：
 *   1. localStorage['pr_lang']（用户上次的选择，跨会话记忆）
 *   2. navigator.languages / navigator.language（首次访问跟随浏览器）
 *   3. 项目原始语言 zh（无法判断时的兜底）
 *
 * 注意：第 2 步只在"真实浏览器环境"（存在 document）里生效。Node 自测环境下
 * 没有 document，直接落到第 3 步，这样单元测试的结果不会随宿主系统语言变化。
 *
 * 切换语言会写入 localStorage、更新 <html lang>，并通知所有订阅者，
 * 页面即时重渲染（含动态提示、表头、错误条），不需要刷新。
 *
 * 字典约定：
 *   · 文案里的 {name} 由 t(key, params) 替换；
 *   · 含 HTML 标签的文案（如 <b>…</b>）只用于 data-i18n-html 或 innerHTML 场景；
 *   · 中英两份字典的键集合必须完全一致（下方 selfCheck 会在自测中核对）。
 * ========================================================================== */

(function (root) {
  var STORAGE_KEY = 'pr_lang';
  var SUPPORTED = ['zh', 'en'];
  var FALLBACK = 'zh';                       // 项目原始语言
  var LANG_LABEL = { zh: '中文', en: 'English' };

  var DICT = {
    /* ======================= 简体中文 ======================= */
    zh: {
      /* --- 页面 / 品牌 --- */
      'app.title': 'PeptideRanker · 肽活性打分',
      'app.brandTag': '肽活性打分',
      'app.brandSub': '本地离线预测 · 短肽 / 长肽双模型 · 输出 0–1 活性概率',

      /* --- 语言切换 --- */
      'lang.groupAria': '界面语言',
      'lang.zhTitle': '切换到中文界面',
      'lang.enTitle': 'Switch to English',
      'lang.switched': '界面语言已切换为 {lang}',

      /* --- 顶栏状态徽章 --- */
      'status.checking': '正在检测引擎…',
      'status.retry': '重试连接',
      'status.retryTitle': '重新请求 /api/status',
      'status.ready': '引擎就绪',
      'status.unreachable': '引擎不可达',
      'status.notReady': '引擎未就绪',
      'status.readyFalse': '后端返回 ready=false',
      'status.readyFalseDetail': '后端返回 ready=false，但未提供 error 字段。',
      'status.notReadyStatus': '引擎未就绪（ready=false）',
      'status.modelsShort': '短肽 {n}',
      'status.modelsLong': '长肽 {n}',
      'status.threshold': '阈值 {th}',

      /* --- 退出程序 --- */
      'quit.button': '退出程序',
      'quit.buttonTitle': '停止本机打分服务并释放端口（等于关闭启动时那个命令行窗口）',
      'quit.title': '确定要退出程序吗？',
      'quit.bodyHtml': '退出后会停止本机的打分服务并释放端口，网页将无法继续使用（可直接关闭本页）。'
        + '下次要用时，重新双击文件夹里的 <b>启动网页.bat</b> 即可。',
      'quit.hint': '如果你只是想暂时离开、并不想关掉程序，直接关掉本页也行——'
        + '关掉网页后程序会在一段时间没有访问时自动退出。',
      'quit.cancel': '取消',
      'quit.confirm': '确定退出',
      'quit.busy': '正在退出…',
      'quit.confirmFallback': '确定要退出程序吗？退出后将停止本机服务。',
      'quit.doneTitle': '程序已退出',
      'quit.doneBody': '本机打分服务已停止，端口已释放。现在可以安全关闭此页面。',
      'quit.doneHintHtml': '下次使用时，重新双击文件夹里的 <b>启动网页.bat</b> 即可。',

      /* --- 错误条 --- */
      'error.title': '出错了',
      'error.close': '关闭',
      'error.unknown': '未知错误',

      /* --- 序列输入区 --- */
      'input.title': '序列输入',
      'input.loadSample': '载入示例',
      'input.chooseFile': '选择文件',
      'input.clear': '清空输入',
      'input.ariaLabel': '序列输入框',
      'input.placeholder': '每行一条序列（或粘贴 / 拖入 .txt/.fasta/.fa/.csv 文件）：\n'
        + 'ILPILSLIGGLL\nRPPGFSPFR\n>pep_03\nFLPIVGKLLSGLSGLL\n\n'
        + 'FASTA 头以 > 开头，用作序列 ID',
      'input.dropTitle': '松开鼠标以载入文件',
      'input.lengthLabel': '长度处理',
      'input.lengthAuto': 'auto · ≤20 走短肽模型',
      'input.lengthShort': 'short · 强制短肽模型',
      'input.lengthLong': 'long · 强制长肽模型',
      'input.start': '开始打分',
      'input.starting': '正在打分…',

      /* --- 输入统计 --- */
      'stats.count': '共 {n} 条序列，最长 {max}',
      'stats.valid': '合法 {n}',
      'stats.invalid': '非法 {n} 行',
      'stats.format': '格式：{fmt}',

      /* --- 输入格式名（解析结果标签） --- */
      'fmt.line': '逐行',
      'fmt.fasta': 'FASTA',
      'fmt.csv': 'CSV / 单列',

      /* --- 提示框 --- */
      'warn.title': '提示',
      'warn.count': '共 {n} 条',
      'warn.server': '服务端',
      'warn.local': '本地',
      'warn.lineBad': '第 {line} 行含非法字符 \'{char}\'，已跳过',

      /* --- 结果概览 --- */
      'overview.title': '结果概览',
      'overview.count': '序列数',
      'overview.mean': '平均分',
      'overview.median': '中位数',
      'overview.max': '最高分',
      'overview.min': '最低分',
      'overview.above': '≥ {th} 条数',
      'overview.elapsed': '耗时 {n} ms',
      'overview.shortLong': '短肽 {short} · 长肽 {long}',

      /* --- 直方图 --- */
      'hist.title': '分数分布',
      'hist.binsPeakMeta': '{n} 个等宽区间 · 峰值 {max} 条',
      'hist.empty': '暂无分布数据',
      'hist.legendBelow': '低于阈值',
      'hist.legendAbove': '≥ 阈值 {th}',
      'hist.tip': '{range}：{count} 条',

      /* --- 结果表 --- */
      'results.title': '排序结果',
      'results.filterAria': '按阈值筛选',
      'results.filterAll': '全部',
      'results.copy': '复制 TSV',
      'results.export': '导出 CSV',
      'results.clear': '清空',
      'results.metaNone': '尚未打分',
      'results.metaTotal': '共 <b>{n}</b> 条',
      'results.metaShown': '当前显示 <b>{n}</b> 条',
      'results.metaThreshold': '阈值 <b>{th}</b>',
      'results.metaElapsed': '耗时 <b>{n}</b> ms',
      'results.metaWarnings': '服务端提示 <b>{n}</b> 条',
      'results.emptyNoDataTitle': '没有可展示的结果',
      'results.emptyNoDataBody': '本次请求的结果为空，请检查输入序列是否全部被跳过。',
      'results.emptyInitialTitle': '还没有结果',
      'results.emptyInitialBody': '载入示例或粘贴序列，然后点击「开始打分」（快捷键 Ctrl + Enter）。',
      'results.emptyFiltered': '当前筛选下没有序列',

      /* --- 表头 --- */
      'table.rank': '排名',
      'table.id': 'ID',
      'table.sequence': '序列',
      'table.length': '长度',
      'table.score': '分数',
      'table.model': '模型',

      /* --- 模型标签 --- */
      'model.short': '短肽 · short',
      'model.long': '长肽 · long',

      /* --- 按钮 title（悬停提示） --- */
      'btn.scoreDisabledTitle': '引擎未就绪或不可达，无法打分',
      'btn.scoreNeedsInputTitle': '请先输入至少一条合法序列（仅允许 A–Z 字母）',
      'btn.exportReadyTitle': 'POST /api/export（format=csv）',
      'btn.exportNeedsInputTitle': '请先输入至少一条合法序列',

      /* --- 页脚 --- */
      'footer.contract': '接口契约：',
      'footer.api': '服务地址：{url}',
      'footer.idle': '无访问 {n} 分钟后自动退出',
      'footer.sameOrigin': '（同源）',

      /* --- 错误信息 --- */
      'err.network': '无法连接到后端服务 {url}（{msg}）。请确认服务已在 127.0.0.1:{port} 启动。',
      'err.networkReason': '网络错误',
      'err.http': 'HTTP {status}{statusText}',
      'err.httpBody': '：{text}',
      'err.badJson': '后端响应不是合法 JSON（HTTP {status}）：{text}',
      'err.engineNotReady': '引擎未就绪',
      'err.cannotConnect': '无法连接到后端服务',
      'err.noSequences': '没有可打分的序列',
      'err.noSequencesHint': '请粘贴序列、拖入文件或点击「载入示例」后再试。',
      'err.noValid': '没有合法序列',
      'err.noValidHint': '输入中的每一行都含非法字符（只允许 A–Z 字母），已全部跳过。',
      'err.scoreFailed': '打分失败',
      'err.exportNoSequences': '没有可导出的序列',
      'err.exportNoValidHint': '请先输入至少一条合法序列（仅允许 A–Z 字母）。',
      'err.exportFailed': '导出失败',
      'err.exportUnreachable': '导出接口不可达',
      'err.exportUnreachableDetail': 'POST /api/export 失败：{msg}（已改用本地生成 CSV）',
      'err.copyFailed': '复制失败',
      'err.copyFailedHint': '浏览器拒绝了剪贴板访问，请手动全选表格复制。',
      'err.fileType': '不支持的文件类型',
      'err.fileTypeDetail': '仅支持 {exts} 或纯文本文件，收到「{name}」。',
      'err.fileTooLarge': '文件过大',
      'err.fileTooLargeDetail': '「{name}」为 {size} MB，超出 5 MB 上限。',
      'err.fileRead': '文件读取失败',
      'err.fileReadDetail': '读取「{name}」时出错：{msg}',
      'file.unnamed': '未命名文件',

      /* --- Toast 提示 --- */
      'toast.scored': '打分完成：{n} 条结果',
      'toast.scoredWithWarn': '打分完成：{n} 条结果，{w} 条服务端提示',
      'toast.scoreFailed': '打分失败：{msg}',
      'toast.exportApi': '已调用 /api/export，开始下载 {name}',
      'toast.exportNotCsv': '导出接口返回了非 CSV 内容，已在本地生成',
      'toast.exportApiError': '导出接口不可用（{msg}），已在本地生成 CSV',
      'toast.exportOffline': '无法连接导出接口，已在本地生成 CSV',
      'toast.copied': '已复制 {n} 行（TSV，含表头）到剪贴板',
      'toast.noCopy': '当前没有可复制的结果',
      'toast.cleared': '已清空输入与结果',
      'toast.sampleLoaded': '已载入 {n} 条示例序列',
      'toast.fileLoaded': '已载入 {name}（识别 {n} 条序列）',
      'toast.lengthHandling': '长度处理已设为 {value}',
      'toast.inputEmpty': '输入区已经是空的',
      'toast.inputCleared': '已清空输入',
      'toast.dropNotFile': '拖入的内容不是文件'
    },

    /* ========================= English ======================== */
    en: {
      /* --- page / brand --- */
      'app.title': 'PeptideRanker · Peptide Bioactivity Scoring',
      'app.brandTag': 'Bioactivity Scorer',
      'app.brandSub': 'Runs fully offline · dual short/long-peptide models · outputs a 0–1 bioactivity probability',

      /* --- language switch --- */
      'lang.groupAria': 'Interface language',
      'lang.zhTitle': '切换到中文界面',
      'lang.enTitle': 'Switch to English',
      'lang.switched': 'Interface language set to {lang}',

      /* --- status badge --- */
      'status.checking': 'Checking engine…',
      'status.retry': 'Retry',
      'status.retryTitle': 'Request /api/status again',
      'status.ready': 'Engine ready',
      'status.unreachable': 'Engine unreachable',
      'status.notReady': 'Engine not ready',
      'status.readyFalse': 'Backend returned ready=false',
      'status.readyFalseDetail': 'The backend returned ready=false without an error field.',
      'status.notReadyStatus': 'Engine not ready (ready=false)',
      'status.modelsShort': 'short {n}',
      'status.modelsLong': 'long {n}',
      'status.threshold': 'threshold {th}',

      /* --- quit --- */
      'quit.button': 'Quit',
      'quit.buttonTitle': 'Stop the local scoring service and free the port (same as closing the console window)',
      'quit.title': 'Quit the program?',
      'quit.bodyHtml': 'This stops the local scoring service and frees the port, so this page will stop working '
        + '(you can simply close the tab). To use it again, double-click <b>启动网页.bat</b> in the folder.',
      'quit.hint': 'If you only want to step away without shutting the program down, just closing this page is fine — '
        + 'the program exits by itself after a period with no activity.',
      'quit.cancel': 'Cancel',
      'quit.confirm': 'Quit',
      'quit.busy': 'Quitting…',
      'quit.confirmFallback': 'Quit the program? The local service will be stopped.',
      'quit.doneTitle': 'Program quit',
      'quit.doneBody': 'The local scoring service has stopped and the port has been released. '
        + 'You can safely close this page now.',
      'quit.doneHintHtml': 'Next time, double-click <b>启动网页.bat</b> in the folder again.',

      /* --- error bar --- */
      'error.title': 'Something went wrong',
      'error.close': 'Close',
      'error.unknown': 'Unknown error',

      /* --- input card --- */
      'input.title': 'Sequence input',
      'input.loadSample': 'Load sample',
      'input.chooseFile': 'Choose file',
      'input.clear': 'Clear input',
      'input.ariaLabel': 'Sequence input box',
      'input.placeholder': 'One sequence per line (or paste / drop a .txt/.fasta/.fa/.csv file):\n'
        + 'ILPILSLIGGLL\nRPPGFSPFR\n>pep_03\nFLPIVGKLLSGLSGLL\n\n'
        + 'A FASTA header starts with > and is used as the sequence ID',
      'input.dropTitle': 'Release to load the file',
      'input.lengthLabel': 'Length handling',
      'input.lengthAuto': 'auto · ≤20 uses the short-peptide model',
      'input.lengthShort': 'short · force the short-peptide model',
      'input.lengthLong': 'long · force the long-peptide model',
      'input.start': 'Start scoring',
      'input.starting': 'Scoring…',

      /* --- input stats --- */
      'stats.count': '{n} sequences, longest {max}',
      'stats.valid': 'Valid {n}',
      'stats.invalid': '{n} invalid',
      'stats.format': 'Format: {fmt}',

      /* --- input format labels --- */
      'fmt.line': 'line-based',
      'fmt.fasta': 'FASTA',
      'fmt.csv': 'CSV / single column',

      /* --- warnings --- */
      'warn.title': 'Notice',
      'warn.count': '{n} total',
      'warn.server': 'Server',
      'warn.local': 'Local',
      'warn.lineBad': 'Line {line} contains an invalid character \'{char}\' and was skipped',

      /* --- overview --- */
      'overview.title': 'Result overview',
      'overview.count': 'Sequences',
      'overview.mean': 'Mean score',
      'overview.median': 'Median',
      'overview.max': 'Max score',
      'overview.min': 'Min score',
      'overview.above': '{th} or above',
      'overview.elapsed': '{n} ms',
      'overview.shortLong': 'short {short} · long {long}',

      /* --- histogram --- */
      'hist.title': 'Score distribution',
      'hist.binsPeakMeta': '{n} equal-width bins · peak {max}',
      'hist.empty': 'No distribution data yet',
      'hist.legendBelow': 'Below threshold',
      'hist.legendAbove': '≥ threshold {th}',
      'hist.tip': '{range}: {count}',

      /* --- results table --- */
      'results.title': 'Ranked results',
      'results.filterAria': 'Filter by threshold',
      'results.filterAll': 'All',
      'results.copy': 'Copy TSV',
      'results.export': 'Export CSV',
      'results.clear': 'Clear',
      'results.metaNone': 'Not scored yet',
      'results.metaTotal': '<b>{n}</b> in total',
      'results.metaShown': 'showing <b>{n}</b>',
      'results.metaThreshold': 'threshold <b>{th}</b>',
      'results.metaElapsed': '<b>{n}</b> ms',
      'results.metaWarnings': '<b>{n}</b> server notice(s)',
      'results.emptyNoDataTitle': 'Nothing to show',
      'results.emptyNoDataBody': 'This request returned no results — check whether every input sequence was skipped.',
      'results.emptyInitialTitle': 'No results yet',
      'results.emptyInitialBody': 'Load the sample or paste sequences, then click "Start scoring" (shortcut Ctrl + Enter).',
      'results.emptyFiltered': 'No sequences under the current filter',

      /* --- table headers --- */
      'table.rank': 'Rank',
      'table.id': 'ID',
      'table.sequence': 'Sequence',
      'table.length': 'Length',
      'table.score': 'Score',
      'table.model': 'Model',

      /* --- model tags --- */
      'model.short': 'short peptide',
      'model.long': 'long peptide',

      /* --- button tooltips --- */
      'btn.scoreDisabledTitle': 'The engine is not ready or unreachable, so scoring is unavailable',
      'btn.scoreNeedsInputTitle': 'Enter at least one valid sequence first (A–Z letters only)',
      'btn.exportReadyTitle': 'POST /api/export (format=csv)',
      'btn.exportNeedsInputTitle': 'Enter at least one valid sequence first',

      /* --- footer --- */
      'footer.contract': 'API contract:',
      'footer.api': 'Service address: {url}',
      'footer.idle': 'auto-exits after {n} min with no page',
      'footer.sameOrigin': '(same origin)',

      /* --- errors --- */
      'err.network': 'Cannot reach the backend service {url} ({msg}). '
        + 'Make sure the service is running on 127.0.0.1:{port}.',
      'err.networkReason': 'network error',
      'err.http': 'HTTP {status}{statusText}',
      'err.httpBody': ': {text}',
      'err.badJson': 'The backend response is not valid JSON (HTTP {status}): {text}',
      'err.engineNotReady': 'Engine not ready',
      'err.cannotConnect': 'Cannot connect to the backend service',
      'err.noSequences': 'No sequences to score',
      'err.noSequencesHint': 'Paste sequences, drop in a file, or click "Load sample" and try again.',
      'err.noValid': 'No valid sequences',
      'err.noValidHint': 'Every line contains an invalid character (only A–Z letters are allowed) and was skipped.',
      'err.scoreFailed': 'Scoring failed',
      'err.exportNoSequences': 'No sequences to export',
      'err.exportNoValidHint': 'Enter at least one valid sequence first (A–Z letters only).',
      'err.exportFailed': 'Export failed',
      'err.exportUnreachable': 'Export endpoint unreachable',
      'err.exportUnreachableDetail': 'POST /api/export failed: {msg} (fell back to a locally generated CSV)',
      'err.copyFailed': 'Copy failed',
      'err.copyFailedHint': 'The browser denied clipboard access — select the table and copy it manually.',
      'err.fileType': 'Unsupported file type',
      'err.fileTypeDetail': 'Only {exts} or plain-text files are supported; received "{name}".',
      'err.fileTooLarge': 'File too large',
      'err.fileTooLargeDetail': '"{name}" is {size} MB, over the 5 MB limit.',
      'err.fileRead': 'Could not read the file',
      'err.fileReadDetail': 'Error while reading "{name}": {msg}',
      'file.unnamed': 'untitled file',

      /* --- toasts --- */
      'toast.scored': 'Scoring finished: {n} result(s)',
      'toast.scoredWithWarn': 'Scoring finished: {n} result(s), {w} server notice(s)',
      'toast.scoreFailed': 'Scoring failed: {msg}',
      'toast.exportApi': 'Called /api/export, downloading {name}',
      'toast.exportNotCsv': 'The export endpoint returned non-CSV content; generated locally instead',
      'toast.exportApiError': 'Export endpoint unavailable ({msg}); generated locally instead',
      'toast.exportOffline': 'Could not reach the export endpoint; generated locally instead',
      'toast.copied': 'Copied {n} row(s) (TSV, with header) to the clipboard',
      'toast.noCopy': 'There is nothing to copy right now',
      'toast.cleared': 'Input and results cleared',
      'toast.sampleLoaded': 'Loaded {n} sample sequences',
      'toast.fileLoaded': 'Loaded {name} ({n} sequences detected)',
      'toast.lengthHandling': 'Length handling set to {value}',
      'toast.inputEmpty': 'The input box is already empty',
      'toast.inputCleared': 'Input cleared',
      'toast.dropNotFile': 'The dropped item is not a file'
    }
  };

  /* 服务端（pr_engine / server.py）随请求下发的 warnings 语言码。*/
  var current = '';

  /* ------------------------------ 内部工具 -------------------------------- */

  function isSupported(lang) { return SUPPORTED.indexOf(lang) >= 0; }

  /* 任意 BCP-47 语言标签 -> 受支持的两种语言之一（''=无法判断） */
  function normalize(value) {
    var v = String(value === null || value === undefined ? '' : value).trim().toLowerCase();
    if (!v) return '';
    if (v === 'zh' || v.indexOf('zh-') === 0 || v.indexOf('zh_') === 0) return 'zh';
    if (v.indexOf('zh') === 0) return 'zh';
    return 'en';
  }

  function readStored() {
    try {
      if (typeof localStorage === 'undefined' || !localStorage) return '';
      var stored = normalize(localStorage.getItem(STORAGE_KEY));
      return isSupported(stored) ? stored : '';
    } catch (e) {
      return '';                       // 隐私模式 / 禁用存储：忽略即可
    }
  }

  function writeStored(lang) {
    try {
      if (typeof localStorage === 'undefined' || !localStorage) return;
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (e) { /* 忽略 */ }
  }

  /* URL 上的 ?lang=zh / ?lang=en：显式指定本次访问的界面语言。
     用于分享链接、截图与浏览器自动化测试；只影响本次访问，不写入 localStorage。 */
  function queryLang() {
    try {
      if (typeof location === 'undefined' || !location || !location.search) return '';
      if (typeof URLSearchParams === 'undefined') return '';
      var raw = String(new URLSearchParams(String(location.search)).get('lang') || '')
        .trim().toLowerCase();
      if (!raw) return '';
      /* 只认明确写出的 zh / en（含 zh-CN、en-US 这类带地区的写法）；
         其它值一律忽略，避免把 ?lang=de 静默当成英文。 */
      if (raw === 'zh' || raw.indexOf('zh-') === 0 || raw.indexOf('zh_') === 0) return 'zh';
      if (raw === 'en' || raw.indexOf('en-') === 0 || raw.indexOf('en_') === 0) return 'en';
      return '';
    } catch (e) {
      return '';
    }
  }

  function detect() {
    var stored = readStored();
    if (stored) return stored;
    /* 只有真实浏览器环境才跟随浏览器语言；Node 自测环境退回项目原始语言，
       否则测试结果会随宿主系统语言变化。 */
    if (typeof document !== 'undefined' && document) {
      try {
        if (typeof navigator !== 'undefined' && navigator) {
          var list = (navigator.languages && navigator.languages.length)
            ? navigator.languages : [navigator.language];
          for (var i = 0; i < list.length; i++) {
            var hit = normalize(list[i]);
            if (isSupported(hit)) return hit;
          }
        }
      } catch (e) { /* 忽略 */ }
    }
    return FALLBACK;
  }

  /* {name} 占位替换；无参数时原样返回 */
  function format(template, params) {
    var out = String(template === null || template === undefined ? '' : template);
    if (!params) return out;
    return out.replace(/\{(\w+)\}/g, function (whole, name) {
      return Object.prototype.hasOwnProperty.call(params, name)
        ? String(params[name] === null || params[name] === undefined ? '' : params[name])
        : whole;
    });
  }

  /* ------------------------------ 对外 API -------------------------------- */

  var listeners = [];

  function t(key, params) {
    var table = DICT[current] || DICT[FALLBACK];
    var value = Object.prototype.hasOwnProperty.call(table, key) ? table[key] : null;
    if (value === null) {
      /* 缺键时依次退回：原始语言 -> 键名本身（便于一眼看出漏翻） */
      value = Object.prototype.hasOwnProperty.call(DICT[FALLBACK], key) ? DICT[FALLBACK][key] : String(key);
    }
    return format(value, params);
  }

  function lang() { return current; }

  /* 语言标签（用于 toast 显示“已切换为 中文 / English”） */
  function label(code) { return LANG_LABEL[code || current] || code || current; }

  /* 应用 index.html 上的静态文案：
       data-i18n             -> textContent（元素内不能再有图标等子节点）
       data-i18n-html        -> innerHTML（文案自身含 <b> 等标签）
       data-i18n-title       -> title 属性
       data-i18n-placeholder -> placeholder 属性
       data-i18n-aria-label  -> aria-label 属性
     注意：只按“单个属性选择器”逐个查询，因为自测用的 DOM 垫片不支持逗号选择器列表。 */
  var ATTR_MAP = [
    ['data-i18n', 'text'],
    ['data-i18n-html', 'html'],
    ['data-i18n-title', 'title'],
    ['data-i18n-placeholder', 'placeholder'],
    ['data-i18n-aria-label', 'aria-label']
  ];

  function applyStatic(doc) {
    var d = doc || (typeof document !== 'undefined' ? document : null);
    if (!d || !d.querySelectorAll) return;
    /* 每个属性单独查询：同一个元素可以同时带 data-i18n-placeholder 与
       data-i18n-aria-label，必须两个都应用，因此这里不做去重。 */
    for (var i = 0; i < ATTR_MAP.length; i++) {
      var attr = ATTR_MAP[i][0], mode = ATTR_MAP[i][1];
      var nodes = d.querySelectorAll('[' + attr + ']');
      for (var j = 0; j < nodes.length; j++) {
        var node = nodes[j];
        var value = t(node.getAttribute(attr));
        if (mode === 'text') node.textContent = value;
        else if (mode === 'html') node.innerHTML = value;
        else if (mode === 'title') node.setAttribute('title', value);
        else if (mode === 'placeholder') node.setAttribute('placeholder', value);
        else if (mode === 'aria-label') node.setAttribute('aria-label', value);
      }
    }
    /* <html lang> 供浏览器 / 读屏软件识别当前语言 */
    if (d.documentElement && d.documentElement.setAttribute) {
      d.documentElement.setAttribute('lang', current === 'zh' ? 'zh-CN' : 'en');
    }
  }

  /* 切换语言：写存储 -> 通知订阅者。同一语言重复调用不触发任何通知。 */
  function setLang(next, options) {
    var opts = options || {};
    var target = isSupported(next) ? next : FALLBACK;
    if (target === current) {
      if (!opts.silent) return current;
    }
    current = target;
    if (!opts.transient) writeStored(target);
    for (var i = 0; i < listeners.length; i++) {
      try { listeners[i](target); } catch (e) { /* 单个订阅者出错不影响其他 */ }
    }
    return current;
  }

  function onChange(fn) {
    if (typeof fn === 'function') listeners.push(fn);
    return fn;
  }

  /* 初始化：即使还没切过语言，也要立刻确定 current */
  current = FALLBACK;

  var api = {
    STORAGE_KEY: STORAGE_KEY,
    SUPPORTED: SUPPORTED,
    FALLBACK: FALLBACK,
    dict: DICT,
    t: t,
    format: format,
    lang: lang,
    label: label,
    detect: detect,
    queryLang: queryLang,
    setLang: setLang,
    onChange: onChange,
    applyStatic: applyStatic,
    normalize: normalize,
    /* 自测用：两种语言的键集合是否一致 */
    keyDiff: function () {
      var zh = Object.keys(DICT.zh), en = Object.keys(DICT.en);
      return {
        missingInEn: zh.filter(function (k) { return en.indexOf(k) < 0; }),
        missingInZh: en.filter(function (k) { return zh.indexOf(k) < 0; }),
        emptyValues: zh.concat(en).filter(function (k, i, arr) {
          return arr.indexOf(k) === i &&
            (!String(DICT.zh[k] || '').length || !String(DICT.en[k] || '').length);
        })
      };
    },
    /* 自测用：不依赖 localStorage 直接设定语言 */
    _reset: function (code) { current = isSupported(code) ? code : FALLBACK; }
  };

  root.PR_I18N = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof window !== 'undefined' ? window : this));
