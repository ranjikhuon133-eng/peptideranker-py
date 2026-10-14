# PeptideRanker 本地打分重做版（纯 Python 引擎）

> 原版 PeptideRanker 是 2010 年的 Linux x86-64 二进制加一个 Perl 包装脚本；本仓库把它和 30 个神经网络权重**原封不动**保留为数值校验基准，另用纯 Python（NumPy）从零复刻同一套网络，并提供零构建依赖的本地网页界面与命令行工具。

[English](README.md) | **中文**

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white) ![引擎依赖](https://img.shields.io/badge/引擎依赖-仅%20NumPy-013243?logo=numpy&logoColor=white) ![Web 服务依赖](https://img.shields.io/badge/Web%20服务依赖-仅标准库-2ea44f) ![监听](https://img.shields.io/badge/监听-127.0.0.1%20only-6e40c9) ![许可证](https://img.shields.io/badge/重做代码-MIT-3da639) ![平台](https://img.shields.io/badge/平台-Windows%20%7C%20Linux%20%7C%20macOS-0078D6)

**双语文档**：[README.md](README.md)（English）· [README.zh-CN.md](README.zh-CN.md)（中文）· [USAGE.md](USAGE.md)（英文使用说明）· [使用说明.md](使用说明.md)（中文使用指南）

---

## 目录

- [这是什么](#这是什么)
- [为什么要重做](#为什么要重做)
- [快速开始](#快速开始)
- [中英双语界面](#中英双语界面)
- [打分语义](#打分语义)
- [与原程序的三处有意差异](#与原程序的三处有意差异)
- [目录结构](#目录结构)
- [支持的输入格式](#支持的输入格式)
- [数值正确性怎么保证](#数值正确性怎么保证)
- [如实说明的局限](#如实说明的局限)
- [环境要求](#环境要求)
- [署名、第三方声明与许可证](#署名第三方声明与许可证)
- [引用](#引用)

---

## 这是什么

这个仓库做三件事：

1. **保留基准**：原作者发布的 2010 年 Linux x86-64 ELF 二进制 `PeptideRanker`、Perl 包装脚本 `PeptideRanker.pl`、以及 `Models_Short/` `Models_Long/` 下 30 个 `.model` 权重文件，**一个字节都没有改动**，仍然可以在 Linux 下按原方式运行。它们是本仓库所有数值结论的对照物。
2. **从零复刻引擎**：用纯 Python + NumPy 重写同一套前向计算，语义逐条对齐反汇编证据（`pr_engine/reference/FORMAT.md`，含反汇编行号），不重新训练、不改权重、不做近似。
3. **补上可用性**：零构建依赖的本地网页界面（原生 JS，无 CDN、无打包器）、命令行批量打分工具、以及一个只监听 `127.0.0.1` 的零第三方依赖 HTTP 服务。

适用场景：手上只有 Windows 机器、不想装 Perl / Linux / Docker，但需要批量、可编程地拿到 PeptideRanker 分数，并且希望这些分数**可对照原程序复核**。

---

## 为什么要重做

原程序在 2010 年是合理交付物；放到现在的 Windows 环境里，几乎每一步都会硌手。下面每一条都对应本仓库的一项具体改动。

| 原来的问题 | 现在怎么解决 |
| --- | --- |
| `PeptideRanker` 是 Linux x86-64 ELF，**在 Windows 上根本跑不起来**（本机也无 WSL/Docker） | 用 NumPy 复刻同一套网络，纯 Python 运行 |
| `PeptideRanker.pl` 里 `$pipeline_dir="."` 写死相对路径，换个目录就崩 | 路径全部由脚本自己解析，任意目录可用 |
| 每条序列都要**写一遍** `peptide.dataset`，再 `rm` 掉 | 内存中直接推理，不落临时文件（并发/批量子进程都安全） |
| 分数要从 `.predictions` 里 `shift` 5 行再 `split` 空格取出，**纯靠文本解析** | 直接返回 `0~1` 的浮点分数与结构化 JSON |
| 一次只能跑一个文件，结果是 `<分数>\t<序列>` 两列 | 一次任意多条，输出含排名/长度/模型来源/统计/直方图 |
| 还要自己装 Perl + 手改脚本路径 | 双击 `启动网页.bat` 即可（Windows） |

---

## 快速开始

三种入口共用同一套解析器与同一个引擎，分数完全一致。

### 网页界面（推荐）

Windows：双击项目根目录的 **`启动网页.bat`**，浏览器自动打开 <http://127.0.0.1:8737/>。

任何平台的手动启动方式：

```bash
python app/server.py --open          # 默认 127.0.0.1:8737，端口被占会自动顺延
python app/server.py --port 9000     # 指定端口
python app/server.py --idle-exit-minutes 15   # 关掉网页 15 分钟后自动退出（0 = 不自动退出）
```

界面能力：多行粘贴、拖拽/选择文件（`.txt/.fasta/.fa/.csv`）、一键载入示例、
按分数排序与筛选（全部 / ≥0.5 / <0.5）、分数分布直方图、
复制结果（TSV）、导出 CSV（带 UTF-8 BOM，Excel 可直接打开）。

**关于退出**（关掉浏览器并**不会**关掉服务，服务是启动脚本那个命令行窗口里的进程）。三条等效路径，都会释放端口：

| 方式 | 说明 |
| --- | --- |
| 网页右上角「退出程序」 | 调 `POST /api/shutdown`，服务端优雅停止 |
| 关闭启动脚本的窗口 / Ctrl+C | 标准方式 |
| 关掉所有网页后自动退出 | 网页每 20 秒向 `/api/heartbeat` 发心跳；心跳停止超过 `--idle-exit-minutes`（默认 10）分钟即自动退出 |

Windows 下另有兜底脚本 **`停止程序.bat`**（先请求 HTTP 优雅退出，失败再 `taskkill`），
用于窗口被误关或服务卡住的场景。这两个 `.bat` 是 **Windows 专用双击启动器**；
Linux/macOS 下等价命令就是 `python app/server.py --open`。

### 命令行

```bash
python pr_cli.py testfile.txt                  # 打分示例文件
python pr_cli.py testfile.txt -o scores.csv    # 导出 CSV
python pr_cli.py --sequence ILPILSLIGGLL RPPGFSPFR
type testfile.txt | python pr_cli.py -         # Windows；Linux/macOS 用 cat testfile.txt | python pr_cli.py -
```

常用参数：`--length-handling {auto,short,long}`、`--threshold/-t`、`--quiet/-q`、`--strict-case`。

### Python 调用

```python
from pr_engine import scoring

report = scoring.score_sequences([
    {"id": "P1", "sequence": "ILPILSLIGGLL"},
    {"id": "P2", "sequence": "EEERDEDEVIEEEVKRGLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC"},
])
for r in report.results:
    print(r.rank, r.sequence, f"{r.score:.4f}", r.model)
```

### HTTP 接口

服务只监听 `127.0.0.1`，不需要联网。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/status` | 引擎是否就绪、模型计数、`threshold`、`idle_exit_minutes`；恒返回 200，未就绪时以 `ready=false` + `error` 表达 |
| `GET` | `/api/heartbeat` | 网页心跳，用于空闲自动退出判定 |
| `POST` | `/api/score` | 请求体接受 `text`（原始文本，服务端解析）或 `sequences`（数组，元素为字符串或 `{id, sequence}`）；可选 `length_handling`（`auto`/`short`/`long`）、`strict_case`；返回结构化 JSON |
| `POST` | `/api/export` | 同上，另加 `format=csv`；返回带 `Content-Disposition` 的 CSV |
| `POST` | `/api/shutdown` | 优雅停止服务 |

---

## 中英双语界面

网页顶栏有一个 `中文 / EN` 分段切换控件：

- **首次访问**跟随浏览器语言（`navigator.language`，`zh*` → 中文，其余 → 英文）；
- 用户的选择存入 `localStorage`，后续访问自动恢复；
- 切换语言会**实时重渲染所有文案**，包括动态内容——警告（前端本地生成的，以及引擎逐条返回的）、
  Toast 提示、错误条、表头、统计标签、空态、输入框 placeholder 与 `aria-label`、`document.title`
  ——并同步更新 `<html lang>` 属性，无需刷新页面。
- URL 上带 `?lang=zh` / `?lang=en` 可强制本次访问的语言（不写入 `localStorage`），
  方便分享链接或在浏览器自动化里固定语言。
- **引擎也是双语的**：前端在 `/api/score`、`/api/export` 请求体里带上 `lang`（`zh` / `en`，缺省 `zh`），
  `GET /api/status` 则跟随 `Accept-Language` 请求头，因此提示信息不会中英混杂。
  文案表见 [`pr_engine/i18n.py`](pr_engine/i18n.py)。

翻译范围**有意止步于机器可读的数据契约**：导出的 CSV 无论界面语言如何，都固定使用
`rank,id,sequence,length,score,model` 列头与固定文件名 `peptideranker_scores.csv`。
数据文件的表结构不应该随界面语言变化，否则所有下游脚本都会失效——只有面向人的界面文字才翻译。

---

## 打分语义

以下语义来自对原 ELF 二进制 `MModel::predict` / `NNto1::Feed` / `Layer::*` 的逆向，逐条证据（含反汇编行号）见 [`pr_engine/reference/FORMAT.md`](pr_engine/reference/FORMAT.md)。

| 项目 | 规定 |
| --- | --- |
| 字母表 | `ACDEFGHIKLMNPQRSTVWYX`，共 **21 个**；第 21 个是 `X`（未知残基），有独立权重。`B/J/O/U/Z` **不在表内** |
| 模型选择 | 序列长度 `<= 20` 用 `Models_Short`，`> 20` 用 `Models_Long`——与 `PeptideRanker.pl` 第 30–35 行完全一致 |
| 集成方式 | 该组的 **15 个模型**分别前向，输出**逐元素取算术平均**，再取 `argmax` |
| 分数取值 | 分数 = 平均向量的**第 2 个分量**（索引 1，阴性/阳性两类中的阳性类概率） |
| 输出范围 | `0 ~ 1`；预测路径把每个子模型的输出做 softmax 归一化，因此 15 个模型的平均向量各分量和为 1 |

分数取索引 1 的证据链：`MModel::predict` 把平均向量写到 `Sequence+264`，`main` 逐个
`operator<<(double)` 输出到 `.predictions`，Perl 脚本 `shift` 5 行后 `split(/ /)` 取的就是 `$foo[1]`。
同一向量里被写进 `Sequence+272` 的 `argmax` 是**类别下标**，不是分数，两者不要混淆。

### `0.5` 阈值的性质澄清

**`0.5` 不是二进制里的分支。** 原程序的预测路径只做 `argmax`，代码中**不存在任何 `0.5` 比较**。
`0.5` 是原论文与服务器展示层面的约定（公开文献里普遍写作「score above 0.5 → potentially bioactive」），
本应用把它作为界面上的「可能具有生物活性」标记线，可通过 `GET /api/status` 的 `threshold` 字段读到，
命令行侧由 `--threshold` 覆盖。它是一条**展示约定，不是算法的一部分**，不要据此推断引擎内部存在分类分支。

补充：`Layer_soft` 的 `85.0` 溢出兜底分支对随包权重**不可达**——30 个模型所有 softmax 输出单元的
`max(|bias| + Σ|W|) = 13.509229 < 85`，因此分数总是真正的 softmax 值，不会退化成 `1e-4 / 0.9999`。

---

## 与原程序的三处有意差异

原程序对「非标准输入」的行为其实是一个潜在 bug：字符查表**不做范围检查**，非法残基会让该位点整列留空，
逐位点归一化时算出 `0/0`，**整条序列的分数变成 NaN**（不是某个无意义的有限数）。
`pr_engine/reference/oracle.py` 逐字复刻了这个行为；而产品层（`pr_engine/scoring.py`、前端、`pr_cli.py`）
出于可用性做了三处**有意差异**，并且**每条都给出警告，绝不静默**：

| 差异 | 原程序行为 | 本应用默认行为 | 如何恢复原行为 |
| --- | --- | --- | --- |
| 小写输入 | 小写查表越界 → `0/0` → **NaN**（即无结果） | 视同对应大写氨基酸，`rppgfspfr` → 0.9558 | CLI `--strict-case`；HTTP `"strict_case": true` |
| `B/J/O/U/Z` 歧义残基 | 同样 `0/0` → **NaN** | 映射到 `X` 通道（真实存在的歧义残基通道，比整条拒分更有用） | 同上 |
| 数字/标点（如 `ILP1LS`） | 同样 `0/0` → **NaN** | 明确报错并跳过该行，**绝不静默改动序列** | 无（有意加严） |

**「绝不静默改序列」的承诺**：含非法字符的行一律如实报错并跳过，不会删掉字符后照常打分；
所有修正都会以警告形式出现在 CLI 的 stderr、网页的提示区、以及 HTTP 响应的 `warnings` 字段里。

关于 `X` 与 `B/Z` 的性质差别：`X` 是字母表里的第 21 个**真实通道**（有独立权重），
`XXXXXXXXXXXXXXXXXXXX` 得 0.9767；而 `B/Z/J/O/U` 在原程序里不在表内。这就是把后者映射到前者、
而不是直接丢弃的原因。

---

## 目录结构

```
PeptideRanker            # 原始 Linux x86-64 ELF 二进制（只读保留，作为校验基准）
PeptideRanker.pl         # 原始 Perl 包装脚本（只读保留）
README                   # 原作者的原始安装说明（只读保留）
Models_Short/            # 原始的 15 个短肽模型权重（只读保留）
Models_Long/             # 原始的 15 个长肽模型权重（只读保留）
Models_Short.txt         # 短肽模型清单（只读保留）
Models_Long.txt          # 长肽模型清单（只读保留）
testfile.txt             # 原始示例输入（15 条肽，只读保留）

app/
  server.py              # 零第三方依赖 HTTP 服务（只监听 127.0.0.1）
  static/                # 前端页面（原生 JS，无构建、无 CDN）
    index.html           # 页面结构
    app.js               # 交互、中英双语切换、结果表格与直方图
    style.css            # 样式

pr_engine/
  __init__.py
  scoring.py             # 对外唯一打分 API：校验、批量、排序、统计、导出
  reference/
    oracle.py            # 逆向所得的数值引擎（逐位复刻原程序，含越界查表等实测行为）
    FORMAT.md            # 模型文件格式 + 前向公式 + 反汇编证据（逐条行号）

pr_cli.py                # 命令行批量打分
启动网页.bat              # Windows 双击一键启动（自动找 Python、缺失依赖自动装，GBK + CRLF 编码）
停止程序.bat              # Windows 兜底停止脚本（先 HTTP 优雅退出，失败再 taskkill）

scripts/
  selftest.py                    # 服务层自检：HTTP / 解析 / 统计 / 导出 / 边界
  compare_with_oracle.py         # 产品引擎 vs 逆向参考实现，逐位比对（113 条用例）
  validate_published.py          # 公开文献真值逐条比对 + 20aa 边界判定
  validate_against_original.py   # 同上语义的简化入口（读同一份 tsv）
  check_distribution.py          # 分布合理性：随机肽 vs 活性肽
  verify_frontend_integration.py # 前端 + 真实后端联调（44 项）
  final_acceptance.py            # 最终验收（41 项），报告存档到 _re/acceptance_report.txt
  check_delivery.py              # 交付环境自检（启动器缺 Python / 未解压全等场景）
  check_shutdown.py              # 退出路径自检
  run_original.sh                # 在 Linux/Docker 里跑原始二进制，生成标准答案
  Dockerfile.original            # 上述脚本所需的镜像

_re/                     # 逆向工程工作区（分析脚本、反汇编文本、参考分数、验收报告）
README.md                # 英文技术说明（本文件的英文对应版）
README.zh-CN.md          # 本文件
USAGE.md                 # 英文使用说明
使用说明.md               # 中文使用指南（面向最终用户）
LICENSE                  # 重做代码的 MIT 许可证
```

`_re/`（逆向分析工作文件与验证数据）、`scripts/`（自检脚本）、`app/static/_mock/` 都可以删除，不影响使用。

**想给最精简的版本**：保留这 7 项即可（约 2 MB），其余全部可删。

```
启动网页.bat   app/   pr_engine/   Models_Short/   Models_Long/
Models_Short.txt   Models_Long.txt
```

---

## 支持的输入格式

三种入口（网页粘贴 / 文件上传 / CLI）共用同一套解析器，实测支持：

| 输入形态 | 示例 | 结果 |
| --- | --- | --- |
| 纯序列逐行 | `ILPILSLIGGLL` | 每条独立 |
| FASTA（含多行序列） | `>pep1 描述` ⏎ `RPPGFSPFR` | 取 FASTA 头作 ID，同一条可跨行 |
| 带行号/序号 | `1  ILPILSLIGGLL` | 前缀只在「剩余部分仍是合法序列」时去掉 |
| 带标签前缀 | `seq3: RPPGFSPFR` | 识别为 ID 前缀 |
| CSV/TSV 带表头 | `id,sequence,note` ⏎ `p1,RPPGFSPFR,x` | 按表头定位 `sequence` 列，首列作 ID |
| CSV/TSV 无表头 | `p1,RPPGFSPFR` | 自动挑出像序列的那一列 |
| 表头列序任意 | `note,peptide,score` | 按列名定位 |

含非法字符（如 `ILP1LS`）的行**一律如实报错并跳过，绝不静默删字符后照常打分**。

---

## 数值正确性怎么保证

这是本项目最关键、也最容易被糊弄的一环，所以单列一节。每一项结论都给出可原样重跑的复现脚本。

| 检验 | 结果 | 复现脚本 |
| --- | --- | --- |
| 30 个 `.model` 解析 | **30/30 成功，全部消费到 EOF、零剩余字节** | `python _re/probe_parse.py`；`python _re/verify_oracle.py` |
| 产品引擎 vs 逆向参考实现 | **113 条用例逐位一致（差 < 1e-12）**（含全部同聚物、长度边界 19/20/21/22、未知残基、随机序列） | `python scripts/compare_with_oracle.py` |
| **vs 原版公开服务器输出（729 条）** | **673 条在 ±0.01 内（92.3%），其中 628 条逐位相同（86.1%），中位偏差 0.000000** | `python scripts/final_acceptance.py`（H 节）；`python scripts/validate_published.py` |
| **vs 原作者论文 Figure S3（15 条）** | **13/15 在 ±0.01 内，15/15 在 ±0.02 内（最大偏差 0.018）** | `python scripts/validate_published.py`（`_re/reference_scores.tsv` 的 SECTION 1 即 Figure S3） |
| **20aa 模型切换边界探针（11 条）** | **11 条全部与 Short 模型逐位吻合（Δ=0.0000），且全部不吻合 Long 模型 ⇒ 确认 `<=20 → Short`** | `python scripts/validate_published.py`（20aa 边界判定段） |
| 分布合理性 | 随机 8/12/15/20/25/35/50 肽各 200 条：平均 0.35~0.49，≥0.5 占比 31%~46%；缓激肽 `RPPGFSPFR` 0.9558 | `python scripts/check_distribution.py` |
| 服务层自检 | 全部通过 | `python scripts/selftest.py` |
| 前端联调 | **44 项全部通过** | `python scripts/verify_frontend_integration.py` |
| 最终验收 | **41 项全通过**（报告存档 `_re/acceptance_report.txt`） | `python scripts/final_acceptance.py` |

配套方法与数据来源：

1. **逆向取证**：`_re/disasm.py` 是针对该 ELF 手写的 x86-64 反汇编器（本机没有 objdump/capstone），
   用于逐条确认 `Layer::forward`、`Layer::read`、`NNto1::Feed`、`MModel::predict` 的真实语义。
   2026-10-12 修复了 4 处解码错误，修复后 `.text` 里 133 个符号全部解码成功（`<bytes>`/`err`/`db 0x` 均为 0）。
2. **真值来源**：`_re/reference_scores.tsv`（679 条，均为**原版 `distilldeep.ucd.ie/PeptideRanker` 服务器**的输出，
   从 Europe PMC 全文 XML 里逐条提取，每条带可复核 URL）+ `_re/reference_scores_boundary.tsv`（50 条边界探针），
   合计 729 条。检索与复核方法见 `_re/reference_scores.md`。
3. **与原程序直接对照**（可选，需要 Docker/Linux）：
   ```bash
   docker build -f scripts/Dockerfile.original -t peptideranker-original .
   docker run --rm -v "%cd%:/w" -w /w peptideranker-original \
       bash scripts/run_original.sh testfile.txt > _re/golden_original.txt
   ```
4. **逐条比对与脏数据分拣**：
   ```bash
   python scripts/validate_published.py            # 679 条真值 + 20aa 边界判定
   python scripts/validate_against_original.py     # 简化入口，读同一份 tsv，默认容差 ±0.01
   python scripts/validate_against_original.py --tolerance 0.001
   python scripts/detect_table_shift.py            # 区分「数据质量问题」与「真实算法偏差」
   python scripts/triage_reference_rows.py         # 分拣脏数据（三字母缩写 / 蛋白名混入）
   ```

结论：本引擎与**原版服务器**在同一算法上数值等价（86.1% 逐位相同、92.3% 在 ±0.01 内），
而不是「随便训了个模型」。`pr_engine/reference/FORMAT.md` 第 10、11 节把未解决的不确定性
（如 `.flatblast` 对齐路径不支持、非 ASCII 字符属原程序未定义行为）逐条显式列出，不做隐瞒。

---

## 如实说明的局限

**1. 那 7.8% 的偏差有三个具体来源**，均可在数据侧定位：

- 原论文 **Figure S3 是截图，只有 2 位小数**，且该截图对应的是**后来重建过的 web 服务器**，
  与我们手里 2010 年的二进制存在约 ±0.02 的版本差（15 条中有 13 条在 ±0.01 内，最大偏差 0.018）。
- 少数文献表格把**行标签与序列拼成了一串**（如 `ACEIDPPIVI`，其实是标签 `ACEI` / `DPPIV` 与序列 `I` 的拼接），
  其分数实际属于 `DPPIVI`，不是该「序列」本身的分数。
- **低复杂度/重复序列上偏差偏大**，这与 softmax 在近饱和区的数值敏感性一致。

详见 `_re/reference_scores.md` 的来源说明与 `scripts/detect_table_shift.py`、`scripts/triage_reference_rows.py` 的分拣结果。

**2. `testfile.txt` 那 15 条序列，在任何公开文献里都找不到原始分数。**
检索方式为两种独立手段：Europe PMC 全文检索，以及抓取 250 篇 OA 论文全文 XML 做逐字串匹配（0 命中）。
因此**无法对这 15 条做外部数值校验**——它们只用于证明「端到端可运行、输出格式与原脚本一致」。
这一点如实保留，不用它充作正确性证据。

**3. 其他已知边界**：

- 长度路由按**字符数**计算（含被跳过的非法字符），不是有效残基数。
- 空序列/长度 0 在原程序里会给出一个固定分数（实测 `0.4531538853`），产品层直接拒绝空输入。
- 工作目录下若存在 `<序列名>.flatblast`，原程序会读入对齐信息并改变 profile；本实现**不支持**该路径
  （仓库自带的输入流程不会产生该文件）。
- `0x20..0x7E` 之外（含非 ASCII）的字符在原程序里会越界读到未映射内存，属**未定义行为**；本实现按「跳过」处理。

---

## 环境要求

- **Python 3.9+**，以及 **NumPy**。NumPy 是引擎唯一的第三方运行时依赖；
  HTTP 服务与前端只用 Python 标准库与原生 JavaScript（无框架、无构建步骤、无 CDN）。
- Windows 下 `启动网页.bat` 会在缺失 NumPy 时尝试自动安装（这一步需要联网）。
- **不需要联网、不需要 Perl、不需要 Linux、不需要 Docker**；服务只监听 `127.0.0.1`，不对外暴露。
- 跨平台：`启动网页.bat` 与 `停止程序.bat` 是 Windows 专用的双击启动器；
  Linux/macOS 下的等价命令是 `python app/server.py --open`。
- Windows 下这两个 `.bat` 必须保持 **GBK 编码 + CRLF 换行**，否则 cmd 会拆坏命令。

---

## 署名、第三方声明与许可证

**重做的代码**（`pr_engine/` 下的 Python 引擎、`app/` 网页前端与 HTTP 服务、`pr_cli.py`、`scripts/` 下的脚本）
采用 **MIT 许可证**，全文见仓库根目录的 [`LICENSE`](LICENSE)。

**以下内容属于第三方产物**，仅为复现本仓库的数值校验而**原样**再分发，**权利归原作者**
（University College Dublin / Shields 实验室），不属于本仓库的重做部分：

- 2010 年的 Linux ELF 二进制 `PeptideRanker`；
- Perl 包装脚本 `PeptideRanker.pl`；
- `Models_Short/` 与 `Models_Long/` 下全部 **30 个 `.model` 权重文件**；
- 模型清单 `Models_Short.txt` / `Models_Long.txt`，以及示例输入 `testfile.txt`。

**MIT 许可证不覆盖上述第三方产物。** 本仓库不为这些产物声称任何许可证，也不代表原作者授权；
复用、再分发或商用这些产物时，需遵守原作者提出的条件，并自行确认其许可状态。
除上述清单外的其余文件（包括 `README`、`_re/`、`使用说明.md` 等文档）为本次重做新增。

---

## 引用

原方法与数据来自：

- Mooney C, Haslam NJ, Pollastri G, Shields DC.
  *Towards the Improved Discovery and Design of Functional Peptides: Common Features
  of Diverse Classes Permit Generalized Prediction of Bioactivity.*
  PLoS ONE, 2012, 7(10): e45012.
  <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0045012>
- PeptideRanker 原始服务器：<http://distilldeep.ucd.ie/PeptideRanker/>（早期为 `bioware.ucd.ie`）
