/* PeptideRanker 前端端到端测试（DOM 垫片版，自测用，不属于产品代码）
 *
 * 本机沙箱内无法启动 Chrome/Edge（crashpad 被拒绝），因此用 dom_shim.mjs 提供的最小 DOM
 * 加载真实 index.html + app.js，并通过真实 HTTP 调用 _mock/mock_server.py，覆盖：
 *   渲染、实时统计、载入示例、打分、加载态、表格/概览/直方图、表头排序、筛选、
 *   非法行提示、CSV 文件导入、Ctrl+Enter、复制 TSV、导出 CSV（BOM + 表头）、清空，
 *   以及 ready=false / 503 / 500 三条故障路径。
 *
 * 前置：mock 服务已在 8899 端口运行
 * 运行：node app/static/_mock/dom_test.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { installDom, fireDomContentLoaded } from './dom_shim.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const staticDir = path.join(here, '..');
const BASE = process.env.MOCK_BASE || 'http://127.0.0.1:8899';
/* REAL_BACKEND=1 时对着真实后端（app/server.py）跑：跳过 mock 专属的故障模式切换，
 * 并额外用直连请求核对后端响应字段名与契约一致。 */
const REAL = process.env.REAL_BACKEND === '1';

const htmlSrc = fs.readFileSync(path.join(staticDir, 'index.html'), 'utf8');
const i18nSrc = fs.readFileSync(path.join(staticDir, 'i18n.js'), 'utf8');
const appSrc = fs.readFileSync(path.join(staticDir, 'app.js'), 'utf8');
const cssSrc = fs.readFileSync(path.join(staticDir, 'style.css'), 'utf8');
/* 产品页面里 i18n.js 与 app.js 共享全局作用域，这里拼接起来模拟 */
const bundle = i18nSrc + '\n' + appSrc;
const exampleText = new Function(bundle + '\nreturn EXAMPLE_SEQUENCES;')();
const exampleSeqs = exampleText.split('\n');
const EXPECT = { count: exampleSeqs.length, maxLen: Math.max(...exampleSeqs.map(s => s.length)) };

const sleep = ms => new Promise(r => setTimeout(r, ms));

let pass = 0, fail = 0;
const failures = [];
function ok(name, cond, extra) {
  if (cond) pass++;
  else { fail++; failures.push({ name, extra: extra === undefined ? null : extra }); }
}
function eq(name, actual, expected) {
  const good = JSON.stringify(actual) === JSON.stringify(expected);
  ok(name + (good ? '' : `  [实际 ${JSON.stringify(actual)} ≠ 期望 ${JSON.stringify(expected)}]`), good);
}
async function waitFor(fn, timeout = 8000) {
  const t0 = Date.now();
  for (;;) {
    let v = false;
    try { v = fn(); } catch { v = false; }
    if (v) return true;
    if (Date.now() - t0 > timeout) return false;
    await sleep(30);
  }
}
async function setMode(mode) {
  const res = await fetch(BASE + '/__mock/mode', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode })
  });
  if (!res.ok) throw new Error('切换 mode 失败 ' + res.status);
}
async function serverLog(clear) {
  const res = await fetch(BASE + '/__mock/log', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(clear ? { clear: true } : {})
  });
  return (await res.json()).requests;
}

/* ------------------------------ 页面工厂 --------------------------------- */
let current = null;
/* lang：写入 localStorage 的初始界面语言。默认固定为 zh，这样测试结果
   不随宿主系统语言变化（i18n 的 detect() 会优先读 localStorage）。
   query：覆盖 location.search，用于验证 ?api= / ?lang= 这类查询参数。 */
function newPage(lang, query) {
  const dom = installDom(htmlSrc, { origin: BASE });
  current = dom;
  if (query) dom.window.location.search = query;
  dom.storage.setItem('pr_lang', lang || 'zh');
  new Function(bundle)();
  fireDomContentLoaded(dom.document);
  return dom;
}

const D = () => current.document;
const I18N = () => globalThis.PR_I18N;
const $ = id => D().getElementById(id);
const $$ = sel => D().querySelectorAll(sel);
const txt = el => (el ? el.textContent.trim() : null);
const rows = () => $$('#resultBody tr');
const rowAt = i => rows()[i] || null;
const rankOf = i => txt(rowAt(i) ? rowAt(i).querySelector('.rank') : null);
const lenOf = i => (rowAt(i) ? Number(txt(rowAt(i).children[3])) : null);
const scoreOf = i => txt(rowAt(i) ? rowAt(i).querySelector('.score__num') : null);
const modelOf = i => (rowAt(i) ? txt(rowAt(i).children[5]) : null);
const allScores = () => $$('#resultBody .score__num').map(n => parseFloat(n.textContent));
const scoreTexts = () => $$('#resultBody .score__num').map(n => n.textContent.trim());
const allLengths = () => rows().map(r => Number(txt(r.children[3])));
const barWidth = i => {
  const bar = rowAt(i) ? rowAt(i).querySelector('.score__bar i') : null;
  return bar ? parseFloat(bar.style.width) : null;
};
const setInput = text => {
  const ta = $('seqInput');
  ta.value = text;
  ta.dispatch('input');
};
const isDesc = a => a.every((v, i) => i === 0 || a[i - 1] >= v);
const isAsc = a => a.every((v, i) => i === 0 || a[i - 1] <= v);

