/* PeptideRanker 前端真实浏览器冒烟测试（自测用，不属于产品代码）
 *
 * 用 Chrome/Edge 的 DevTools 协议（CDP）驱动无头浏览器，对 _mock/mock_server.py
 * 提供的页面做端到端断言：渲染、加载态、表格/概览/直方图、排序、筛选、快捷键、
 * 复制、导出下载、中英双语界面切换（含英文截图），
 * 以及 ready=false / 503 / 500 三种故障路径，并截图。
 *
 * 前置：mock 服务已在 8899 端口运行
 *   D:\\01APP\\51python3.14.3\\python.exe app/static/_mock/mock_server.py --port 8899
 * 运行：node app/static/_mock/smoke.mjs
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const staticDir = path.join(here, '..');
const ART = path.join(here, '_artifacts');
const DL = path.join(ART, 'downloads');
const BASE = process.env.MOCK_BASE || 'http://127.0.0.1:8899';
const DEBUG_PORT = Number(process.env.CDP_PORT || 9333);

fs.rmSync(ART, { recursive: true, force: true });
fs.mkdirSync(DL, { recursive: true });

const appJs = fs.readFileSync(path.join(staticDir, 'app.js'), 'utf8');
const exampleText = new Function(appJs + '\nreturn EXAMPLE_SEQUENCES;')();
const exampleSeqs = exampleText.split('\n');
const EXPECT = {
  sampleCount: exampleSeqs.length,
  maxLen: Math.max(...exampleSeqs.map(s => s.length))
};

const BUNDLES = [
  { name: 'chrome', exe: process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' },
  { name: 'edge', exe: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe' }
];

const sleep = ms => new Promise(r => setTimeout(r, ms));

/* --------------------------------- CDP 客户端 ------------------------------ */
class CDP {
  constructor(ws) {
    this.ws = ws;
    this.seq = 0;
    this.pending = new Map();
    this.handlers = [];
    ws.addEventListener('message', ev => {
      let msg;
      try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString()); } catch { return; }
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message + ' (' + msg.error.code + ')')); else resolve(msg.result);
      } else if (msg.method) {
        this.handlers.forEach(h => { try { h(msg); } catch { /* ignore */ } });
      }
    });
  }
  on(fn) { this.handlers.push(fn); }
  send(method, params = {}, sessionId) {
    const id = ++this.seq;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.ws.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (this.pending.has(id)) { this.pending.delete(id); reject(new Error('CDP 超时: ' + method)); }
      }, 30000);
    });
  }
}

async function httpJson(url, timeout = 8000) {
  const res = await fetch(url, { signal: AbortSignal.timeout(timeout) });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

async function waitHttp(url, timeout = 20000) {
  const t0 = Date.now();
  for (;;) {
    try { return await httpJson(url, 3000); } catch { /* retry */ }
    if (Date.now() - t0 > timeout) throw new Error('等不到 ' + url);
    await sleep(250);
  }
}

function launchBrowser(bundle) {
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'pr-cdp-'));
  const args = [
    '--headless=new',
    '--remote-debugging-port=' + DEBUG_PORT,
    '--remote-allow-origins=*',
    '--user-data-dir=' + userData,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-background-networking',
    '--disable-gpu',
    '--mute-audio',
    '--window-size=1440,1100',
    '--force-device-scale-factor=1',
    'about:blank'
  ];
  const child = spawn(bundle.exe, args, { stdio: 'ignore', detached: false, windowsHide: true });
  return { child, userData };
}

/* --------------------------------- 结果收集 -------------------------------- */
const report = { phases: [], consoleErrors: [], exceptions: [], logNetworkErrors: [], downloads: [] };
let failures = 0;

function recordPhase(name, out) {
  report.phases.push({ name, pass: out.pass, fail: out.fail, steps: out.steps });
  failures += out.fail;
  console.log(`\n=== ${name}：${out.pass} 通过 / ${out.fail} 失败 ===`);
  out.steps.filter(s => !s.pass).forEach(s => {
    console.log('  FAIL ' + s.name + (s.extra ? '  ' + JSON.stringify(s.extra) : ''));
  });
}

/* ----------------------------------- 主流程 -------------------------------- */
let browser = null;
let cdp = null;
let session = null;
let ws = null;

