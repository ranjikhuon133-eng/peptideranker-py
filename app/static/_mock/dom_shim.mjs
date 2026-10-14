/* 极简 DOM / 浏览器 API 垫片（自测用，不属于产品代码）
 *
 * 本机沙箱内 Chrome / Edge / WebView2 都无法启动（crashpad OpenProcess 被拒绝后自杀），
 * 因此用这个垫片在 Node 里加载真实的 index.html + app.js，配合 mock_server.py 提供的
 * 真实 HTTP 接口，端到端执行全部渲染与交互代码路径。
 *
 * 支持范围：HTML 子集解析、getElementById/querySelector(All)、classList、dataset、
 * style、hidden/disabled、事件冒泡与委托、innerHTML/textContent、Blob 下载钩子、
 * document.execCommand('copy') 钩子。不负责排版与 CSS 计算。
 */

const VOID_TAGS = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
  'link', 'meta', 'param', 'source', 'track', 'wbr']);

function decodeEntities(str) {
  return String(str).replace(/&(?:#(\d+)|#x([0-9a-fA-F]+)|(amp|lt|gt|quot|apos|nbsp));/gi,
    (m, dec, hex, name) => {
      if (dec) return String.fromCodePoint(Number(dec));
      if (hex) return String.fromCodePoint(parseInt(hex, 16));
      switch (String(name || '').toLowerCase()) {
        case 'amp': return '&';
        case 'lt': return '<';
        case 'gt': return '>';
        case 'quot': return '"';
        case 'apos': return "'";
        case 'nbsp': return '\u00a0';
        default: return m;
      }
    });
}

function kebab(prop) { return String(prop).replace(/[A-Z]/g, m => '-' + m.toLowerCase()); }

function parseStyleAttr(text) {
  const out = {};
  String(text || '').split(';').forEach(piece => {
    const i = piece.indexOf(':');
    if (i < 0) return;
    const k = piece.slice(0, i).trim();
    const v = piece.slice(i + 1).trim();
    if (k) out[k] = v;
  });
  return out;
}

function parseAttrString(text, el) {
  const re = /([^\s=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
  let m;
  while ((m = re.exec(text))) {
    const name = m[1].toLowerCase();
    const value = m[2] !== undefined ? m[2] : (m[3] !== undefined ? m[3] : (m[4] !== undefined ? m[4] : ''));
    el.attributes.set(name, decodeEntities(value));
  }
  return el;
}

/* ------------------------------ 选择器引擎 -------------------------------- */
function parseCompound(text) {
  const c = { tag: null, id: null, classes: [], attrs: [] };
  const re = /(\[[^\]]*\])|(#[A-Za-z0-9_-]+)|(\.[A-Za-z0-9_-]+)|([A-Za-z][A-Za-z0-9-]*)/g;
  let m;
  while ((m = re.exec(text))) {
    if (m[1]) {
      const inner = m[1].slice(1, -1);
      const eq = inner.indexOf('=');
      if (eq < 0) c.attrs.push({ name: inner.trim().toLowerCase(), value: null });
      else c.attrs.push({
        name: inner.slice(0, eq).trim().toLowerCase(),
        value: inner.slice(eq + 1).trim().replace(/^["']|["']$/g, '')
      });
    } else if (m[2]) c.id = m[2].slice(1);
    else if (m[3]) c.classes.push(m[3].slice(1));
    else if (m[4]) c.tag = m[4].toLowerCase();
  }
  return c;
}

function matchesCompound(el, c) {
  if (!el || el.nodeType !== 1) return false;
  if (c.tag && el.tagName !== c.tag) return false;
  if (c.id && el.getAttribute('id') !== c.id) return false;
  for (const cl of c.classes) if (!el.classList.contains(cl)) return false;
  for (const a of c.attrs) {
    const v = el.getAttribute(a.name);
    if (v === null) return false;
    if (a.value !== null && v !== a.value) return false;
  }
  return true;
}

function matchesSelector(el, selector) {
  const compounds = String(selector).trim().split(/\s+/).map(parseCompound);
  if (!compounds.length) return false;
  let idx = compounds.length - 1;
  if (!matchesCompound(el, compounds[idx])) return false;
  idx--;
  let node = el.parentNode;
  while (idx >= 0 && node) {
    if (matchesCompound(node, compounds[idx])) idx--;
    node = node.parentNode;
  }
  return idx < 0;
}

/* --------------------------------- 节点 ---------------------------------- */
let UID = 0;

class ClassList {
  constructor(el) { this.el = el; }
  _list() { return String(this.el.getAttribute('class') || '').split(/\s+/).filter(Boolean); }
  _set(list) { this.el.setAttribute('class', list.join(' ')); }
  contains(c) { return this._list().indexOf(c) >= 0; }
  add() { const l = this._list(); Array.from(arguments).forEach(c => { if (l.indexOf(c) < 0) l.push(c); }); this._set(l); }
  remove() { const drop = Array.from(arguments); this._set(this._list().filter(c => drop.indexOf(c) < 0)); }
  toggle(c, force) {
    const has = this.contains(c);
    const want = force === undefined ? !has : !!force;
    if (want) this.add(c); else this.remove(c);
    return want;
  }
  get length() { return this._list().length; }
  item(i) { return this._list()[i] || null; }
}

export class El {
  constructor(tag, doc) {
    this.nodeType = 1;
    this.tagName = String(tag).toLowerCase();
    this.ownerDocument = doc;
    this.attributes = new Map();
    this.childNodes = [];
    this.parentNode = null;
    this._listeners = new Map();
    this._value = '';
    this._uid = ++UID;
    this.style = this._makeStyle();
  }

  _makeStyle() {
    const el = this;
    return new Proxy({}, {
      get(t, prop) {
        if (typeof prop !== 'string') return undefined;
        return parseStyleAttr(el.getAttribute('style'))[kebab(prop)] || '';
      },
      set(t, prop, value) {
        const css = parseStyleAttr(el.getAttribute('style'));
        css[kebab(prop)] = String(value);
        el.setAttribute('style', Object.keys(css).map(k => k + ': ' + css[k]).join('; '));
        return true;
      }
    });
  }

  /* ---- 属性 ---- */
  getAttribute(name) { const v = this.attributes.get(String(name).toLowerCase()); return v === undefined ? null : v; }
  setAttribute(name, value) { this.attributes.set(String(name).toLowerCase(), String(value)); }
  hasAttribute(name) { return this.attributes.has(String(name).toLowerCase()); }
  removeAttribute(name) { this.attributes.delete(String(name).toLowerCase()); }

  get id() { return this.getAttribute('id') || ''; }
  set id(v) { this.setAttribute('id', v); }
  get className() { return this.getAttribute('class') || ''; }
  set className(v) { this.setAttribute('class', v); }
  get classList() { if (!this._classList) this._classList = new ClassList(this); return this._classList; }
  get title() { return this.getAttribute('title') || ''; }
  set title(v) { this.setAttribute('title', v); }
  get hidden() { return this.hasAttribute('hidden'); }
  set hidden(v) { if (v) this.setAttribute('hidden', ''); else this.removeAttribute('hidden'); }
  get disabled() { return this.hasAttribute('disabled'); }
  set disabled(v) { if (v) this.setAttribute('disabled', ''); else this.removeAttribute('disabled'); }
  get value() { return this._value; }
  set value(v) { this._value = v === null || v === undefined ? '' : String(v); }
  get checked() { return this.hasAttribute('checked'); }
  set checked(v) { if (v) this.setAttribute('checked', ''); else this.removeAttribute('checked'); }

  get dataset() {
    if (!this._dataset) {
      const el = this;
      this._dataset = new Proxy({}, {
        get(t, prop) {
          if (typeof prop !== 'string') return undefined;
          const v = el.getAttribute('data-' + kebab(prop));
          return v === null ? undefined : v;
        },
        set(t, prop, v) { el.setAttribute('data-' + kebab(prop), String(v)); return true; },
        has(t, prop) { return el.hasAttribute('data-' + kebab(prop)); }
      });
    }
    return this._dataset;
  }

  /* ---- 树 ---- */
  get children() { return this.childNodes.filter(n => n.nodeType === 1); }
  get firstChild() { return this.childNodes[0] || null; }
  get parentElement() { return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null; }
  appendChild(node) {
    if (node.parentNode) node.parentNode.removeChild(node);
    node.parentNode = this;
    this.childNodes.push(node);
    return node;
  }
  removeChild(node) {
    const i = this.childNodes.indexOf(node);
    if (i >= 0) { this.childNodes.splice(i, 1); node.parentNode = null; }
    return node;
  }
  get textContent() {
    let out = '';
    const walk = n => {
      if (n.nodeType === 3) { out += n.text; return; }
      n.childNodes.forEach(walk);
    };
    this.childNodes.forEach(walk);
    return out;
  }
  set textContent(v) {
    this.childNodes = [];
    const text = v === null || v === undefined ? '' : String(v);
    if (text !== '') this.appendChild({ nodeType: 3, text, parentNode: null });
  }
  get innerHTML() {
    const ser = n => {
      if (n.nodeType === 3) return n.text;
      const attrs = Array.from(n.attributes.entries()).map(([k, v]) => ` ${k}="${v}"`).join('');
      return '<' + n.tagName + attrs + '>' + n.childNodes.map(ser).join('') + '</' + n.tagName + '>';
    };
    return this.childNodes.map(ser).join('');
  }
  set innerHTML(html) {
    this.childNodes = [];
    parseInto(this, String(html === null || html === undefined ? '' : html), this.ownerDocument);
  }

  /* ---- 查询 ---- */
  querySelectorAll(selector) {
    const out = [];
    const walk = n => {
      n.childNodes.forEach(c => {
        if (c.nodeType === 1) {
          if (matchesSelector(c, selector)) out.push(c);
          walk(c);
        }
      });
    };
    walk(this);
    return out;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  matches(selector) { return matchesSelector(this, selector); }
  closest(selector) {
    let node = this;
    while (node) {
      if (node.nodeType === 1 && matchesSelector(node, selector)) return node;
      node = node.parentNode;
    }
    return null;
  }

  /* ---- 事件 ---- */
  addEventListener(type, fn) {
    if (!this._listeners.has(type)) this._listeners.set(type, []);
    this._listeners.get(type).push(fn);
  }
  removeEventListener(type, fn) {
    const list = this._listeners.get(type);
    if (list) this._listeners.set(type, list.filter(f => f !== fn));
  }
  dispatch(type, props) {
    const ev = Object.assign({
      type, target: this, currentTarget: this,
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      stopPropagation() { this._stopped = true; }
    }, props || {});
    let node = this;
    const hooks = (this.ownerDocument && this.ownerDocument.__hooks) || { errors: [] };
    while (node) {
      const list = node._listeners && node._listeners.get(type);
      if (list) {
        ev.currentTarget = node;
        for (const fn of list.slice()) {
          try { fn.call(node, ev); } catch (e) { hooks.errors.push(type + '@' + (node.tagName || '?') + ': ' + (e && e.stack ? e.stack : e)); }
        }
      }
      if (ev._stopped) break;
      node = node.parentNode;
    }
    return ev;
  }
  click() {
    if (this.disabled && (this.tagName === 'button' || this.tagName === 'input' || this.tagName === 'select')) return;
    this.dispatch('click');
  }
  focus() { }
  blur() { }
  select() { }
  setSelectionRange() { }
  scrollIntoView() { }

  /* 测试辅助 */
  get tagLabel() { return this.tagName; }
  toString() { return '<' + this.tagName + (this.id ? ' id=' + this.id : '') + '>'; }
}

/* ------------------------------ HTML 解析 -------------------------------- */
function parseInto(root, html, doc) {
  const tagRe = /<(\/?)([a-zA-Z][A-Za-z0-9:-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>/g;
  const stack = [root];
  let last = 0, m;
  const pushText = text => {
    if (!text) return;
    const decoded = decodeEntities(text);
    if (decoded.trim() === '' && !/\u00a0/.test(decoded)) return;   // 忽略纯排版空白
    stack[stack.length - 1].appendChild({ nodeType: 3, text: decoded, parentNode: null });
  };
  while ((m = tagRe.exec(html))) {
    pushText(html.slice(last, m.index));
    last = tagRe.lastIndex;
    const isClose = m[1] === '/';
    const name = m[2].toLowerCase();
    const selfClose = m[4] === '/';
    if (isClose) {
      for (let i = stack.length - 1; i > 0; i--) {
        if (stack[i].tagName === name) { stack.length = i; break; }
      }
      continue;
    }
    const node = new El(name, doc);
    parseAttrString(m[3] || '', node);
    stack[stack.length - 1].appendChild(node);
    if (!selfClose && !VOID_TAGS.has(name)) stack.push(node);
  }
  pushText(html.slice(last));
}

/* ------------------------------ document --------------------------------- */
class Document extends El {
  constructor() {
    super('#document', null);
    this.ownerDocument = this;
    this.readyState = 'loading';
    this.title = '';
    this.__hooks = { errors: [], created: [], objectUrls: [], copied: [] };
    this.body = new El('body', this);
    this.documentElement = new El('html', this);
    this.appendChild(this.documentElement);
    this.documentElement.appendChild(this.body);
    this.__hooks.errors = [];
  }
  createElement(tag) {
    const el = new El(tag, this);
    this.__hooks.created.push(el);
    return el;
  }
  createDocumentFragment() {
    const frag = new El('#fragment', this);
    frag.nodeType = 11;
    return frag;
  }
  getElementById(id) {
    const found = this.querySelectorAll('#' + id);
    return found[0] || null;
  }
  execCommand(cmd) {
    if (cmd === 'copy') {
      const areas = this.__hooks.created.filter(e => e.tagName === 'textarea');
      const last = areas[areas.length - 1];
      this.__hooks.copied.push(last ? last.value : '');
      return true;
    }
    return false;
  }
  get activeElement() { return this.body; }
}

/* ------------------------------- 安装 ------------------------------------ */
export function installDom(html, options) {
  const opts = options || {};
  const doc = new Document();
  const htmlMatch = /<html[^>]*>([\s\S]*)<\/html>/i.exec(html);
  const headMatch = /<head[^>]*>([\s\S]*?)<\/head>/i.exec(html);
  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  const titleMatch = /<title>([\s\S]*?)<\/title>/i.exec(html || '');
  if (titleMatch) doc.title = decodeEntities(titleMatch[1]).trim();
  // head 里的元素（除 link/script）与 body 内容分别解析
  const headHtml = headMatch ? headMatch[1] : '';
  parseInto(doc.documentElement, headHtml.replace(/<title>[\s\S]*?<\/title>/i, ''), doc);
  if (bodyMatch) parseInto(doc.body, bodyMatch[1], doc);
  else if (htmlMatch) parseInto(doc.body, htmlMatch[1], doc);
  else parseInto(doc.body, html || '', doc);

  // select 默认值：选中 selected 的 option，否则第一个 option
  doc.querySelectorAll('select').forEach(sel => {
    const opts = sel.querySelectorAll('option');
    const picked = opts.find(o => o.hasAttribute('selected')) || opts[0];
    sel.value = picked ? (picked.getAttribute('value') || picked.textContent) : '';
  });
  // input[value] / textarea 的初始值
  doc.querySelectorAll('input[type="text"],input:not([type])').forEach(i => { i.value = i.getAttribute('value') || ''; });

  const win = {
    __listeners: new Map(),
    addEventListener(type, fn) {
      if (!this.__listeners.has(type)) this.__listeners.set(type, []);
      this.__listeners.get(type).push(fn);
    },
    removeEventListener() { },
    dispatch(type, props) {
      const ev = Object.assign({ type, util: {}, preventDefault() { } }, props || {});
      (this.__listeners.get(type) || []).slice().forEach(fn => {
        try { fn(ev); } catch (e) { doc.__hooks.errors.push('window.' + type + ': ' + (e && e.stack ? e.stack : e)); }
      });
      return ev;
    },
    location: null,
    document: doc
  };

  const origin = (opts.origin || 'http://127.0.0.1:8899').replace(/\/+$/, '');
  const parsedOrigin = new URL(origin);
  const locationStub = {
    protocol: parsedOrigin.protocol,
    host: parsedOrigin.host,
    hostname: parsedOrigin.hostname,
    port: parsedOrigin.port,
    origin: parsedOrigin.origin,
    href: origin + '/',
    search: '?api=' + encodeURIComponent(origin),
    pathname: '/'
  };
  win.location = locationStub;

  const globalRef = globalThis;
  const previous = {
    document: globalRef.document,
    window: globalRef.window,
    location: globalRef.location,
    localStorage: globalRef.localStorage,
    createObjectURL: globalRef.URL.createObjectURL,
    revokeObjectURL: globalRef.URL.revokeObjectURL,
    execCommand: undefined
  };
  globalRef.document = doc;
  globalRef.window = win;
  globalRef.location = locationStub;

  /* localStorage 垫片：产品页面用它记住界面语言（pr_lang）。
     页面创建前先写入 pr_lang，即可让被测页面以确定语言启动，
     不受宿主系统语言影响。 */
  const storageMap = new Map();
  const storage = opts.storage || {
    get length() { return storageMap.size; },
    key(i) { return Array.from(storageMap.keys())[i] ?? null; },
    getItem(k) { k = String(k); return storageMap.has(k) ? storageMap.get(k) : null; },
    setItem(k, v) { storageMap.set(String(k), String(v)); },
    removeItem(k) { storageMap.delete(String(k)); },
    clear() { storageMap.clear(); }
  };
  try { globalRef.localStorage = storage; } catch { /* ignore */ }

  try { globalRef.URL.createObjectURL = blob => { doc.__hooks.objectUrls.push(blob); return 'blob:mock/' + doc.__hooks.objectUrls.length; }; } catch { /* ignore */ }
  try { globalRef.URL.revokeObjectURL = () => { }; } catch { /* ignore */ }

  return {
    document: doc,
    window: win,
    storage: storage,
    hooks: doc.__hooks,
    restore() {
      globalRef.document = previous.document;
      globalRef.window = previous.window;
      globalRef.location = previous.location;
      try { globalRef.localStorage = previous.localStorage; } catch { /* ignore */ }
      try { globalRef.URL.createObjectURL = previous.createObjectURL; } catch { /* ignore */ }
      try { globalRef.URL.revokeObjectURL = previous.revokeObjectURL; } catch { /* ignore */ }
    }
  };
}

export function fireDomContentLoaded(doc) {
  doc.readyState = 'complete';
  doc.dispatch('DOMContentLoaded');
}
