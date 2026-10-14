/* PeptideRanker 前端浏览器端自测脚本（自测用，不属于产品代码）
 * 由 smoke.mjs 通过 CDP Runtime.evaluate 注入，定义 window.__PR_TESTS。
 * 全部断言基于真实 DOM，不依赖产品代码暴露任何测试钩子。
 */
window.__PR_TESTS = (function () {
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  function waitFor(fn, timeout) {
    var t0 = Date.now(), lim = timeout || 8000;
    return new Promise(function (resolve) {
      (function loop() {
        var v = false;
        try { v = fn(); } catch (e) { v = false; }
        if (v) return resolve(true);
        if (Date.now() - t0 > lim) return resolve(false);
        setTimeout(loop, 40);
      })();
    });
  }

  function mkReport() {
    var out = { pass: 0, fail: 0, steps: [] };
    return {
      out: out,
      ok: function (name, cond, extra) {
        out.steps.push({ name: name, pass: !!cond, extra: extra === undefined ? null : extra });
        if (cond) out.pass++; else out.fail++;
      },
      eq: function (name, actual, expected) {
        var pass = JSON.stringify(actual) === JSON.stringify(expected);
        out.steps.push({
          name: name, pass: pass,
          extra: pass ? null : { actual: actual, expected: expected }
        });
        if (pass) out.pass++; else out.fail++;
      }
    };
  }

  /* ------------------------------- DOM 读取器 ------------------------------ */
  var rows = function () { return $$('#resultBody tr'); };
  var rowAt = function (i) { return rows()[i] || null; };
  var txt = function (el) { return el ? el.textContent.trim() : null; };
  var rankOf = function (i) { var r = rowAt(i); return r ? txt(r.querySelector('.rank')) : null; };
  var idOf = function (i) { var r = rowAt(i); return r ? txt(r.children[1]) : null; };
  var seqOf = function (i) { var r = rowAt(i); return r ? txt(r.children[2]) : null; };
  var lenOf = function (i) { var r = rowAt(i); return r ? Number(txt(r.children[3])) : null; };
  var scoreOf = function (i) { var r = rowAt(i); return r ? txt(r.querySelector('.score__num')) : null; };
  var modelOf = function (i) { var r = rowAt(i); return r ? txt(r.children[5]) : null; };
  var barWidthOf = function (i) {
    var r = rowAt(i);
    var bar = r ? r.querySelector('.score__bar i') : null;
    return bar ? parseFloat(bar.style.width) : null;
  };
  var allScores = function () { return $$('#resultBody .score__num').map(function (n) { return parseFloat(n.textContent); }); };
  var allLengths = function () { return rows().map(function (r) { return Number(txt(r.children[3])); }); };

  var setInput = function (text) {
    var ta = $('#seqInput');
    ta.value = text;
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  };

  var isDesc = function (arr) { for (var i = 1; i < arr.length; i++) if (arr[i] > arr[i - 1]) return false; return true; };
  var isAsc = function (arr) { for (var i = 1; i < arr.length; i++) if (arr[i] < arr[i - 1]) return false; return true; };

  /* =============================== 主流程测试 ============================== */
  async function main() {
    var R = mkReport();
    var EXPECT = window.__EXPECT || { sampleCount: 15, maxLen: 0 };

    /* --- 渲染与引擎状态 --- */
    R.ok('页面基本骨架渲染', !!$('#seqInput') && !!$('#scoreBtn') && !!$('#resultBody') && !!$('#histogram'));
    R.ok('标题正确', /PeptideRanker/.test(document.title), document.title);
    R.ok('界面为中文', document.body.textContent.indexOf('开始打分') >= 0 && document.body.textContent.indexOf('结果概览') >= 0);
    R.ok('等待引擎就绪', await waitFor(function () { return $('#statusBadge').dataset.state === 'ready'; }, 8000));
    R.eq('状态徽章标题', txt($('#statusTitle')), '引擎就绪');
    R.ok('状态栏含双模型数量', txt($('#statusMeta')).indexOf('短肽 15') >= 0 && txt($('#statusMeta')).indexOf('长肽 15') >= 0, txt($('#statusMeta')));
    R.ok('状态栏含版本号', txt($('#statusMeta')).indexOf('v1.0') >= 0, txt($('#statusMeta')));
    R.ok('状态栏含阈值', txt($('#statusMeta')).indexOf('0.50') >= 0, txt($('#statusMeta')));
    R.ok('无错误条', $('#errorBar').hidden === true);
    R.ok('空输入时打分按钮禁用', $('#scoreBtn').disabled === true);
    R.ok('初始显示空态占位', $('#resultsEmpty').hidden === false && $('#tableWrap').hidden === true);

    /* --- 输入统计（实时） --- */
    setInput('ILPILSLIGGLL\nRPPGFSPFR');
    await sleep(220);
    R.eq('实时统计条数与最长', txt($('#statCount')), '共 2 条序列，最长 12');
    setInput('');
    await sleep(220);
    R.eq('清空后统计归零', txt($('#statCount')), '共 0 条序列，最长 0');

    /* --- 一键载入示例 --- */
    $('#sampleBtn').click();
    await waitFor(function () { return /共 15 条序列/.test(txt($('#statCount'))); }, 3000);
    R.eq('示例条数', txt($('#statCount')), '共 ' + EXPECT.sampleCount + ' 条序列，最长 ' + EXPECT.maxLen);
    R.eq('示例全部合法', txt($('#statValid')), '合法 ' + EXPECT.sampleCount);
    R.ok('无非法行时隐藏非法计数', $('#statInvalid').hidden === true);
    R.ok('格式识别为逐行', txt($('#statFormat')).indexOf('逐行') >= 0, txt($('#statFormat')));
    R.ok('镜像层按行渲染', $('#editorMirror').children.length >= EXPECT.sampleCount, $('#editorMirror').children.length);
    R.ok('载入示例后打分按钮可用', $('#scoreBtn').disabled === false);

    /* --- 打分 + 加载态 --- */
    $('#scoreBtn').click();
    R.ok('点击后立即进入加载态并禁用按钮', document.body.classList.contains('is-loading') && $('#scoreBtn').disabled === true);
    R.ok('等待结果渲染', await waitFor(function () { return rows().length === EXPECT.sampleCount; }, 10000));
    R.ok('加载态已复位', document.body.classList.contains('is-loading') === false);
    R.ok('表格已显示、空态已隐藏', $('#tableWrap').hidden === false && $('#resultsEmpty').hidden === true);
    R.eq('结果行数', rows().length, EXPECT.sampleCount);
    R.eq('排名从 1 开始且连续', [rankOf(0), rankOf(EXPECT.sampleCount - 1)], ['1', String(EXPECT.sampleCount)]);
    R.ok('分数按降序（契约要求）', isDesc(allScores()), allScores().slice(0, 4));
    R.ok('分数统一 4 位小数', allScores().every(function (v) { return /^\d+\.\d{4}$/.test(String(v)); }), allScores().slice(0, 3));
    R.ok('分数都在 0~1 之间', allScores().every(function (v) { return v >= 0 && v <= 1; }));
    R.ok('进度条宽度与分数一致', Math.abs(barWidthOf(0) - allScores()[0] * 100) < 0.6,
      { bar: barWidthOf(0), score: allScores()[0] });
    R.ok('模型标签与长度规则一致（≤20 短肽）', rows().every(function (r, i) {
      var len = lenOf(i), label = modelOf(i) || '';
      return len <= 20 ? label.indexOf('短肽') >= 0 : label.indexOf('长肽') >= 0;
    }));
    R.ok('阈值高亮与分数一致', rows().every(function (r, i) {
      var above = allScores()[i] >= 0.5;
      var hasClass = r.classList.contains('row--above');
      var hasTag = !!r.querySelector('.tag--threshold');
      return above === hasClass && above === hasTag;
    }));
    R.ok('存在 ≥0.5 的行', allScores().filter(function (v) { return v >= 0.5; }).length > 0);

    /* --- 概览卡片 --- */
    R.eq('概览：序列数', txt($('#sumCount')), String(EXPECT.sampleCount));
    var sc = allScores();
    R.eq('概览：最高分 = 首行分数', txt($('#sumMax')), sc[0].toFixed(4));
    R.eq('概览：最低分 = 末行分数', txt($('#sumMin')), sc[sc.length - 1].toFixed(4));
    var mean = sc.reduce(function (a, b) { return a + b; }, 0) / sc.length;
    R.ok('概览：平均分与本地计算一致', Math.abs(parseFloat(txt($('#sumMean'))) - mean) < 0.0002,
      { ui: txt($('#sumMean')), calc: mean.toFixed(4) });
    var sorted = sc.slice().sort(function (a, b) { return a - b; });
    var mid = Math.floor(sorted.length / 2);
    var median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    R.ok('概览：中位数与本地计算一致', Math.abs(parseFloat(txt($('#sumMedian'))) - median) < 0.0002,
      { ui: txt($('#sumMedian')), calc: median.toFixed(4) });
    R.eq('概览：≥阈值条数', txt($('#sumAbove')), String(sc.filter(function (v) { return v >= 0.5; }).length));
    R.ok('概览：非空态', txt($('#sumCount')) !== '—' && txt($('#sumMean')) !== '—');

    /* --- 直方图 --- */
    var cols = $$('#histogram .hist__col');
    R.eq('直方图 10 个区间', cols.length, 10);
    var histTotal = $$('#histogram .hist__count').reduce(function (a, n) { return a + Number(txt(n)); }, 0);
    R.eq('直方图计数总和 = 序列数', histTotal, EXPECT.sampleCount);
    R.ok('直方图有柱高', cols.some(function (c) { return parseFloat(c.querySelector('.hist__bar').style.height) > 4; }));

    /* --- 表头排序 --- */
    $('#resultTable thead th[data-sort="length"]').click();
    await sleep(60);
    R.ok('按长度降序', isDesc(allLengths()), allLengths().slice(0, 4));
    R.eq('长度表头 aria-sort=descending', $('#resultTable th[data-sort="length"]').getAttribute('aria-sort'), 'descending');
    $('#resultTable thead th[data-sort="length"]').click();
    await sleep(60);
    R.ok('再次点击切换为升序', isAsc(allLengths()), allLengths().slice(0, 4));
    R.eq('长度表头 aria-sort=ascending', $('#resultTable th[data-sort="length"]').getAttribute('aria-sort'), 'ascending');
    $('#resultTable thead th[data-sort="rank"]').click();
    await sleep(60);
    R.ok('按排名升序', isAsc(rows().map(function (r) { return Number(txt(r.querySelector('.rank'))); })));
    $('#resultTable thead th[data-sort="score"]').click();
    await sleep(60);
    R.ok('按分数降序（回到默认）', isDesc(allScores()), allScores().slice(0, 3));

    /* --- 快捷筛选 --- */
    var aboveN = Number(txt($('#sumAbove')));
    $('#filterGroup .seg[data-filter="above"]').click();
    await sleep(60);
    R.eq('筛选 ≥0.5 行数', rows().length, aboveN);
    R.ok('筛选 ≥0.5 全部达标', allScores().every(function (v) { return v >= 0.5; }), allScores());
    R.ok('筛选按钮处于激活态', $('#filterGroup .seg[data-filter="above"]').classList.contains('is-active'));
    $('#filterGroup .seg[data-filter="below"]').click();
    await sleep(60);
    R.eq('筛选 <0.5 行数', rows().length, EXPECT.sampleCount - aboveN);
    R.ok('筛选 <0.5 全部低于阈值', allScores().every(function (v) { return v < 0.5; }), allScores());
    R.eq('筛选标签显示计数', txt($('#segAbove')), '≥ 0.50 (' + aboveN + ')');
    $('#filterGroup .seg[data-filter="all"]').click();
    await sleep(60);
    R.eq('恢复全部', rows().length, EXPECT.sampleCount);

    /* --- 非法字符输入 --- */
    setInput('ILPILSLIGGLL\nRPPGF1SPFR\nFLPIVGKLLSGLSGLL');
    await sleep(250);
    R.eq('非法输入统计', txt($('#statCount')), '共 3 条序列，最长 16');
    R.eq('非法行计数', txt($('#statInvalid')), '非法 1 行');
    R.ok('非法行计数可见', $('#statInvalid').hidden === false);
    R.eq('镜像层标出非法行', $$('#editorMirror .ln--bad').length, 1);
    R.ok('出现本地解析提示', $('#warnBox').hidden === false && txt($('#warnList')).indexOf("第 2 行含非法字符 '1'，已跳过") >= 0,
      txt($('#warnList')));
    R.ok('提示带本地来源标签', !!$('#warnList .tag--local'));
    $('#scoreBtn').click();
    R.ok('非法行下仍能打分', await waitFor(function () { return rows().length === 2; }, 10000));
    R.eq('合法行数', rows().length, 2);
    R.ok('跳过行未出现在结果中', txt($('#resultBody')).indexOf('RPPGF1SPFR') < 0);

    /* --- Ctrl+Enter 快捷键 --- */
    setInput('RPPGFSPFR');
    await sleep(220);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true, cancelable: true }));
    R.ok('Ctrl+Enter 触发打分', await waitFor(function () { return rows().length === 1; }, 10000));
    R.eq('快捷键结果行数', rows().length, 1);
    R.eq('快捷键结果分数位数', String(scoreOf(0)).length, 6);

    /* --- 复制 TSV --- */
    $('#copyBtn').click();
    var copied = await waitFor(function () {
      var t = $('#toast');
      return !t.hidden && t.textContent.indexOf('已复制') >= 0;
    }, 3000);
    R.ok('复制 TSV 成功提示', copied, txt($('#toast')));
    var clip = null;
    try {
      if (navigator.clipboard && navigator.clipboard.readText) clip = await navigator.clipboard.readText();
    } catch (e) { clip = null; }
    if (clip) {
      /* Windows 剪贴板把换行写成 CRLF，先归一化再断言 */
      clip = clip.replace(/\r\n/g, '\n');
      var lines = clip.split('\n');
      R.eq('剪贴板首行为 TSV 表头', lines[0], 'rank\tid\tsequence\tlength\tscore\tmodel');
      R.eq('剪贴板数据行数', lines.length - 1, 1);
      R.ok('剪贴板分数为 4 位小数', /\t\d\.\d{4}\t/.test(clip), clip);
    } else {
      R.ok('剪贴板内容可读（无权限时跳过，已由提示覆盖）', true);
    }

    /* --- 重新载入示例并打分，准备导出与截图 --- */
    $('#sampleBtn').click();
    await sleep(220);
    $('#scoreBtn').click();
    await waitFor(function () { return rows().length === EXPECT.sampleCount; }, 10000);
    R.ok('再次打分成功', rows().length === EXPECT.sampleCount);
    return R.out;
  }

  /* ============================ 引擎未就绪 (ready=false) =================== */
  async function notReady() {
    var R = mkReport();
    R.ok('页面未白屏', !!$('#seqInput') && !!$('#scoreBtn') && !!$('#resultBody'));
    R.ok('等待错误状态', await waitFor(function () { return $('#statusBadge').dataset.state === 'error'; }, 8000));
    R.eq('徽章标题', txt($('#statusTitle')), '引擎未就绪');
    R.ok('错误条可见', $('#errorBar').hidden === false);
    R.eq('错误条标题', txt($('#errorTitle')), '引擎未就绪');
    R.ok('错误文本来自后端 error 字段', txt($('#errorText')).indexOf('模型文件缺失') >= 0, txt($('#errorText')));
    R.ok('错误条带 role=alert', $('#errorBar').getAttribute('role') === 'alert');
    $('#sampleBtn').click();
    await sleep(250);
    R.eq('载入示例仍可更新统计', txt($('#statCount')), '共 ' + window.__EXPECT.sampleCount + ' 条序列，最长 ' + window.__EXPECT.maxLen);
    R.ok('引擎未就绪时打分按钮禁用', $('#scoreBtn').disabled === true);
    R.ok('禁用按钮带原因提示', String($('#scoreBtn').title).length > 0, $('#scoreBtn').title);
    $('#errorCloseBtn').click();
    R.ok('错误条可关闭', $('#errorBar').hidden === true);
    R.ok('关闭后页面仍可用', $('#statusBadge').dataset.state === 'error');
    return R.out;
  }

  /* ============================== 服务不可达 (503) ========================= */
  async function down() {
    var R = mkReport();
    R.ok('页面未白屏', !!$('#seqInput') && !!$('#scoreBtn'));
    R.ok('等待错误状态', await waitFor(function () { return $('#statusBadge').dataset.state === 'error'; }, 8000));
    R.eq('徽章标题', txt($('#statusTitle')), '引擎不可达');
    R.ok('错误条可见', $('#errorBar').hidden === false);
    R.ok('错误文本含 HTTP/后端信息', /服务不可用|HTTP 503/.test(txt($('#errorText'))), txt($('#errorText')));
    R.ok('状态副标题展示原因', txt($('#statusMeta')).length > 0, txt($('#statusMeta')));
    R.ok('打分按钮禁用', $('#scoreBtn').disabled === true);
    R.ok('重试按钮存在', !!$('#recheckBtn') && $('#recheckBtn').disabled === false);
    return R.out;
  }

  /* ============================ 打分接口 500 ============================== */
  async function err500() {
    var R = mkReport();
    R.ok('页面未白屏', !!$('#seqInput') && !!$('#scoreBtn'));
    R.ok('状态仍为就绪', await waitFor(function () { return $('#statusBadge').dataset.state === 'ready'; }, 8000));
    $('#sampleBtn').click();
    await sleep(250);
    $('#scoreBtn').click();
    R.ok('等待打分错误', await waitFor(function () { return $('#errorBar').hidden === false; }, 10000));
    R.eq('错误条标题', txt($('#errorTitle')), '打分失败');
    R.ok('错误文本来自 error 字段', txt($('#errorText')).indexOf('打分引擎内部错误') >= 0, txt($('#errorText')));
    R.ok('加载态已复位', document.body.classList.contains('is-loading') === false);
    R.ok('页面结构仍完整（无白屏）', !!$('#resultMeta') && !!$('#histogram') && $('#resultsEmpty').hidden === false);
    R.ok('打分按钮恢复可用', $('#scoreBtn').disabled === false);
    $('#errorCloseBtn').click();
    R.ok('错误条可关闭', $('#errorBar').hidden === true);
    return R.out;
  }

  /* ============================ 中英双语界面 ============================== */
  /* 结束时页面停在英文，供 smoke.mjs 截图；随后由 i18nBack 切回中文，
     因为后面的故障路径阶段断言的是中文文案。 */
  async function i18n() {
    var R = mkReport();
    var PR = window.PR_I18N;
    var EXPECT = window.__EXPECT || { sampleCount: 15, maxLen: 0 };
    R.ok('i18n.js 已加载', !!PR && typeof PR.lang === 'function' && typeof PR.t === 'function');
    if (!PR) return R.out;
    R.ok('等待引擎就绪', await waitFor(function () { return $('#statusBadge').dataset.state === 'ready'; }, 8000));

    var segZh = $('#langSwitch .seg[data-lang="zh"]');
    var segEn = $('#langSwitch .seg[data-lang="en"]');
    R.ok('语言切换控件存在', !!segZh && !!segEn);
    R.ok('切换控件有地球图标', !!$('#langSwitch .langswitch__icon'));

    /* --- 中文基准（并打分一次，让动态文案也参与切换） --- */
    if (PR.lang() !== 'zh') segZh.click();
    await sleep(150);
    R.eq('切到中文', PR.lang(), 'zh');
    R.eq('中文 document.title', document.title, 'PeptideRanker · 肽活性打分');
    R.eq('中文 <html lang>', document.documentElement.getAttribute('lang'), 'zh-CN');
    R.eq('中文按钮', txt($('#sampleBtn').querySelector('span')), '载入示例');
    R.eq('中文表头', txt($('th[data-sort="score"] span')), '分数');
    R.eq('中文概览标签', txt($('.stat__label')), '序列数');
    R.eq('中文 zh 按钮激活', segZh.classList.contains('is-active'), true);

    $('#sampleBtn').click();
    await sleep(250);
    $('#scoreBtn').click();
    await waitFor(function () { return rows().length === EXPECT.sampleCount; }, 10000);
    R.ok('中文下打分成功', rows().length === EXPECT.sampleCount);

    /* --- 切到英文：静态文案 + 动态文案都要变 --- */
    segEn.click();
    await sleep(200);
    R.eq('切到英文', PR.lang(), 'en');
    R.eq('英文 <html lang>', document.documentElement.getAttribute('lang'), 'en');
    R.eq('英文 document.title', document.title, 'PeptideRanker · Peptide Bioactivity Scoring');
    R.eq('英文按钮', txt($('#sampleBtn').querySelector('span')), 'Load sample');
    R.eq('英文表头', txt($('th[data-sort="score"] span')), 'Score');
    R.eq('英文概览标签', txt($('.stat__label')), 'Sequences');
    R.eq('英文输入统计', txt($('#statCount')),
         EXPECT.sampleCount + ' sequences, longest ' + EXPECT.maxLen);
    R.ok('英文结果元信息（动态文案）', /in total/.test(txt($('#resultMeta'))), txt($('#resultMeta')));
    R.ok('英文概览元信息（动态文案）', /short \d+/.test(txt($('#overviewMeta'))), txt($('#overviewMeta')));
    R.ok('英文筛选按钮保留计数', /\d+/.test(txt($('#segAbove'))), txt($('#segAbove')));
    R.ok('英文下结果表仍完整', rows().length === EXPECT.sampleCount);
    R.ok('英文模型标签', modelOf(0) === 'short peptide' || modelOf(0) === 'long peptide', modelOf(0));
    R.eq('英文 EN 按钮激活', segEn.classList.contains('is-active'), true);
    R.eq('英文 zh 按钮非激活', segZh.classList.contains('is-active'), false);
    R.eq('localStorage 记忆英文', window.localStorage.getItem('pr_lang'), 'en');
    R.ok('切换后有 toast 反馈', /English/.test(txt($('#toast'))), txt($('#toast')));

    /* 英文下非法行警告也要是英文 */
    var ep = $('#seqInput');
    ep.value = 'ILP1LS';
    ep.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(220);
    R.ok('英文非法行警告', txt($('#warnList')).indexOf('invalid character') >= 0, txt($('#warnList')));
    R.eq('英文格式标签', txt($('#statFormat')), 'Format: line-based');
    /* 还原成已打分状态，便于截图 */
    $('#sampleBtn').click();
    await sleep(250);
    $('#scoreBtn').click();
    await waitFor(function () { return rows().length === EXPECT.sampleCount; }, 10000);
    R.ok('英文下重新打分成功', rows().length === EXPECT.sampleCount);
    return R.out;
  }

  /* 切回中文：后续故障路径阶段的断言基于中文文案 */
  async function i18nBack() {
    var R = mkReport();
    var PR = window.PR_I18N;
    if (!PR) { R.ok('i18n 可用', false); return R.out; }
    $('#langSwitch .seg[data-lang="zh"]').click();
    await sleep(180);
    R.eq('切回中文', PR.lang(), 'zh');
    R.eq('切回后 document.title', document.title, 'PeptideRanker · 肽活性打分');
    R.eq('切回后 <html lang>', document.documentElement.getAttribute('lang'), 'zh-CN');
    R.eq('切回后按钮', txt($('#sampleBtn').querySelector('span')), '载入示例');
    R.eq('切回后表头', txt($('th[data-sort="score"] span')), '分数');
    R.eq('切回后 localStorage', window.localStorage.getItem('pr_lang'), 'zh');
    R.ok('切回后无英文残留提示', txt($('#statFormat')).indexOf('Format') < 0, txt($('#statFormat')));
    return R.out;
  }

  return { main: main, i18n: i18n, i18nBack: i18nBack, notReady: notReady, down: down, err500: err500 };
})();
