# app/static/_mock/ —— 前端自测脚手架（不属于产品代码）

这里的文件**只用于开发自测**，产品页面只需要 `../index.html`、`../app.js`、`../i18n.js`、
`../style.css` 四个文件；部署时可以把整个 `_mock/` 目录删掉。

## 1. 被测对象

| 文件 | 说明 |
| --- | --- |
| `../index.html` | 页面结构（内联 SVG 图标库、无任何外链资源） |
| `../style.css` | 深色主题样式（无 @import、无外部字体、无 CDN） |
| `../i18n.js` | 界面多语言（中/英）字典与切换逻辑，须在 `app.js` 之前加载 |
| `../app.js` | 全部交互逻辑；三接口调用、解析、渲染、错误处理 |

> 产品页面里 `i18n.js` 与 `app.js` 共享全局作用域（`PR_I18N`），
> 因此两个测试脚本都用 `i18n.js + '\n' + app.js` 拼接后放进同一个 `new Function` 里执行。

## 2. mock 服务（按冻结契约实现，用于故障注入）

```
D:\01APP\51python3.14.3\python.exe app\static\_mock\mock_server.py --port 8901
```

- 端口用 8901/8899 之类，**不要占用 8737**，避免与真实服务冲突。
- 同时提供静态目录（`app/static`）与三个接口：`GET /api/status`、`POST /api/score`、`POST /api/export`。
- 浏览器打开：`http://127.0.0.1:8901/?api=http://127.0.0.1:8901`
  （`?api=` 只是把前端指向 mock；真实部署在 8737 时同源访问，无需该参数。）
- 故障模式（前端错误处理专项）：
  ```
  curl -X POST http://127.0.0.1:8901/__mock/mode -d "{\"mode\":\"notready\"}"
  # mode ∈ ok | notready | down | err500
  ```
- `/__mock/log` 返回收到的请求记录，用于断言请求体字段名与契约完全一致。

## 3. 测试脚本

```
# 纯函数单元测试（解析 / 统计 / 直方图 / CSV / 服务地址解析）
node app\static\_mock\unit_test.mjs

# 端到端 vs mock（含 ready=false / 503 / 500 三条故障路径）
set MOCK_BASE=http://127.0.0.1:8901
node app\static\_mock\dom_test.mjs

# 端到端 vs 真实后端 app/server.py（跳过 mock 专属故障模式，并直连核对响应字段名）
set REAL_BACKEND=1
set MOCK_BASE=http://127.0.0.1:8899
node app\static\_mock\dom_test.mjs

# 真实浏览器版本（CDP + 截图 + 真实下载校验），需要能启动 Chrome/Edge
node app\static\_mock\smoke.mjs
```

- `dom_shim.mjs`：极简 DOM 实现（HTML 子集解析、querySelector、classList、dataset、
  style、事件冒泡与委托、innerHTML/textContent、Blob 下载钩子、execCommand 复制钩子、
  **localStorage 垫片**），用来在 Node 中加载**真实**的 index.html + i18n.js + app.js，
  不做排版/CSS 计算。被测服务地址通过 `installDom(html, {origin})` 注入，不要硬编码端口。
  注意选择器引擎**不支持逗号分隔的选择器列表**，也不做 CSS 计算。
- `newPage(lang)`：创建页面并预置 `localStorage.pr_lang`。默认 `'zh'`，
  这样界面语言不随宿主系统语言变化；要测英文界面就传 `'en'`。
- `browser_test.js` + `smoke.mjs`：真实浏览器版本（CDP 驱动 Chrome/Edge，含截图与真实下载校验）。
  **注意**：在 DSH 受限沙箱会话中 Chrome / Edge / WebView2 都启动不了
  （crashpad `OpenProcess` 被拒绝后自杀），只有在**完全权限 / 普通桌面会话**下才能运行；
  运行时会在 `_artifacts/` 下产出截图与 `report.json`（该目录已加入 `.gitignore`）。

## 4. 最近一次执行结果

| 套件 | 结果 |
| --- | --- |
| `unit_test.mjs` | **138 / 138 通过**（含 39 项多语言断言） |
| `dom_test.mjs`（mock，含故障注入） | **214 / 214 通过**（含 35 项中英切换端到端断言） |
| `dom_test.mjs`（REAL_BACKEND=1，真实 `app/server.py`） | **180 / 180 通过** |
| `smoke.mjs`（真实 Chrome，含截图） | **145 / 145 通过**，未捕获异常 0、console.error 0 |

多语言覆盖到的点：中英字典键集合一致且无空文案、语言标签归一化（`zh-CN`/`zh-Hant`/`en-US`/`ja`）、
`localStorage` 记忆值优先于浏览器语言、`?lang=` 覆盖（仅本次、不落盘、未知值被忽略）、
切换后**静态文案 + 动态文案（统计、警告、Toast、错误条、表头、概览标签、结果元信息、空态、
placeholder、aria-label、`<html lang>`、`document.title`）全部即时更新**、来回切换正确、
切换有 toast 反馈、选择写入 `localStorage`、英文下非法行警告与格式标签也是英文、无未捕获异常。

`smoke.mjs` 的真实浏览器一轮还会产出截图：`01-main.png`（中文宽屏）、`02-results.png`、
`03-bottom.png`、`04-narrow.png`（窄屏响应式）、`05-error.png`（错误条）、
**`06-english.png`（英文界面）**。

mock 故障注入覆盖：`ready=false`(200)、`ready=false`(503，真实后端形态)、服务不可达(503)、
打分接口 500、不支持的文件类型——每种都断言错误条文本、按钮禁用与"页面不白屏"。

真实后端一轮覆盖到的关键点：页面在真实引擎数据下完整渲染（15 条结果、概览、10 桶直方图、
阈值高亮）、三档 `length_handling` 与结果 `model` 一致、`/api/export` 真实返回
`text/csv; charset=utf-8` + BOM + `rank,id,sequence,length,score,model` 表头、
`results/summary/histogram/elapsed_ms` 字段名与契约一致、`lang` 字段随请求下发、无未捕获异常。

> 服务端多语言（`pr_engine/i18n.py`）由 `scripts/selftest.py` 与
> `scripts/verify_frontend_integration.py` 覆盖；`lang` 取值 `zh` / `en`，
> 缺省中文，请求体里的 `lang` 优先于 `Accept-Language` 头。
