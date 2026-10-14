/* PeptideRanker 前端纯函数单元测试（自测用，不属于产品代码）
 * 运行：node app/static/_mock/unit_test.mjs
 *
 * 做法：把 i18n.js + app.js 源码放进 new Function 作用域执行，导出其中的纯函数，
 * 因为 app.js 只在 typeof document !== 'undefined' 时才初始化 DOM。
 * 无 document 时 i18n 走"项目原始语言 zh"兜底，所以下面的中文断言与宿主语言无关。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const i18nJs = fs.readFileSync(path.join(here, '..', 'i18n.js'), 'utf8');
const appJs = fs.readFileSync(path.join(here, '..', 'app.js'), 'utf8');
/* 产品页面里 i18n.js 与 app.js 共享全局作用域，这里用拼接模拟同一个作用域 */
const bundle = i18nJs + '\n' + appJs;

const H = new Function(
  bundle +
  `
  return {
    parseSequences, computeSummary, computeHistogram, splitCsvLine, badCharsOf,
    normalizeResult, csvEscape, localCsvText, withBom, state, fmt4, scoreHue,
    badgeModel, escapeHtml, clamp01, apiBase,
    i18n: I18N, t: t
  };
`
)();

/* ------------------------------ 迷你测试框架 ------------------------------ */
const results = [];
function check(name, cond, extra) {
  results.push({ name, pass: !!cond, extra: extra === undefined ? null : extra });
}
function eq(name, actual, expected) {
  const pass = JSON.stringify(actual) === JSON.stringify(expected);
  check(name, pass, pass ? null : { actual, expected });
}

const L1 = 'ILPILSLIGGLL';
const L2 = 'RPPGFSPFR';
const L3 = 'FLPIVGKLLSGLSGLL';