async function main() {
  const browserTestSrc = fs.readFileSync(path.join(here, 'browser_test.js'), 'utf8');

  let launched = null;
  for (const bundle of BUNDLES) {
    if (!fs.existsSync(bundle.exe)) continue;
    launched = { bundle, ...launchBrowser(bundle) };
    try {
      await waitHttp(`http://127.0.0.1:${DEBUG_PORT}/json/version`, 20000);
      console.log(`[smoke] 已启动 ${bundle.name}: ${bundle.exe}`);
      break;
    } catch (e) {
      console.log(`[smoke] ${bundle.name} 启动失败：${e.message}`);
      try { launched.child.kill(); } catch { /* ignore */ }
      launched = null;
    }
  }
  if (!launched) throw new Error('未找到可用的 Chrome/Edge');
  browser = launched;

  const version = await httpJson(`http://127.0.0.1:${DEBUG_PORT}/json/version`);
  ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve);
    ws.addEventListener('error', e => reject(new Error('WS 连接失败')));
  });
  cdp = new CDP(ws);

  const target = await cdp.send('Target.createTarget', { url: 'about:blank' });
  session = (await cdp.send('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId;

  cdp.on(msg => {
    if (msg.method === 'Runtime.exceptionThrown') {
      report.exceptions.push(JSON.stringify(msg.params.exceptionDetails).slice(0, 500));
    } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
      report.consoleErrors.push(msg.params.args.map(a => a.value || a.description || a.type).join(' ').slice(0, 300));
    } else if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error') {
      report.logNetworkErrors.push((msg.params.entry.source + ': ' + msg.params.entry.text).slice(0, 300));
    }
  });

  await cdp.send('Runtime.enable', {}, session);
  await cdp.send('Log.enable', {}, session);
  await cdp.send('Page.enable', {}, session);
  await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true }, session);
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: DL, eventsEnabled: true });
  try {
    await cdp.send('Browser.grantPermissions', {
      origin: BASE, permissions: ['clipboardReadWrite', 'clipboardSanitizedWrite']
    });
  } catch (e) {
    console.log('[smoke] 剪贴板授权失败（不致命）：' + e.message);
  }

  const evaluate = async (expression, opts = {}) => {
    const res = await cdp.send('Runtime.evaluate', {
      expression, awaitPromise: true, returnByValue: true, ...opts
    }, session);
    if (res.exceptionDetails) {
      const d = res.exceptionDetails;
      throw new Error('页面脚本异常：' + (d.exception && d.exception.description ? d.exception.description : JSON.stringify(d)).slice(0, 600));
    }
    return res.result.value;
  };

  const waitPageReady = async (url) => {
    await cdp.send('Page.navigate', { url }, session);
    const t0 = Date.now();
    for (;;) {
      try {
        const ok = await evaluate('document.readyState === "complete" && !window.__PR_TESTS && !!document.getElementById("seqInput")');
        if (ok) break;
      } catch { /* 导航中上下文销毁，重试 */ }
      if (Date.now() - t0 > 20000) throw new Error('页面加载超时：' + url);
      await sleep(150);
    }
    await evaluate('window.__EXPECT = ' + JSON.stringify(EXPECT) + ';');
    await evaluate(browserTestSrc + '\n;true');
  };

  const setMode = async (mode) => {
    const res = await fetch(BASE + '/__mock/mode', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode })
    });
    if (!res.ok) throw new Error('切换 mock 模式失败：' + res.status);
  };

  const runPhase = async (fn) => {
    const out = await evaluate(`window.__PR_TESTS.${fn}()`);
    return out;
  };

  const shot = async (file, opts = {}) => {
    if (opts.metrics) await cdp.send('Emulation.setDeviceMetricsOverride', opts.metrics, session);
    if (opts.scroll !== undefined) {
      await evaluate('window.scrollTo(0, ' + opts.scroll + '); true');
      await sleep(250);
    }
    const res = await cdp.send('Page.captureScreenshot', { format: 'png', fromSurface: true }, session);
    fs.writeFileSync(path.join(ART, file), Buffer.from(res.data, 'base64'));
    console.log('[smoke] 截图 -> ' + file);
  };

  const PAGE_URL = BASE + '/?api=' + encodeURIComponent(BASE);

  /* ---- 阶段 1：正常流程 ---- */
  await setMode('ok');
  await waitPageReady(PAGE_URL);
  recordPhase('正常流程（渲染/统计/打分/排序/筛选/非法行/快捷键/复制）', await runPhase('main'));

  /* 截图：宽屏 */
  await shot('01-main.png', { metrics: { width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false } });
  await evaluate("document.querySelector('.area-results').scrollIntoView({block:'start'}); true");
  await sleep(300);
  await shot('02-results.png');
  await evaluate("window.scrollTo(0, document.body.scrollHeight); true");
  await sleep(300);
  await shot('03-bottom.png');

  /* 导出下载校验 */
  await evaluate("document.querySelector('#exportBtn').click(); true");
  const csvFile = await (async () => {
    const t0 = Date.now();
    for (;;) {
      const files = fs.existsSync(DL) ? fs.readdirSync(DL).filter(f => f.endsWith('.csv')) : [];
      if (files.length) return path.join(DL, files[0]);
      if (Date.now() - t0 > 8000) return null;
      await sleep(200);
    }
  })();
  if (!csvFile) {
    failures++;
    report.downloads.push({ name: '导出 CSV 下载', pass: false, extra: '未在 8s 内看到下载文件' });
    console.log('  FAIL 导出 CSV 未产生下载文件');
  } else {
    const buf = fs.readFileSync(csvFile);
    const hasBom = buf[0] === 0xEF && buf[1] === 0xBB && buf[2] === 0xBF;
    const text = buf.slice(hasBom ? 3 : 0).toString('utf8');
    const lines = text.trim().split('\n');
    const head = lines[0].replace(/\r$/, '');
    const checks = [
      ['导出文件名 = peptideranker_scores.csv', path.basename(csvFile) === 'peptideranker_scores.csv', path.basename(csvFile)],
      ['导出 CSV 带 UTF-8 BOM', hasBom, buf.slice(0, 3).toString('hex')],
      ['导出表头与契约一致', head === 'rank,id,sequence,length,score,model', head],
      ['导出行数 = 序列数 + 表头', lines.length === EXPECT.sampleCount + 1, lines.length],
      ['导出分数 4 位小数', /,\d+\.\d{4},/.test(lines[1] || ''), lines[1]],
      ['导出按 rank 排序', (lines[1] || '').startsWith('1,'), lines[1]]
    ];
    let pass = 0, fail = 0;
    const steps = checks.map(([name, ok, extra]) => {
      if (ok) pass++; else fail++;
      return { name, pass: ok, extra: ok ? null : extra };
    });
    report.phases.push({ name: '导出 CSV（POST /api/export + 下载）', pass, fail, steps });
    failures += fail;
    console.log(`\n=== 导出 CSV：${pass} 通过 / ${fail} 失败 ===`);
    steps.filter(s => !s.pass).forEach(s => console.log('  FAIL ' + s.name + '  ' + JSON.stringify(s.extra)));
    report.downloads.push({ file: path.basename(csvFile), bytes: buf.length, bom: hasBom });
  }

  /* 窄屏响应式截图 */
  await shot('04-narrow.png', { metrics: { width: 420, height: 900, deviceScaleFactor: 2, mobile: true }, scroll: 0 });

  /* ---- 阶段：中英双语界面（结束时停在英文，故先截图再切回中文） ---- */
  await cdp.send('Emulation.clearDeviceMetricsOverride', {}, session);
  recordPhase('中英双语界面（静态+动态文案 / localStorage / <html lang>）', await runPhase('i18n'));
  await shot('06-english.png', { metrics: { width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false } });
  await cdp.send('Emulation.clearDeviceMetricsOverride', {}, session);
  recordPhase('中英双语界面：切回中文', await runPhase('i18nBack'));

  /* ---- 阶段 2：引擎未就绪 ---- */
  await cdp.send('Emulation.clearDeviceMetricsOverride', {}, session);
  await setMode('notready');
  await waitPageReady(PAGE_URL);
  recordPhase('故障路径：GET /api/status 返回 ready=false', await runPhase('notReady'));

  /* ---- 阶段 3：服务不可达 ---- */
  await setMode('down');
  await waitPageReady(PAGE_URL);
  recordPhase('故障路径：/api/status 503 服务不可达', await runPhase('down'));

  /* ---- 阶段 4：打分接口 500 ---- */
  await setMode('err500');
  await waitPageReady(PAGE_URL);
  recordPhase('故障路径：POST /api/score 500', await runPhase('err500'));
  await shot('05-error.png', { metrics: { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false }, scroll: 0 });

  await setMode('ok');

  /* ---- 控制台检查 ---- */
  console.log('\n=== 控制台 / 未捕获异常 ===');
  console.log('  console.error：' + report.consoleErrors.length + (report.consoleErrors.length ? ' -> ' + JSON.stringify(report.consoleErrors) : ''));
  console.log('  未捕获异常：' + report.exceptions.length + (report.exceptions.length ? ' -> ' + JSON.stringify(report.exceptions) : ''));
  console.log('  网络层 error 日志（故障路径下为预期）：' + report.logNetworkErrors.length);
  if (report.exceptions.length) failures += report.exceptions.length;
  if (report.consoleErrors.length) failures += report.consoleErrors.length;

  let totalPass = 0, totalFail = 0;
  report.phases.forEach(p => { totalPass += p.pass; totalFail += p.fail; });
  console.log(`\n================ 汇总：${totalPass} 通过 / ${totalFail} 失败` +
    `，未捕获异常 ${report.exceptions.length}，console.error ${report.consoleErrors.length} ================`);
  report.summary = { totalPass, totalFail, exceptions: report.exceptions.length, consoleErrors: report.consoleErrors.length, EXPECT };
  fs.writeFileSync(path.join(ART, 'report.json'), JSON.stringify(report, null, 2));
  console.log('[smoke] 报告 -> ' + path.join(ART, 'report.json'));
}

try {
  await main();
} catch (e) {
  failures++;
  console.log('\n[smoke] 运行失败：' + (e && e.stack ? e.stack : e));
} finally {
  try { if (ws) ws.close(); } catch { /* ignore */ }
  try { if (browser) browser.child.kill(); } catch { /* ignore */ }
  await sleep(300);
  process.exit(failures ? 1 : 0);
}