/* ============================== 静态一致性 =============================== */
{
  const idsInHtml = new Set((htmlSrc.match(/\bid="([^"]+)"/g) || []).map(s => s.slice(4, -1)));  const idsUsed = new Set((appSrc.match(/getElementById\('([^']+)'\)|\$\('([^']+)'\)/g) || [])
    .map(s => (/getElementById\('([^']+)'\)/.exec(s) || [null, null])[1] || (/\$\('([^']+)'\)/.exec(s) || [null, null])[1])
    .filter(Boolean));
  const missing = Array.from(idsUsed).filter(id => !idsInHtml.has(id));
  ok('app.js 引用的所有元素 id 都存在于 index.html' + (missing.length ? '：缺 ' + missing.join(',') : ''), missing.length === 0);

  const symbols = new Set((htmlSrc.match(/<symbol id="([^"]+)"/g) || []).map(s => s.replace(/.*id="([^"]+)".*/, '$1')));
  const used = new Set([...htmlSrc.matchAll(/href="#([^"]+)"/g)].map(m => m[1])
    .concat([...appSrc.matchAll(/icon\('([^']+)'/g)].map(m => m[1]))
    .concat([...appSrc.matchAll(/#(i-[a-z]+)/g)].map(m => m[1])));
  const badIcons = Array.from(used).filter(i => !symbols.has(i));
  ok('所有内联 SVG 图标引用都有对应 symbol' + (badIcons.length ? '：缺 ' + badIcons.join(',') : ''), badIcons.length === 0);

  const cssBody = cssSrc.replace(/\/\*[\s\S]*?\*\//g, '');
  const open = (cssBody.match(/{/g) || []).length, close = (cssBody.match(/}/g) || []).length;
  eq('style.css 花括号配平', open, close);
  ok('style.css 无 @import / 外链字体 / CDN',
    !/@import/.test(cssBody) && !/url\(\s*['"]?https?:/i.test(cssBody) && !/fonts\.googleapis|cdn\./i.test(cssBody));
  ok('index.html 无外部资源引用（script/link 均为本地）',
    !/<script[^>]+src="https?:/i.test(htmlSrc) && !/<link[^>]+href="https?:/i.test(htmlSrc));
  ok('index.html 声明深色配色', /name="color-scheme"\s+content="dark"/.test(htmlSrc));
  ok('index.html 在 app.js 之前引入 i18n.js',
    htmlSrc.indexOf('src="i18n.js"') >= 0 && htmlSrc.indexOf('src="i18n.js"') < htmlSrc.indexOf('src="app.js"'));
  ok('i18n.js 非空', i18nSrc.length > 3000);

  /* 多语言静态一致性：data-i18n 系列属性引用的键必须在字典里存在 */
  const pr = new Function(bundle + '\nreturn PR_I18N;')();
  const dictKeys = new Set(Object.keys(pr.dict.zh));
  const htmlKeys = [...htmlSrc.matchAll(/data-i18n(?:-html|-title|-placeholder|-aria-label)?="([^"]+)"/g)].map(m => m[1]);
  const badKeys = [...new Set(htmlKeys)].filter(k => !dictKeys.has(k));
  ok('index.html 的 data-i18n 键全部已定义' + (badKeys.length ? '：缺 ' + badKeys.join(',') : ''), badKeys.length === 0);
  const codeKeys = [...appSrc.matchAll(/\bt\(\s*'([^']+)'/g)].map(m => m[1])
    .concat([...appSrc.matchAll(/\bt\([^)]*\?\s*'([^']+)'\s*:\s*'([^']+)'/g)].flatMap(m => [m[1], m[2]]));
  const badCodeKeys = [...new Set(codeKeys)].filter(k => !dictKeys.has(k));
  ok('app.js 的 t() 键全部已定义' + (badCodeKeys.length ? '：缺 ' + badCodeKeys.join(',') : ''), badCodeKeys.length === 0);
  const diff = pr.keyDiff();
  ok('中英字典键集合一致', diff.missingInEn.length === 0 && diff.missingInZh.length === 0, diff);
}

/* ======================== 部署形态：静态资源可访问 ======================== */
{
  const index = await fetch(BASE + '/');
  ok('GET / 返回 200', index.status === 200, index.status);
  const indexText = await index.text();
  ok('GET / 返回 index.html', indexText.includes('PeptideRanker') && indexText.includes('id="seqInput"'));
  ok('index.html 用相对路径引用 style.css/app.js',
    /href="style\.css"/.test(indexText) && /src="app\.js"/.test(indexText) && /src="i18n\.js"/.test(indexText));
  const js = await fetch(BASE + '/app.js');
  const css = await fetch(BASE + '/style.css');
  const i18nRes = await fetch(BASE + '/i18n.js');
  eq('GET /app.js 返回 200', js.status, 200);
  eq('GET /style.css 返回 200', css.status, 200);
  eq('GET /i18n.js 返回 200', i18nRes.status, 200);
  ok('app.js 内容非空', (await js.text()).length > 10000);
  ok('style.css 内容非空', (await css.text()).length > 5000);
  ok('i18n.js 内容非空', (await i18nRes.text()).length > 3000);
}

/* ==================== 多语言切换（中文 / English） ======================= */
{
  /* 种子语言用 en：宿主 navigator.language 是中文，因此这同时验证了
     “localStorage 记忆值优先于浏览器语言”。 */
  newPage('en');
  ok('i18n：i18n.js 已加载并挂到全局', typeof globalThis.PR_I18N === 'object' && !!I18N());
  eq('i18n：localStorage 记忆值优先（启动即英文）', I18N().lang(), 'en');
  eq('i18n：<html lang> 为 en', D().documentElement.getAttribute('lang'), 'en');
  eq('i18n：英文页面标题', D().title, 'PeptideRanker · Peptide Bioactivity Scoring');
  eq('i18n：英文按钮文案', txt($('sampleBtn').querySelector('span')), 'Load sample');
  eq('i18n：英文表头', txt(D().querySelector('th[data-sort="score"] span')), 'Score');
  eq('i18n：英文输入统计', txt($('statCount')), '0 sequences, longest 0');
  eq('i18n：英文空态标题', txt($('resultsEmpty').querySelector('strong')), 'No results yet');
  eq('i18n：英文输入框 aria-label', $('seqInput').getAttribute('aria-label'), 'Sequence input box');
  eq('i18n：英文 placeholder 首行',
    $('seqInput').getAttribute('placeholder').split('\n')[0],
    'One sequence per line (or paste / drop a .txt/.fasta/.fa/.csv file):');
  ok('i18n：EN 按钮为激活态', D().querySelector('#langSwitch .seg[data-lang="en"]').classList.contains('is-active'));
  ok('i18n：中文按钮非激活态', D().querySelector('#langSwitch .seg[data-lang="zh"]').classList.contains('is-active') === false);

  /* 非法行警告是解析期生成的，必须随语言变化 */
  setInput('ILP1LS');
  await sleep(160);
  ok('i18n：英文非法行警告', txt($('warnList')).includes('invalid character'), txt($('warnList')));
  eq('i18n：英文格式标签', txt($('statFormat')), 'Format: line-based');
  eq('i18n：英文非法计数', txt($('statInvalid')), '1 invalid');

  /* 切回中文 */
  D().querySelector('#langSwitch .seg[data-lang="zh"]').click();
  eq('i18n：点击后语言变为 zh', I18N().lang(), 'zh');
  eq('i18n：<html lang> 变回 zh-CN', D().documentElement.getAttribute('lang'), 'zh-CN');
  eq('i18n：中文页面标题', D().title, 'PeptideRanker · 肽活性打分');
  eq('i18n：中文按钮文案', txt($('sampleBtn').querySelector('span')), '载入示例');
  eq('i18n：中文表头', txt(D().querySelector('th[data-sort="score"] span')), '分数');
  ok('i18n：中文非法行警告', txt($('warnList')).includes('含非法字符'), txt($('warnList')));
  eq('i18n：中文格式标签', txt($('statFormat')), '格式：逐行');
  ok('i18n：中文按钮回到激活态', D().querySelector('#langSwitch .seg[data-lang="zh"]').classList.contains('is-active'));
  eq('i18n：选择写入 localStorage', current.storage.getItem('pr_lang'), 'zh');
  ok('i18n：切换有 toast 反馈', /界面语言/.test(txt($('toast'))), txt($('toast')));
  ok('i18n：切换后无未捕获异常', current.hooks.errors.length === 0, current.hooks.errors.slice(0, 2));

  /* 再切到英文：确认可来回切换 */
  D().querySelector('#langSwitch .seg[data-lang="en"]').click();
  eq('i18n：再次切到英文', I18N().lang(), 'en');
  eq('i18n：再次切换后 toast 为英文', txt($('toast')), 'Interface language set to English');
  eq('i18n：localStorage 更新为 en', current.storage.getItem('pr_lang'), 'en');

  /* URL 上的 ?lang= 覆盖 localStorage 记忆值，但只影响本次访问（不落盘） */
  newPage('zh', '?api=' + encodeURIComponent(BASE) + '&lang=en');
  eq('i18n：?lang=en 覆盖 localStorage', I18N().lang(), 'en');
  eq('i18n：?lang=en 时界面为英文', txt($('sampleBtn').querySelector('span')), 'Load sample');
  eq('i18n：?lang= 不写入 localStorage', current.storage.getItem('pr_lang'), 'zh');
  newPage('zh', '?api=' + encodeURIComponent(BASE) + '&lang=de');
  eq('i18n：未知 ?lang 值回落到 localStorage', I18N().lang(), 'zh');
}

/* ============================ 阶段 1：正常流程 ============================ */
if (!REAL) await setMode('ok');
{
  newPage();
  ok('页面骨架渲染', !!$('seqInput') && !!$('scoreBtn') && !!$('resultBody') && !!$('histogram'));
  eq('页面标题', D().title, 'PeptideRanker · 肽活性打分');
  ok('空输入时打分按钮禁用', $('scoreBtn').disabled === true);
  ok('初始为空态占位', $('resultsEmpty').hidden === false && $('tableWrap').hidden === true);
  eq('初始统计', txt($('statCount')), '共 0 条序列，最长 0');

  ok('等待引擎就绪', await waitFor(() => $('statusBadge').dataset.state === 'ready', 8000));
  eq('状态徽章标题', txt($('statusTitle')), '引擎就绪');
  if (REAL) {
    ok('状态栏展示真实引擎信息', txt($('statusMeta')).includes('python-port') && txt($('statusMeta')).includes('短肽'),
      txt($('statusMeta')));
  } else {
    ok('状态栏含短肽/长肽模型数', txt($('statusMeta')).includes('短肽 15') && txt($('statusMeta')).includes('长肽 15'), txt($('statusMeta')));
  }
  ok('状态栏含版本与阈值', txt($('statusMeta')).includes('v1.0') && txt($('statusMeta')).includes('0.50'), txt($('statusMeta')));
  ok('就绪时无错误条', $('errorBar').hidden === true);
  /* 页脚 = 服务地址（+ 真实后端还会带上“无访问自动退出”分钟数） */
  ok('底部显示服务地址', txt($('footerApi')).indexOf('服务地址：' + BASE) === 0, txt($('footerApi')));

  /* 实时统计 */
  setInput('ILPILSLIGGLL\nRPPGFSPFR');
  await sleep(150);
  eq('实时统计', txt($('statCount')), '共 2 条序列，最长 12');
  setInput('');
  await sleep(150);
  eq('清空输入后统计归零', txt($('statCount')), '共 0 条序列，最长 0');

  /* 载入示例 */
  $('sampleBtn').click();
  await waitFor(() => /共 15 条/.test(txt($('statCount'))), 3000);
  eq('示例统计', txt($('statCount')), `共 ${EXPECT.count} 条序列，最长 ${EXPECT.maxLen}`);
  eq('示例全部合法', txt($('statValid')), `合法 ${EXPECT.count}`);
  ok('无非法行时隐藏非法 chip', $('statInvalid').hidden === true);
  ok('格式识别为逐行', txt($('statFormat')).includes('逐行'), txt($('statFormat')));
  ok('镜像层按行渲染', $('editorMirror').children.length >= EXPECT.count, $('editorMirror').children.length);
  ok('载入示例后按钮可用', $('scoreBtn').disabled === false);

  /* 打分与加载态 */
  $('scoreBtn').click();
  ok('点击后立即进入加载态并禁用按钮', D().body.classList.contains('is-loading') && $('scoreBtn').disabled === true);
  ok('等待结果渲染', await waitFor(() => rows().length === EXPECT.count, 10000));
  ok('加载态复位', D().body.classList.contains('is-loading') === false);
  ok('表格显示、空态隐藏', $('tableWrap').hidden === false && $('resultsEmpty').hidden === true);
  eq('结果行数', rows().length, EXPECT.count);
  eq('排名首尾', [rankOf(0), rankOf(EXPECT.count - 1)], ['1', String(EXPECT.count)]);
  ok('分数降序（契约）', isDesc(allScores()), allScores().slice(0, 4));
  ok('分数均为 4 位小数（显示文本）', scoreTexts().every(t => /^\d+\.\d{4}$/.test(t)), scoreTexts().slice(0, 3));
  ok('分数都在 0~1', allScores().every(v => v >= 0 && v <= 1));
  ok('进度条宽度与分数一致', Math.abs(barWidth(0) - allScores()[0] * 100) < 0.6, { bar: barWidth(0), score: allScores()[0] });
  ok('模型标签符合 ≤20 短肽规则', rows().every((r, i) => (lenOf(i) <= 20 ? modelOf(i).includes('短肽') : modelOf(i).includes('长肽'))));
  ok('阈值高亮与分数一致', rows().every((r, i) => {
    const above = allScores()[i] >= 0.5;
    return above === r.classList.contains('row--above') && above === !!r.querySelector('.tag--threshold');
  }));
  if (!REAL) ok('存在 ≥0.5 的行', allScores().some(v => v >= 0.5));

  /* 概览 */
  const sc = allScores();
  eq('概览序列数', txt($('sumCount')), String(EXPECT.count));
  eq('概览最高分', txt($('sumMax')), sc[0].toFixed(4));
  eq('概览最低分', txt($('sumMin')), sc[sc.length - 1].toFixed(4));
  const mean = sc.reduce((a, b) => a + b, 0) / sc.length;
  ok('概览平均分与本地计算一致', Math.abs(parseFloat(txt($('sumMean'))) - mean) < 0.0002, { ui: txt($('sumMean')), calc: mean.toFixed(4) });
  const sorted = sc.slice().sort((a, b) => a - b), mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  ok('概览中位数与本地计算一致', Math.abs(parseFloat(txt($('sumMedian'))) - median) < 0.0002, { ui: txt($('sumMedian')), calc: median.toFixed(4) });
  eq('概览 ≥阈值条数', txt($('sumAbove')), String(sc.filter(v => v >= 0.5).length));
  eq('概览命中率提示', txt($('sumAboveLabel')), '≥ 0.50 条数');

  /* 直方图 */
  eq('直方图 10 个区间', $$('#histogram .hist__col').length, 10);
  eq('直方图计数总和', $$('#histogram .hist__count').reduce((a, n) => a + Number(txt(n)), 0), EXPECT.count);
  ok('直方图有可见柱高', $$('#histogram .hist__bar').some(b => parseFloat(b.style.height) > 4));
  eq('直方图元信息', txt($('histMeta')), '10 个等宽区间 · 峰值 ' + Math.max(...$$('#histogram .hist__count').map(n => Number(txt(n)))) + ' 条');

  /* 排序 */
  D().querySelector('th[data-sort="length"]').click();
  ok('按长度降序', isDesc(allLengths()), allLengths().slice(0, 4));
  eq('表头 aria-sort=descending', D().querySelector('th[data-sort="length"]').getAttribute('aria-sort'), 'descending');
  D().querySelector('th[data-sort="length"]').click();
  ok('再次点击变升序', isAsc(allLengths()), allLengths().slice(0, 4));
  eq('表头 aria-sort=ascending', D().querySelector('th[data-sort="length"]').getAttribute('aria-sort'), 'ascending');
  D().querySelector('th[data-sort="id"]').click();
  ok('按 ID 排序不报错', rows().length === EXPECT.count);
  D().querySelector('th[data-sort="score"]').click();
  ok('按分数降序（默认）', isDesc(allScores()), allScores().slice(0, 3));
  eq('无残留 aria-sort 于其他表头', D().querySelector('th[data-sort="length"]').getAttribute('aria-sort'), null);

  /* 筛选 */
  const aboveN = Number(txt($('sumAbove')));
  D().querySelector('#filterGroup .seg[data-filter="above"]').click();
  eq('筛选 ≥0.5 行数', rows().length, aboveN);
  ok('筛选 ≥0.5 全部达标', allScores().every(v => v >= 0.5));
  ok('筛选按钮激活态', D().querySelector('#filterGroup .seg[data-filter="above"]').classList.contains('is-active'));
  D().querySelector('#filterGroup .seg[data-filter="below"]').click();
  eq('筛选 <0.5 行数', rows().length, EXPECT.count - aboveN);
  ok('筛选 <0.5 全部低于阈值', allScores().every(v => v < 0.5));
  eq('筛选标签带计数', txt($('segAbove')), `≥ 0.50 (${aboveN})`);
  D().querySelector('#filterGroup .seg[data-filter="all"]').click();
  eq('恢复全部', rows().length, EXPECT.count);

  /* 非法字符 */
  setInput('ILPILSLIGGLL\nRPPGF1SPFR\nFLPIVGKLLSGLSGLL');
  await sleep(200);
  eq('非法输入统计', txt($('statCount')), '共 3 条序列，最长 16');
  eq('非法行计数', txt($('statInvalid')), '非法 1 行');
  ok('非法计数可见', $('statInvalid').hidden === false);
  eq('镜像层标出 1 个非法行', $$('#editorMirror .ln--bad').length, 1);
  ok('出现本地解析提示', $('warnBox').hidden === false && txt($('warnList')).includes("第 2 行含非法字符 '1'，已跳过"), txt($('warnList')));
  ok('提示带本地来源标签', !!$$('#warnList .tag--local').length);
  $('scoreBtn').click();
  ok('非法行下仍可打分', await waitFor(() => rows().length === 2, 10000));
  eq('合法行数', rows().length, 2);
  ok('跳过行未出现在结果中', txt($('resultBody')).indexOf('RPPGF1SPFR') < 0);

  /* Ctrl+Enter */
  setInput('RPPGFSPFR');
  await sleep(200);
  D().dispatch('keydown', { key: 'Enter', ctrlKey: true });
  ok('Ctrl+Enter 触发打分', await waitFor(() => rows().length === 1, 10000));
  eq('快捷键结果行数', rows().length, 1);
  eq('快捷键结果分数位数', String(scoreOf(0)).length, 6);

  /* 复制 TSV */
  const before = current.hooks.copied.length;
  $('copyBtn').click();
  await sleep(200);
  const copied = current.hooks.copied.slice(before);
  if (copied.length) {
    const lines = copied[copied.length - 1].split('\n');
    eq('剪贴板 TSV 表头', lines[0], 'rank\tid\tsequence\tlength\tscore\tmodel');
    eq('剪贴板数据行数', lines.length - 1, 1);
    ok('剪贴板分数 4 位小数', /\t\d\.\d{4}\t/.test(copied[copied.length - 1]), copied[copied.length - 1]);
  } else {
    ok('复制给出成功提示', txt($('toast')).includes('已复制'), txt($('toast')));
  }

  /* CSV 文件导入 */
  const fakeFile = {
    name: 'peptides.csv', size: 120, type: 'text/csv',
    text: async () => 'id,sequence\nA1,ILPILSLIGGLL\nA2,RPPGFSPFR\nA3,FLPIVGKLLSGLSGLL\n'
  };
  $('fileInput').files = [fakeFile];
  $('fileInput').dispatch('change');
  ok('CSV 文件导入后统计更新', await waitFor(() => txt($('statCount')) === '共 3 条序列，最长 16', 3000), txt($('statCount')));
  eq('CSV 导入后格式标签', txt($('statFormat')), '格式：CSV / 单列');
  $('scoreBtn').click();
  ok('CSV 导入后可打分', await waitFor(() => rows().length === 3, 10000));
  eq('CSV 导入结果 ID 来自首列', txt(rowAt(0).children[1]).length > 0, true);
  ok('CSV 导入 ID 在 A1/A2/A3 中', rows().every((r, i) => ['A1', 'A2', 'A3'].includes(txt(r.children[1]))));

  /* 不支持的文件类型 -> 明确报错而不是白屏 */
  $('fileInput').files = [{ name: 'report.docx', size: 2048, type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', text: async () => 'x' }];
  $('fileInput').dispatch('change');
  await waitFor(() => $('errorBar').hidden === false, 3000);
  eq('不支持文件类型时错误标题', txt($('errorTitle')), '不支持的文件类型');
  ok('错误文本给出支持的扩展名', txt($('errorText')).includes('.csv'), txt($('errorText')));
  ok('报错后页面结构完好', !!$('seqInput') && txt($('statCount')).length > 0);
  $('errorCloseBtn').click();

  /* 导出 CSV（真实 POST /api/export + 下载钩子） */
  const urlsBefore = current.hooks.objectUrls.length;
  $('sampleBtn').click();
  await waitFor(() => /共 15 条/.test(txt($('statCount'))), 3000);
  $('scoreBtn').click();
  await waitFor(() => rows().length === EXPECT.count, 10000);
  $('exportBtn').click();
  ok('导出触发下载', await waitFor(() => current.hooks.objectUrls.length > urlsBefore, 8000));
  const blob = current.hooks.objectUrls[current.hooks.objectUrls.length - 1];
  const buf = Buffer.from(await blob.arrayBuffer());
  const hasBom = buf[0] === 0xEF && buf[1] === 0xBB && buf[2] === 0xBF;
  const csvLines = buf.slice(hasBom ? 3 : 0).toString('utf8').trim().split('\n');
  ok('导出 CSV 带 UTF-8 BOM', hasBom, buf.slice(0, 3).toString('hex'));
  eq('导出 CSV 表头与契约一致', csvLines[0].replace(/\r$/, ''), 'rank,id,sequence,length,score,model');
  eq('导出行数', csvLines.length, EXPECT.count + 1);
  ok('导出分数至少 4 位小数', /,\d+\.\d{4,},/.test(csvLines[1]), csvLines[1]);
  ok('导出按 rank 排序', csvLines[1].startsWith('1,'));
  ok('导出 MIME 为 text/csv', blob.type.includes('csv'), blob.type);

  /* 清空 */
  $('clearBtn').click();
  await sleep(120);
  eq('清空后输入为空', $('seqInput').value, '');
  eq('清空后无结果行', rows().length, 0);
  ok('清空后回到空态', $('tableWrap').hidden === true && $('resultsEmpty').hidden === false);
  eq('清空后概览归零', txt($('sumCount')), '—');
  eq('清空后统计归零', txt($('statCount')), '共 0 条序列，最长 0');
  ok('清空后打分按钮禁用', $('scoreBtn').disabled === true);

  ok('运行期间无未捕获异常', current.hooks.errors.length === 0, current.hooks.errors.slice(0, 3));
}

/* ==================== 契约一致性：真实发出的请求体 ====================== */
if (!REAL) {
  const log = await serverLog(false);
  const scoreReqs = log.filter(r => r.method === 'POST' && r.path === '/api/score');
  const exportReqs = log.filter(r => r.method === 'POST' && r.path === '/api/export');
  ok('确实调用了 GET /api/status', log.some(r => r.method === 'GET' && r.path === '/api/status'));
  ok('确实调用了 POST /api/score', scoreReqs.length > 0, scoreReqs.length);
  ok('确实调用了 POST /api/export（非本地兜底）', exportReqs.length > 0, exportReqs.length);

  const lastScore = scoreReqs[scoreReqs.length - 1];
  if (lastScore && lastScore.body) {
    eq('score 请求体字段名与契约一致', Object.keys(lastScore.body).sort(), ['lang', 'length_handling', 'sequences']);
    ok('lang 取值合法', ['zh', 'en'].includes(lastScore.body.lang), lastScore.body.lang);
    ok('length_handling 取值合法', ['auto', 'short', 'long'].includes(lastScore.body.length_handling), lastScore.body.length_handling);
    eq('length_handling 默认 auto', lastScore.body.length_handling, 'auto');
    ok('sequences 为数组', Array.isArray(lastScore.body.sequences));
    const item = lastScore.body.sequences[0] || {};
    eq('sequences 元素字段名与契约一致', Object.keys(item).sort(), ['id', 'sequence']);
    ok('sequences 元素 id 非空', String(item.id).length > 0, item.id);
    ok('sequences 元素 sequence 为大写字母', /^[A-Z]+$/.test(String(item.sequence)), item.sequence);
    ok('每条序列都合法（非法行已在前端跳过）',
      lastScore.body.sequences.every(s => /^[A-Z]+$/.test(String(s.sequence))));
  }

  const lastExport = exportReqs[exportReqs.length - 1];
  if (lastExport && lastExport.body) {
    eq('export 请求体字段名与契约一致', Object.keys(lastExport.body).sort(), ['format', 'lang', 'length_handling', 'sequences']);
    eq('export format=csv', lastExport.body.format, 'csv');
    ok('export 与 score 使用同一 sequences 结构',
      Array.isArray(lastExport.body.sequences) && lastExport.body.sequences.every(s => 'id' in s && 'sequence' in s));
  }

  /* length_handling 三种取值都能透传（先保证有可打分的输入） */
  $('sampleBtn').click();
  await waitFor(() => /共 15 条/.test(txt($('statCount'))), 3000);
  for (const mode of ['short', 'long', 'auto']) {
    await serverLog(true);
    $('lengthHandling').value = mode;
    $('scoreBtn').click();
    const seen = await (async () => {
      const t0 = Date.now();
      for (;;) {
        const reqs = (await serverLog(false)).filter(r => r.path === '/api/score');
        if (reqs.length) return reqs[0].body.length_handling;
        if (Date.now() - t0 > 8000) return null;
        await sleep(50);
      }
    })();
    eq('length_handling 透传 ' + mode, seen, mode);
    await waitFor(() => D().body.classList.contains('is-loading') === false, 8000);
  }
} else {
  /* ------- 真实后端：直连核对响应字段名与契约 ------- */
  const samplePayload = {
    sequences: exampleSeqs.map((s, i) => ({ id: 'seq' + (i + 1), sequence: s })),
    length_handling: 'auto'
  };
  const st = await (await fetch(BASE + '/api/status')).json();
  eq('真实后端 /api/status ready=true', st.ready, true);
  eq('真实后端 engine 字段', st.engine, 'python-port');
  eq('真实后端 version 字段', st.version, '1.0');
  eq('真实后端 threshold 字段', st.threshold, 0.5);
  ok('真实后端 models 含 short/long 计数', st.models && 'short' in st.models && 'long' in st.models, st.models);

  const sr = await fetch(BASE + '/api/score', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(samplePayload)
  });
  eq('真实后端 /api/score 返回 200', sr.status, 200);
  const sd = await sr.json();
  eq('results 字段名与契约一致', Object.keys(sd.results[0]).sort(), ['id', 'length', 'model', 'rank', 'score', 'sequence']);
  const needSummary = ['count', 'max', 'mean', 'median', 'min', 'n_above_threshold'];
  ok('summary 含契约要求的全部字段（允许附加字段）',
    needSummary.every(k => k in sd.summary), Object.keys(sd.summary));
  eq('histogram 桶数', sd.histogram.length, 10);
  eq('histogram 桶字段名与契约一致', Object.keys(sd.histogram[0]).sort(), ['count', 'hi', 'lo']);
  ok('warnings 为数组', Array.isArray(sd.warnings));
  ok('elapsed_ms 为数字', typeof sd.elapsed_ms === 'number', sd.elapsed_ms);
  eq('results 条数', sd.results.length, EXPECT.count);
  ok('results 按 score 降序', isDesc(sd.results.map(r => r.score)));
  eq('rank 从 1 连续', sd.results.map(r => r.rank), sd.results.map((_, i) => i + 1));
  eq('model 取值 ∈ {short,long}', Array.from(new Set(sd.results.map(r => r.model))).sort().every(m => ['short', 'long'].includes(m)), true);

  const er = await fetch(BASE + '/api/export', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ format: 'csv' }, samplePayload))
  });
  eq('真实后端 /api/export 返回 200', er.status, 200);
  const ect = er.headers.get('Content-Type') || '';
  ok('export Content-Type 为 text/csv; charset=utf-8', ect.includes('text/csv') && ect.includes('utf-8'), ect);
  ok('export 带 Content-Disposition 附件名',
    /attachment;\s*filename="?peptideranker_scores\.csv"?/.test(er.headers.get('Content-Disposition') || ''),
    er.headers.get('Content-Disposition'));
  const ebuf = Buffer.from(await er.arrayBuffer());
  ok('export 带 UTF-8 BOM', ebuf[0] === 0xEF && ebuf[1] === 0xBB && ebuf[2] === 0xBF, ebuf.slice(0, 3).toString('hex'));
  const ehead = ebuf.slice(3).toString('utf8').split('\n')[0].replace(/\r$/, '');
  eq('export 表头与契约一致', ehead, 'rank,id,sequence,length,score,model');

  /* UI 侧：三档 length_handling 都能渲染出结果，且模型标签与档位一致 */
  $('sampleBtn').click();
  await waitFor(() => /共 15 条/.test(txt($('statCount'))), 3000);
  for (const mode of ['short', 'long', 'auto']) {
    $('lengthHandling').value = mode;
    $('scoreBtn').click();
    const labels = () => rows().map((r, i) => modelOf(i));
    const good = await waitFor(() => {
      if (D().body.classList.contains('is-loading')) return false;
      const ls = labels();
      if (ls.length !== EXPECT.count) return false;
      if (mode === 'auto') return true;
      return ls.every(l => (mode === 'short' ? l.includes('短肽') : l.includes('长肽')));
    }, 20000);
    ok('UI 切换 length_handling=' + mode + ' 后结果与档位一致', good, labels().slice(0, 4));
  }
  $('lengthHandling').value = 'auto';
}

/* ===================== CSS 类名覆盖（静态排版检查） ====================== */
{
  // 分两轮采集：非法行状态 + 结果状态，两次的类名取并集
  const used = new Set();
  const collect = () => D().querySelectorAll('*').forEach(el => el.classList._list().forEach(c => used.add(c)));

  setInput('ILPILSLIGGLL\nRPPGF1SPFR');
  await sleep(220);
  collect();

  $('sampleBtn').click();
  await sleep(150);
  $('scoreBtn').click();
  await waitFor(() => rows().length === EXPECT.count, 8000);
  collect();

  const cssBody = cssSrc.replace(/\/\*[\s\S]*?\*\//g, '');
  const missing = Array.from(used).filter(cls => {
    const esc = cls.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
    return !new RegExp('\\.' + esc + '(?![\\w-])').test(cssBody);
  });
  ok('渲染后所有用到的 class 都在 style.css 中有样式' + (missing.length ? '：缺 ' + missing.join(',') : ''), missing.length === 0);
  ['row--above', 'rank--1', 'score__bar', 'tag--short', 'tag--threshold', 'hist__bar',
    'ln--bad', 'tag--local', 'toast--ok'].forEach(cls => {
    ok('动态类 ' + cls + ' 已实际渲染并被 CSS 覆盖', used.has(cls) &&
      new RegExp('\\.' + cls.replace(/[-]/g, '\\-') + '(?![\\w-])').test(cssBody), Array.from(used).length);
  });
}

/* ================= 阶段 2~4：故障路径（仅 mock 可控故障模式） ============ */
if (!REAL) {
/* ========================= 阶段 2：ready=false =========================== */
await setMode('notready');
{
  newPage();
  ok('(未就绪) 页面未白屏', !!$('seqInput') && !!$('scoreBtn'));
  ok('(未就绪) 等到错误状态', await waitFor(() => $('statusBadge').dataset.state === 'error', 8000));
  eq('(未就绪) 徽章文案', txt($('statusTitle')), '引擎未就绪');
  ok('(未就绪) 错误条可见', $('errorBar').hidden === false);
  eq('(未就绪) 错误条标题', txt($('errorTitle')), '引擎未就绪');
  ok('(未就绪) 文本来自后端 error 字段', txt($('errorText')).includes('模型文件缺失'), txt($('errorText')));
  eq('(未就绪) role=alert', $('errorBar').getAttribute('role'), 'alert');
  $('sampleBtn').click();
  await sleep(150);
  eq('(未就绪) 载入示例仍更新统计', txt($('statCount')), `共 ${EXPECT.count} 条序列，最长 ${EXPECT.maxLen}`);
  ok('(未就绪) 打分按钮禁用', $('scoreBtn').disabled === true);
  ok('(未就绪) 禁用按钮带原因', String($('scoreBtn').title).length > 0, $('scoreBtn').title);
  $('errorCloseBtn').click();
  ok('(未就绪) 错误条可关闭', $('errorBar').hidden === true);
  ok('(未就绪) 关闭后仍显示引擎异常', $('statusBadge').dataset.state === 'error');
  ok('(未就绪) 无未捕获异常', current.hooks.errors.length === 0, current.hooks.errors.slice(0, 3));
}

/* ========================== 阶段 3：/api/status 503 ====================== */
await setMode('down');
{
  newPage();
  ok('(503) 页面未白屏', !!$('seqInput') && !!$('scoreBtn'));
  ok('(503) 等到错误状态', await waitFor(() => $('statusBadge').dataset.state === 'error', 8000));
  eq('(503) 徽章文案', txt($('statusTitle')), '引擎不可达');
  ok('(503) 错误条可见', $('errorBar').hidden === false);
  ok('(503) 错误文本含后端信息', /服务不可用|HTTP 503/.test(txt($('errorText'))), txt($('errorText')));
  ok('(503) 副标题展示原因', txt($('statusMeta')).length > 0, txt($('statusMeta')));
  ok('(503) 打分按钮禁用', $('scoreBtn').disabled === true);
  ok('(503) 重试按钮可用', $('recheckBtn').disabled === false);
  ok('(503) 无未捕获异常', current.hooks.errors.length === 0, current.hooks.errors.slice(0, 3));
}

/* ================= 阶段 4b：503 + ready=false（真实后端形态） ============ */
if (!REAL) {
  await setMode('notready503');
  newPage();
  ok('(503未就绪) 页面未白屏', !!$('seqInput') && !!$('scoreBtn'));
  ok('(503未就绪) 等到错误状态', await waitFor(() => $('statusBadge').dataset.state === 'error', 8000));
  eq('(503未就绪) 徽章按契约语义显示未就绪', txt($('statusTitle')), '引擎未就绪');
  ok('(503未就绪) 错误文本来自后端 error 字段', txt($('errorText')).includes('模型文件缺失'), txt($('errorText')));
  ok('(503未就绪) 打分按钮禁用', $('scoreBtn').disabled === true);
  $('sampleBtn').click();
  await sleep(150);
  ok('(503未就绪) 载入示例仍可用', txt($('statCount')) === `共 ${EXPECT.count} 条序列，最长 ${EXPECT.maxLen}`, txt($('statCount')));
  ok('(503未就绪) 无未捕获异常', current.hooks.errors.length === 0, current.hooks.errors.slice(0, 3));
}

/* ========================== 阶段 4：/api/score 500 ======================= */
await setMode('err500');
{
  newPage();
  ok('(500) 页面未白屏', !!$('seqInput') && !!$('scoreBtn'));
  ok('(500) 状态仍就绪', await waitFor(() => $('statusBadge').dataset.state === 'ready', 8000));
  $('sampleBtn').click();
  await sleep(150);
  $('scoreBtn').click();
  ok('(500) 等到打分错误', await waitFor(() => $('errorBar').hidden === false, 10000));
  eq('(500) 错误条标题', txt($('errorTitle')), '打分失败');
  ok('(500) 错误文本来自 error 字段', txt($('errorText')).includes('打分引擎内部错误'), txt($('errorText')));
  ok('(500) 加载态复位', D().body.classList.contains('is-loading') === false);
  ok('(500) 页面结构仍完整', !!$('resultMeta') && !!$('histogram') && $('resultsEmpty').hidden === false);
  ok('(500) 打分按钮恢复可用', $('scoreBtn').disabled === false);
  $('errorCloseBtn').click();
  ok('(500) 错误条可关闭', $('errorBar').hidden === true);
  ok('(500) 无未捕获异常', current.hooks.errors.length === 0, current.hooks.errors.slice(0, 3));
}

await setMode('ok');
} else {
  console.log('（REAL_BACKEND=1：跳过 mock 专属的 ready=false / 503 / 500 故障路径）');
}

/* ================================ 输出 ================================== */
console.log(`\n端到端（DOM 垫片，${REAL ? '真实后端 ' + BASE : 'mock ' + BASE}）测试：${pass} 通过 / ${fail} 失败`);
failures.forEach(f => console.log('  FAIL ' + f.name + (f.extra !== null ? '  ' + JSON.stringify(f.extra) : '')));
process.exit(fail ? 1 : 0);