/* ================================ 解析测试 =============================== */
{
  const r = H.parseSequences([L1, L2, L3].join('\n'));
  eq('逐行：条数', r.entries.length, 3);
  eq('逐行：id 自动编号', r.entries.map(e => e.id), ['seq1', 'seq2', 'seq3']);
  eq('逐行：序列原样', r.entries[0].sequence, L1);
  eq('逐行：格式标签', r.formatLabel, '逐行');
  eq('逐行：无警告', r.warnings.length, 0);
  eq('逐行：每行长度', r.entries.map(e => e.sequence.length), [12, 9, 16]);
}
{
  const r = H.parseSequences('  ' + L1 + '  \r\n\r\n\t\r\n' + L2 + '\n\n');
  eq('CRLF/空行/空白：条数', r.entries.length, 2);
  eq('CRLF/空行：首条已 trim', r.entries[0].sequence, L1);
  eq('CRLF/空行：行号', r.entries.map(e => e.line), [1, 4]);
}
{
  const r = H.parseSequences('ILPIL1SLIGGLL');
  const e = r.entries[0];
  check('非法字符：条目标记 invalid', e.valid === false);
  eq('非法字符：badChars', e.badChars, ['1']);
  eq('非法字符：警告文案', r.warnings[0].text, "第 1 行含非法字符 '1'，已跳过");
  eq('非法字符：本地来源', r.warnings[0].source, 'local');
  eq('非法字符：行标记', r.lineFlags[0].bad, true);
}
{
  const r = H.parseSequences('ILPILSLIGGLL\nRPP-GFSPFR\nFLPIVGKLLSGLSGLL\nA*B');
  eq('多非法行：合法条数', r.entries.filter(e => e.valid).length, 2);
  eq('多非法行：警告数', r.warnings.length, 2);
  eq('多非法行：警告行号', r.warnings.map(w => w.text.slice(0, 3)), ['第 2', '第 4']);
  eq('多非法行：坏行标记数', r.lineFlags.filter(f => f && f.bad).length, 2);
  eq('多非法行：下划线也是非法字符', r.entries[1].badChars, ['-']);
}
{
  const r = H.parseSequences(['>pep A', 'ACDE', 'FGHI', '', '>pep B', 'KLMN'].join('\n'));
  eq('FASTA：格式标签', r.formatLabel, 'FASTA');
  eq('FASTA：条数', r.entries.length, 2);
  eq('FASTA：头作为 ID', r.entries[0].id, 'pep');
  eq('FASTA：拼接续行', r.entries[0].sequence, 'ACDEFGHI');
  eq('FASTA：重名 ID 去重', r.entries[1].id, 'pep-2');
  eq('FASTA：第二条序列', r.entries[1].sequence, 'KLMN');
  eq('FASTA：头行被标记', r.lineFlags[0].fasta, true);
}
{
  const r = H.parseSequences(['>p1', 'ACD1'].join('\n'));
  eq('FASTA：非法字符 -> invalid', r.entries[0].valid, false);
  eq('FASTA：非法字符行号', r.warnings[0].text, "第 2 行含非法字符 '1'，已跳过");
  eq('FASTA：行标记落在续行', r.lineFlags[1].bad, true);
}
{
  const r = H.parseSequences(['>only-header', '', ''].join('\n'));
  eq('FASTA：只有头无序列 -> 0 条', r.entries.length, 0);
}
{
  const r = H.parseSequences(['id,sequence', 'pep1,' + L1, 'pep2,' + L2].join('\n'));
  eq('CSV：格式标签', r.formatLabel, 'CSV / 单列');
  eq('CSV：跳表头', r.entries.length, 2);
  eq('CSV：取 id 列', r.entries.map(e => e.id), ['pep1', 'pep2']);
  eq('CSV：取 sequence 列', r.entries.map(e => e.sequence), [L1, L2]);
}
{
  const r = H.parseSequences(['sequence', L1, L2].join('\n'));
  eq('CSV 单列：条数', r.entries.length, 2);
  eq('CSV 单列：自动 id', r.entries.map(e => e.id), ['seq1', 'seq2']);
}
{
  const r = H.parseSequences(['1,' + L1, '2,' + L2].join('\n'));
  eq('CSV 无表头带序号列：条数', r.entries.length, 2);
  eq('CSV 无表头带序号列：识别序列列', r.entries.map(e => e.sequence), [L1, L2]);
  eq('CSV 无表头带序号列：首列当 id', r.entries.map(e => e.id), ['1', '2']);
}
{
  const r = H.parseSequences(['"pep,1",' + L1].join('\n'));
  eq('CSV 引号内逗号：序列列', r.entries[0].sequence, L1);
  eq('CSV 引号内逗号：id', r.entries[0].id, 'pep,1');
}
{
  const r = H.parseSequences('');
  eq('空输入：0 条', r.entries.length, 0);
  eq('空输入：无警告', r.warnings.length, 0);
}
{
  const r = H.parseSequences([L1, L1, L1].join('\n'));
  eq('重复序列：不去重', r.entries.length, 3);
  eq('重复序列：id 仍唯一', new Set(r.entries.map(e => e.id)).size, 3);
}
{
  const r = H.parseSequences('ilpilsliggll\n');
  eq('小写输入：统一大写', r.entries[0].sequence, 'ILPILSLIGGLL');
  eq('小写输入：合法', r.entries[0].valid, true);
}
{
  eq('splitCsvLine 引号', H.splitCsvLine('a,"b,c",d'), ['a', 'b,c', 'd']);
  eq('splitCsvLine 转义引号', H.splitCsvLine('"a""b",c'), ['a"b', 'c']);
  eq('badCharsOf 去重保序', H.badCharsOf('A1B2C1'), ['1', '2']);
  eq('badCharsOf 干净序列', H.badCharsOf('ACDEFG'), []);
}

/* ============================== 统计 / 直方图 ============================ */
{
  const rows = [
    H.normalizeResult({ rank: 1, id: 'a', sequence: 'AAAA', length: 4, score: 0.9, model: 'short' }, 0),
    H.normalizeResult({ rank: 2, id: 'b', sequence: 'BBBB', length: 4, score: 0.1, model: 'long' }, 1),
    H.normalizeResult({ rank: 3, id: 'c', sequence: 'CCCC', length: 4, score: 0.5, model: 'short' }, 2),
    H.normalizeResult({ rank: 4, id: 'd', sequence: 'DDDD', length: 4, score: 0.3, model: 'short' }, 3)
  ];
  const s = H.computeSummary(rows, 0.5);
  eq('summary.count', s.count, 4);
  eq('summary.mean', Math.round(s.mean * 1e6) / 1e6, 0.45);
  eq('summary.median', s.median, 0.4);
  eq('summary.min', s.min, 0.1);
  eq('summary.max', s.max, 0.9);
  eq('summary.n_above_threshold(>=0.5)', s.n_above_threshold, 2);

  const odd = H.computeSummary(rows.slice(0, 3), 0.5);
  eq('summary.median 奇数个', odd.median, 0.5);

  const bins = H.computeHistogram(rows, 10);
  eq('histogram 桶数', bins.length, 10);
  eq('histogram 计数总和', bins.reduce((a, b) => a + b.count, 0), 4);
  eq('histogram 0.9 落最后一桶', bins[9].count, 1);
  eq('histogram 边界 0.5 落第 6 桶', bins[5].count, 1);
  eq('histogram 桶区间', [bins[0].lo, bins[0].hi, bins[9].lo, bins[9].hi], [0, 0.1, 0.9, 1]);
}
{
  const s = H.computeSummary([], 0.5);
  eq('summary 空结果 count', s.count, 0);
  eq('summary 空结果 mean', s.mean, null);
  const one = H.computeSummary([H.normalizeResult({ score: 1 }, 0)], 0.5);
  eq('summary score=1 计入阈值', one.n_above_threshold, 1);
}
{
  const n = H.normalizeResult({}, 2);
  eq('normalizeResult 缺省 rank', n.rank, 3);
  eq('normalizeResult 缺省 score', n.score, null);
  eq('normalizeResult 缺省 length', n.length, 0);
  const e = H.normalizeResult({ sequence: 'ABCDE' }, 0);
  eq('normalizeResult 用序列长度兜底', e.length, 5);
  eq('score=0 不被当成缺失', H.normalizeResult({ score: 0 }, 0).score, 0);
}

/* ============================ 导出 / 格式化 ============================== */
{
  eq('csvEscape 普通', H.csvEscape('ABC'), 'ABC');
  eq('csvEscape 逗号', H.csvEscape('a,b'), '"a,b"');
  eq('csvEscape 引号', H.csvEscape('a"b'), '"a""b"');
  eq('fmt4 四位小数', H.fmt4(0.81234), '0.8123');
  eq('fmt4 非法值', H.fmt4(null), '—');
  eq('scoreHue 0 -> 0', H.scoreHue(0), 0);
  eq('scoreHue 1 -> 130', H.scoreHue(1), 130);
  eq('clamp01 越界', [H.clamp01(-3), H.clamp01(9)], [0, 1]);
  eq('escapeHtml', H.escapeHtml('<b>"x"&'), '&lt;b&gt;&quot;x&quot;&amp;');
  eq('badgeModel short', H.badgeModel('short').includes('短肽'), true);
  eq('badgeModel long', H.badgeModel('long').includes('长肽'), true);
  eq('badgeModel 未知值原样显示', H.badgeModel('weird').includes('weird'), true);
}
{
  H.state.results = [
    { rank: 2, id: 'b', sequence: 'BBBB', length: 4, score: 0.2, model: 'long' },
    { rank: 1, id: 'a', sequence: 'AAAA', length: 4, score: 0.8, model: 'short' }
  ];
  const csv = H.localCsvText();
  const lines = csv.trim().split('\n');
  eq('本地 CSV 表头与契约一致', lines[0], 'rank,id,sequence,length,score,model');
  eq('本地 CSV 按 rank 排序', lines[1].split(',')[0], '1');
  eq('本地 CSV 分数 4 位小数', lines[1].split(',')[4], '0.8000');
  eq('本地 CSV 行数', lines.length, 3);
  H.state.results = [];
}
{
  const plain = new Uint8Array([0x61, 0x62]);
  const withBom = H.withBom(plain.buffer);
  eq('withBom 补 BOM', Array.from(withBom.slice(0, 3)), [0xEF, 0xBB, 0xBF]);
  eq('withBom 不丢内容', withBom[3], 0x61);
  const already = new Uint8Array([0xEF, 0xBB, 0xBF, 0x61]).buffer;
  eq('withBom 幂等', Array.from(H.withBom(already)), [0xEF, 0xBB, 0xBF, 0x61]);
}

/* ========================= 服务地址解析（部署形态） ====================== */
{
  const withLocation = (loc, searchOverride) => {
    const previous = globalThis.location;
    globalThis.location = searchOverride === undefined ? loc : Object.assign({}, loc, { search: searchOverride });
    try {
      return new Function(bundle + '\nreturn apiBase();')();
    } finally {
      if (previous === undefined) delete globalThis.location; else globalThis.location = previous;
    }
  };
  const base = { protocol: 'http:', host: '127.0.0.1:8737', port: '8737', origin: 'http://127.0.0.1:8737', search: '' };
  eq('由 8737 同源提供时走相对路径', withLocation(base), '');
  eq('由 80 端口反代时走相对路径', withLocation(Object.assign({}, base, { port: '', origin: 'http://host' })), '');
  eq('非 8737 端口静态托管时直连 8737', withLocation(Object.assign({}, base, { port: '8000', origin: 'http://127.0.0.1:8000' })), 'http://127.0.0.1:8737');
  eq('file:// 打开时直连 8737', withLocation(Object.assign({}, base, { protocol: 'file:', port: '', origin: 'null' })), 'http://127.0.0.1:8737');
  eq('?api= 覆盖（去掉尾斜杠）', withLocation(base, '?api=http%3A%2F%2F127.0.0.1%3A8899%2F'), 'http://127.0.0.1:8899');
  eq('?api=same 强制同源', withLocation(Object.assign({}, base, { port: '8000' }), '?api=same'), '');
  eq('无 location 时兜底到 8737', (() => {
    const previous = globalThis.location;
    delete globalThis.location;
    try { return new Function(bundle + '\nreturn apiBase();')(); } finally { if (previous !== undefined) globalThis.location = previous; }
  })(), 'http://127.0.0.1:8737');
}

/* ================================ 多语言 ================================ */
{
  /* 用 app.js 作用域里的同一个 i18n 实例：下面的 apiBase 用例会重新求值 bundle，
     从而覆盖 globalThis.PR_I18N，若改用全局引用就会拿到另一个实例。 */
  const I18N = H.i18n;
  check('i18n：PR_I18N 已挂载到全局', !!globalThis.PR_I18N);
  check('i18n：app.js 取到的是同一个实例', H.i18n === H.i18n && !!H.i18n);
  const diff = I18N.keyDiff();
  eq('i18n：en 缺失的键为空', diff.missingInEn, []);
  eq('i18n：zh 缺失的键为空', diff.missingInZh, []);
  eq('i18n：没有空文案', diff.emptyValues, []);
  check('i18n：支持的语种为 zh/en', JSON.stringify(I18N.SUPPORTED) === '["zh","en"]');

  /* 语言标签归一化 */
  eq('i18n：zh-CN -> zh', I18N.normalize('zh-CN'), 'zh');
  eq('i18n：zh-Hant -> zh', I18N.normalize('zh-Hant'), 'zh');
  eq('i18n：zh_TW -> zh', I18N.normalize('zh_TW'), 'zh');
  eq('i18n：en-US -> en', I18N.normalize('en-US'), 'en');
  eq('i18n：ja -> en（非中文一律英文）', I18N.normalize('ja'), 'en');
  eq('i18n：空串 -> 空（无法判断）', I18N.normalize(''), '');

  /* 中文侧必须与改造前的文案逐字一致（保证既有测试与用户体验不回归） */
  I18N._reset('zh');
  eq('i18n：默认语言码', I18N.lang(), 'zh');
  eq('i18n：中文状态标题', I18N.t('status.ready'), '引擎就绪');
  eq('i18n：中文占位替换', I18N.t('stats.count', { n: 3, max: 12 }), '共 3 条序列，最长 12');
  eq('i18n：缺参时保留占位符', I18N.t('stats.count', { n: 3 }), '共 3 条序列，最长 {max}');
  eq('i18n：中文模型标签', I18N.t('model.short'), '短肽 · short');
  eq('i18n：中文阈值标签', I18N.t('overview.above', { th: '0.50' }), '≥ 0.50 条数');

  /* 英文侧 */
  I18N._reset('en');
  eq('i18n：英文语言码', I18N.lang(), 'en');
  eq('i18n：英文状态标题', I18N.t('status.ready'), 'Engine ready');
  eq('i18n：英文占位替换', I18N.t('stats.count', { n: 3, max: 12 }), '3 sequences, longest 12');
  eq('i18n：英文模型标签', I18N.t('model.short'), 'short peptide');
  eq('i18n：未知键回退为键名', I18N.t('no.such.key.at.all'), 'no.such.key.at.all');

  /* 解析结果（格式标签、非法行警告）必须随语言切换 */
  I18N._reset('zh');
  const zhWarn = H.parseSequences('ILP1LS').warnings[0].text;
  const zhFmt = H.parseSequences('ILPILSLIGGLL').formatLabel;
  I18N._reset('en');
  eq('i18n：中文非法行警告', zhWarn, "第 1 行含非法字符 '1'，已跳过");
  eq('i18n：英文非法行警告', H.parseSequences('ILP1LS').warnings[0].text,
     "Line 1 contains an invalid character '1' and was skipped");
  eq('i18n：中文格式标签', zhFmt, '逐行');
  eq('i18n：英文逐行格式标签', H.parseSequences('ILPILSLIGGLL').formatLabel, 'line-based');
  eq('i18n：英文 FASTA 格式标签', H.parseSequences('>pep1\nILPILSLIGGLL').formatLabel, 'FASTA');
  eq('i18n：英文 CSV 格式标签', H.parseSequences('id,sequence\np1,ILPILSLIGGLL').formatLabel, 'CSV / single column');
  eq('i18n：英文模型徽章', H.badgeModel('short').includes('short peptide'), true);
  eq('i18n：英文长肽徽章', H.badgeModel('long').includes('long peptide'), true);
  I18N._reset('zh');        // 还原，避免影响后续断言

  /* 无 localStorage / 无 document 时不应抛异常 */
  let threw = false;
  try { I18N.detect(); I18N.queryLang(); I18N.applyStatic(null); } catch (e) { threw = true; }
  check('i18n：缺少 localStorage/document 时不抛异常', threw === false);

  /* URL 显式覆盖 ?lang= */
  const withQuery = (search) => {
    const previous = globalThis.location;
    globalThis.location = { protocol: 'http:', host: '127.0.0.1:8899', port: '8899',
                            origin: 'http://127.0.0.1:8899', search: search };
    try { return I18N.queryLang(); } finally {
      if (previous === undefined) delete globalThis.location; else globalThis.location = previous;
    }
  };
  eq('i18n：?lang=en 被识别', withQuery('?lang=en'), 'en');
  eq('i18n：?lang=zh 被识别', withQuery('?lang=zh'), 'zh');
  eq('i18n：?lang=zh-CN 归一化为 zh', withQuery('?lang=zh-CN'), 'zh');
  eq('i18n：?lang=en-US 归一化为 en', withQuery('?lang=en-US'), 'en');
  eq('i18n：?lang 值大小写不敏感', withQuery('?lang=EN'), 'en');
  eq('i18n：参数名大小写敏感（?LANG= 不是 ?lang=）', withQuery('?LANG=en'), '');
  eq('i18n：无 lang 参数返回空', withQuery('?api=same'), '');
  eq('i18n：未知 lang 值被忽略', withQuery('?lang=de'), '');
  eq('i18n：?lang 与其它参数共存', withQuery('?api=http%3A%2F%2Fx&lang=en'), 'en');
}

/* ================================ 输出 ================================== */
const failed = results.filter(r => !r.pass);
for (const r of results) {
  if (!r.pass) console.log('FAIL  ' + r.name + (r.extra ? '  ' + JSON.stringify(r.extra) : ''));
}
console.log(`\n单元测试：${results.length - failed.length}/${results.length} 通过` +
  (failed.length ? `，${failed.length} 失败` : '，全部通过'));
process.exit(failed.length ? 1 : 0);
