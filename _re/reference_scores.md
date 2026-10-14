# PeptideRanker 参考分数（文献 / 补充材料检索报告）

> 检索人：teammate `ref-hunter`　检索日期：2026-10-12
> 目的：为「2010 年 PeptideRanker Linux 二进制 → Python 重实现」提供**外部数值真值（golden values）**
> 配套机器可读文件：`_re/reference_scores.tsv`（679 条）、`_re/reference_scores_boundary.tsv`（50 条，20 aa 边界探针）

---

## 0. 一句话结论

| 问题 | 结论 |
|---|---|
| `testfile.txt` 里那 15 条序列，公开文献中有原始分数吗？ | **没有。0 / 15。** 逐条证据见 §6 |
| 能否找到**原程序（原版服务器）给出的确切分数**？ | **能，679 条**（序列+分数成对，全部可复核） |
| 其中最高权威的是？ | 原论文 **Figure S3**（原版服务器结果页**截图**）里的 **15 条**；以及原论文正文明确写出的 **YPFVEPI = 0.506** |
| 这些不是 testfile 的 15 条，还有校验价值吗？ | **有，而且是目前唯一可行的路子**：可直接用我们的 Python 引擎跑这 679 条序列，逐条比对误差分布，覆盖 Short(≤20 aa) 与 Long(>20 aa) 两套模型 |

---

## 1. 复核方法与可复核性声明（请先读）

### 1.1 `web_fetch` 工具在本会话完全不可用
本会话中 `web_fetch` 对**所有** URL 都失败，包括 `https://example.com`：

```
Error: web fetch failed: TypeError: fetch failed
```

这不是站点问题，是 harness 侧的网络通道故障。因此**本报告所有数据都不是用 `web_fetch` 取的**，改用：

* 内置 Python 3（`urllib`）+ 主机代理 `127.0.0.1:7897` 做 HTTPS GET；
* Shell 侧 `curl.exe` 亦不可用（`schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`），
  故 shell 网络路径也已排除。

### 1.2 只采用「稳定公开 API」作为数据来源
| 来源类型 | URL 模板 | 状态 |
|---|---|---|
| Europe PMC 全文 XML（JATS） | `https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML` | ✅ 可用，已用 |
| Europe PMC 检索 API | `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=...&format=json` | ✅ 可用，已用 |
| PLOS 补充材料文件 | `https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0045012.sNNN&type=supplementary` | ✅ 可用，已用 |
| UCD 机构库全文 PDF | `https://researchrepository.ucd.ie/server/api/core/bitstreams/27ea7086-358b-4b62-86cf-5dffbf0a71f0/content` | ✅ 可用（原论文开放版，与 PLOS 版一致） |
| ACS / MDPI / PMC 网页版 / europepmc.org HTML | — | ❌ 全部 Cloudflare 403，**已剔除其数据** |
| `api.crossref.org` | — | ⚠️ 时通时断 |

### 1.3 复核步骤（其他人可原样重跑）
```powershell
# 例：复核 VPYPR = 0.641232
python -c "import urllib.request;print(urllib.request.urlopen('https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12651066/fullTextXML',timeout=40).read().decode())" > PMC12651066.xml
# 然后在 PMC12651066.xml 中查找 VPYPR / 0.641232（表格表头为 "PeptideRanker Score"）
```
> 注：`pmc.ncbi.nlm.nih.gov` 返回一个 ~10 KB 的挑战页，**不能**用于复核；请用上面的 REST 地址。

### 1.4 文件完整性
| 文件 | 行数（非注释） | 涉及论文数 | SHA-256 |
|---|---|---|---|
| `_re/reference_scores.tsv` | 679 | 52 个 PMCID | `9a450e9fcf2e3bffe30d3c3ded8ae36c8b642f36ddc85350a8f346f81a951314` |
| `_re/reference_scores_boundary.tsv` | 50 | 9 个 PMCID | `22e9da77343c1a90951a37a7dfd0752728021af4344c92f3b989ebeeb79f9bcc` |

---

## 2. 【最高权威】原版程序自己的输出

### 2.1 原论文 Figure S3 —— 原版 PeptideRanker 网页**结果页截图**，15 条 (序列, 分数)

**来源**：Mooney C, Haslam NJ, Pollastri G, Shields DC (2012) *PLoS ONE* 7(10): e45012, Figure S3 "Web server results page"。
**文件 URL（可复核）**：
`https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0045012.s003&type=supplementary`
（同文件也在 Europe PMC 补充材料包内：`https://www.ebi.ac.uk/europepmc/webservices/rest/PMC3466233/supplementaryFiles` → `pone.0045012.s003.png`）

| # | 序列 | 分数（图内显示精度 2 位） | 长度 | 模型 |
|---|---|---|---|---|
| 0 | FPFGPIP | 0.94 | 7 | Short |
| 1 | YPFPGPI | 0.92 | 7 | Short |
| 2 | FPGPIPN | 0.89 | 7 | Short |
| 3 | VYPFPGP | 0.88 | 7 | Short |
| 4 | SLVYPFP | 0.84 | 7 | Short |
| 5 | LVYPFPG | 0.81 | 7 | Short |
| 6 | QSLVYPF | 0.76 | 7 | Short |
| 7 | GPIPNSL | 0.59 | 7 | Short |
| 8 | PIPNSLP | 0.56 | 7 | Short |
| 9 | PGPIPNS | 0.50 | 7 | Short |
| 10 | PNSLPQN | 0.37 | 7 | Short |
| 11 | IPNSLPQ | 0.35 | 7 | Short |
| 12 | TQSLVYP | 0.16 | 7 | Short |
| 13 | AGTQSLV | 0.12 | 7 | Short |
| 14 | QTQSLVY | 0.10 | 7 | Short |

说明：
* 该图同时被另一份补充图 Figure S2（`...s002.png`）佐证：S2 是**输入页截图**，输入框里的 15 条序列
  （AQTQSLV / QTQSLVY / TQSLVYP / QSLVYPF / SLVYPFP / LVYPFPG / VYPFPGP / YPFPGPI / FPFGPIP /
  FPGPIPN / PGPIPNS / GPIPNSL / PIPNSLP / IPNSLPQ / PNSLPQN）与 S3 的输出**一一对应**，无歧义。
* 这 15 条完全满足论文正文的描述："Only one of the overlapping peptides scored slightly higher,
  and it overlaps for 6 of its 7 residues"（FPFGPIP 0.94 > YPFPGPI 0.92，两者 7 位中有 6 位重合），
  以及"Many of the overlapping peptides are predicted not to be bioactive, since they are returned
  with values of under 0.5"（0.37 / 0.35 / 0.16 / 0.12 / 0.10 共 5 条 < 0.5）。
* **这是与工作目录里那份 2010 二进制最同源的真值**（同一篇论文、同一时期）。

### 2.2 原论文正文明确写出的分数

| 序列 | 分数 | 原文 | 来源 |
|---|---|---|---|
| YPFVEPI | **0.506** | "Human beta-casomorphin 7 (YPFVEPI) differs in two positions to the Bovine peptide and is not predicted as strongly to be bioactive (0.506)." | [PLOS ONE 原文](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0045012) / [Europe PMC 全文 XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC3466233/fullTextXML) |
| 牛 β-casomorphin 4/5/6/8/11 | 区间 **0.828–0.969** | "The other Bovine beta-casomorphins (4, 5, 6, 8 and 11) are also predicted to be bioactive (0.828–0.969)." | 同上 |
| YPFPGPI（β-casomorphin 7） | 0.92 | 见 Figure S3 | 见 §2.1 |

> ⚠️ `0.506` 只有 3 位小数，且论文未给出另外 5 个 β-casomorphin 的逐条数值（只有区间）。
> 若要用于严格等价判定，建议以 §2.1 的 15 条 2 位小数 + §3 的 6 位小数数据为主。

---

## 3. 第三方论文报告的原版服务器分数（679 条中的 664 条）

### 3.1 收录标准（避免混入非 PeptideRanker 数字）
每条数据必须**同时**满足：
1. 该数值所在表格的**列标题**字面包含 `PeptideRanker` / `Peptide Ranker`（本报告用的正则：`peptide\s*rank`）；
2. 数值位于该列对应的单元格内（按列索引取值，不是"行内随便一个 0~1 小数"）；
3. 论文正文写明使用 `http://distilldeep.ucd.ie/PeptideRanker/`（即**原版服务器**）；
4. 分数的打印精度 ≥ 4 位小数（原版服务器输出为 6 位小数，第三方多按原样抄录）。

### 3.2 多篇独立论文互相印证（**最高置信度**，建议先用这 5 条）

| 序列 | 分数 | 独立来源数 | 来源（可复核 URL） | 备注 |
|---|---|---|---|---|
| **VPYPR** | **0.641232** | 2 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12651066/fullTextXML<br>https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13608502/fullTextXML | 两篇不同论文**逐位完全相同**；且分别发表于 Foods 2025 与 Marine Drugs 2026 |
| **FIDNIFRF** | **0.956105** | 2 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10780882/fullTextXML<br>https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13361991/fullTextXML | 另一篇报 0.96（四舍五入一致） |
| **YPWTQRFF** | **0.9556** | 2 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12840617/fullTextXML<br>https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12469255/fullTextXML | 另一篇报 0.956（一致） |
| **FGFDGDF** | **0.93535** | 2 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11900222/fullTextXML<br>https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12249663/fullTextXML | 两篇均为 0.93535 |
| **VPPF** | **0.926314** | 2 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11838108/fullTextXML<br>https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12734967/fullTextXML | 两篇均为 0.926314 |

> 这 5 条是"同一序列在不同实验室、不同年份、不同期刊得到同一 6 位小数"的强证据，
> 说明原版服务器数值稳定、可复现，**非常适合当基准**。

### 3.3 短肽（≤ 20 aa，走 Short 模型）代表性样本

（完整 620 条见 `_re/reference_scores.tsv`；此表每条均取自"列标题含 PeptideRanker"的表格）

| 序列 | 长度 | 分数 | 来源 PMCID | 复核 URL |
|---|---|---|---|---|
| ACMGPCC | 7 | 0.960273 | PMC13509369 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13509369/fullTextXML |
| ADHPFLFL | 8 | 0.968736 | PMC10780882 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10780882/fullTextXML |
| ADWDFLPAK | 9 | 0.910647 | PMC11988861 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11988861/fullTextXML |
| AQEACWF | 7 | 0.863384 | PMC12138630 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12138630/fullTextXML |
| DLWGPGWG | 8 | 0.954746 | PMC12400163 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12400163/fullTextXML |
| ESWPGSR | 7 | 0.614027 | PMC10093838 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10093838/fullTextXML |
| FKAAFDMF | 8 | 0.902981 | PMC12844674 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12844674/fullTextXML |
| FLSPF | 5 | 0.964433 | PMC10649794 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10649794/fullTextXML |
| LPYPY | 5 | 0.829798 | PMC11838108 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11838108/fullTextXML |
| LYYAPF | 6 | 0.878367 | PMC11900222 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11900222/fullTextXML |
| GPFPILN | 7 | 0.905623 | PMC11838108 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11838108/fullTextXML |
| GPFPLL | 6 | 0.967691 | PMC11838108 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11838108/fullTextXML |
| RPWR | 4 | 0.938535 | PMC11838108 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11838108/fullTextXML |
| WHLR | 4 | 0.829836 | PMC11838108 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11838108/fullTextXML |
| WARF | 4 | 0.981525 | PMC12138630 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12138630/fullTextXML |
| VYNKFPYTTQ | 10 | 0.18 | PMC9775090 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9775090/fullTextXML |
| IGNNPAKGGLF | 11 | 0.82 | PMC9967564 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9967564/fullTextXML |
| DAALDFGPAL | 10 | 0.78 | PMC9967564 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9967564/fullTextXML |
| APLVSW | 6 | 0.516023 | PMC10674851 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10674851/fullTextXML |
| ATISLENSW | 9 | 0.191382 | PMC10674851 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10674851/fullTextXML |
| DEQSSEK | 7 | 0.0487441 | PMC12478930 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12478930/fullTextXML |
| TPEVDDEALEK | 11 | 0.0891689 | PMC11381472 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11381472/fullTextXML |
| SVVVGPSV | 8 | 0.0990451 | PMC12689192 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12689192/fullTextXML |
| GQVEVTGSK | 9 | 0.0699837 | PMC13114659 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13114659/fullTextXML |
| ACSLLPPMLYSSPLALSR | 18 | 0.826857 | PMC9100645 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9100645/fullTextXML |
| DILKEDMPSQRYLEELHR | 18 | 0.125535 | PMC13486097 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13486097/fullTextXML |
| ALPMHIRL | 8 | 0.811703 | PMC11838108 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11838108/fullTextXML |
| VPYPR | 5 | 0.641232 | PMC13608502 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13608502/fullTextXML |

### 3.4 长肽（> 20 aa，走 Long 模型）代表性样本（完整 44 条见 TSV）

| 序列 | 长度 | 分数 | 来源 PMCID | 复核 URL |
|---|---|---|---|---|
| AMATSAATLLPFSLCLLLLCRASLAQFGR | 29 | 0.994361 | PMC9100645 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9100645/fullTextXML |
| EMGAMGDRTAVMLLMLLLSSWCLTAVTGNR | 30 | 0.998699 | PMC9100645 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9100645/fullTextXML |
| MMSLVSLLLVGILFPTIQAKQFTK | 24 | 0.97371 | PMC13486097 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13486097/fullTextXML |
| QSFQQSESEQQGEKGQRRRSRDEHQRI | 27 | 0.870457 | PMC9100645 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9100645/fullTextXML |
| FTGPPGEPGEAGAPGPMGPRG | 21 | 0.713347 | PMC12681514 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12681514/fullTextXML |
| GPRGPAGPNGPPGKDGSNGMPG | 22 | 0.706289 | PMC12681514 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12681514/fullTextXML |
| ATGPQGPAGQRGPAGPTGPTGPAG | 24 | 0.562816 | PMC12651066 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12651066/fullTextXML |
| ACEIHDPPIVIDPPIIIIRIPLI | 23 | 0.58977 | PMC12195943 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12195943/fullTextXML |
| EPTTSDVVVAGEFDQGSGSMR | 21 | 0.172646 | PMC10674851 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10674851/fullTextXML |
| EGPLSLSEGPSIGPEGGPGGAGVGGG | 26 | 0.269803 | PMC12689192 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12689192/fullTextXML |
| NPARDDRSTSFQTQLGPSGHDSGRR | 25 | 0.390839 | PMC12689192 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12689192/fullTextXML |
| REGAQPGAQPGPEPAAEEQPQAP | 23 | 0.737179 | PMC12689192 | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12689192/fullTextXML |

**分数分布（664 条中的可解析值）**：最小值 ≈ 0.0487，最大值 ≈ 0.9987，
`> 0.5` 的比例约 60%。可作为"引擎输出是否落在合理分布"的粗筛。

---

## 4. 【重点】20 aa 边界归属：论文与脚本互相矛盾

这是本次检索中**对复现最有价值的一条语义发现**。

| 出处 | 说法 |
|---|---|
| 原论文正文（PLOS ONE 2012） | "the web server automatically uses the **short peptide predictor for peptides of less than 20 amino acids**, and the **long peptide predictor for peptides of 20 or more residues**。" → 即 **`len < 20` → Short，`len >= 20` → Long** |
| 工作目录 `PeptideRanker.pl`（2010-12-13） | `if ($length <= 20) { Models_Short } else { Models_Long }` → 即 **`len <= 20` → Short，`len > 20` → Long** |

**恰好 20 aa 的肽**（例如 `testfile.txt` 第 14 条 `FLSLALAALPKLFCLIFKKC`）会因这条规则得到完全不同的分数，
因此它是判定真实规则的**决定性样本**。

好消息：**文献里有 11 条长度为 20 aa 的已发表分数**，全部已单列到
`_re/reference_scores_boundary.tsv`（含 17–23 aa 共 50 条，格式 `序列\t长度\t分数\t来源URL`）：

| 序列 | 长度 | 分数 | 来源 PMCID |
|---|---|---|---|
| FTGPPGEPGEAGAPGPMGPR | 20 | 0.806036 | PMC12681514 |
| GDKAQGVKTDMESWWKKYVF | 20 | 0.737327 | PMC11990805 |
| GDKASGVKVDMESWWNTYIF | 20 | 0.750464 | PMC11990805 |
| GPAGPNGPPGKDGSNGMPGA | 20 | 0.911339 | PMC12681514 |
| GPAGSSGPAGKDGMSGLPGP | 20 | 0.873632 | PMC12681514 |
| GPPGAPGPPGPPGPSGGGFD | 20 | 0.936409 | PMC12681514 |
| GVSFPFPVSSSSAAPPVCCR | 20 | 0.882809 | PMC9100645 |
| HVGKTPIVGQPSIPGGPVRL | 20 | 0.524718 | PMC12689192 |
| QGPSGPSGERGPPGPMGPPG | 20 | 0.892594 | PMC12681514 |
| TGPPGEPGEAGAPGPMGPRG | 20 | 0.831545 | PMC12681514 |
| GFAGDDAPRAVFPSIVGRPR | 20 | 0.6456 | PMC10217141 |

**用法**：用两种规则各跑一遍这 11 条 20-mer，哪一套与上表整体吻合（容差 ±0.01），就确认了真实规则。
额外提示：`PMC12681514` 提供了一串长度 17→21 aa 的**连续递增肽**
（`TGPPGEPGEAGAPGPMGPR`(19) / `TGPPGEPGEAGAPGPMGPRG`(20) / `FTGPPGEPGEAGAPGPMGPRG`(21) /
`FTGPPGEPGEAGAPGPMGPR`(20) …），同一篇论文、同一批实验，**非常适合精确定位切换点**。

---

## 5. 分数语义与阈值（用于交叉验证实现语义）

### 5.1 原版语义（原论文）
* 输出是 **0–1 的概率**："the predicted probability (between 0 and 1) of that peptide being bioactive.
  The closer the predicted probability is to 1, the more confident PeptideRanker is that the peptide is bioactive."
* **训练阈值 0.5**："PeptideRanker was trained at a threshold of 0.5 i.e. any peptide predicted over a
  0.5 threshold is labelled as bioactive."
* 论文报告的高阈值影响：阈值 0.8 时 FPR 从 **11% / 16%**（long / short，@0.5）降到 **2% / 6%**。
* 论文 Table 1（五折交叉验证 @0.5）：Long `MCC 0.72 / Q 86.1`，Short `MCC 0.51 / Q 75.6`；
  独立测试集 Long `MCC 0.74 / AUC 0.94`，Short `MCC 0.54 / AUC 0.83`。
* 论文 Table S1/S5/S6/S10 的标题均写 "measured at a threshold of 0.5"（补充材料 s004/s008/s009/s013）。
* 分界：见 §4（论文 vs 脚本矛盾）。
* 语义提醒（原文）：服务器预测的是 **"how likely the peptide is to be bioactive"，不是 "how bioactive"**。

### 5.2 第三方论文的阈值用法（原版服务器语境，可复核）
| 用法 | 原文片段 | 来源 |
|---|---|---|
| `> 0.5` 判为可能活性 | "Peptides with a PeptideRanker score **above 0.5** are predicted to be potentially biologically active" | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10093838/fullTextXML |
| `> 0.5` 筛选 | "The peptides with active scores **> 0.5** had been identified as promising bioactive peptides." | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10224335/fullTextXML |
| 阈值可自定义 | "we set the score screening threshold to 0.5; that is, peptides with a score higher than 0.5 are considered..." | 同上 |
| 用 0.8 更严 | "using the threshold value of **> 0.8** for the PeptideRanker score" | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10254627/fullTextXML |
| 范围 0–1、越高越可能 | "The results were displayed as PeptideRanker scores, **from 0 to 1**. The higher the PeptideRanker score, the higher the likelihood for a peptide to be bioactive." | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10454390/fullTextXML |
| 常用阈值 0.5 | "none of the identified peptides exceeded the commonly used PeptideRanker **threshold of 0.5**" | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13114659/fullTextXML |
| 可接受区间 0.5–1.0 | "Acceptable probability values for bioactivity are between **1.0–0.5**." | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9967564/fullTextXML |
| N-to-1 神经网络 | "classified by the software PeptideRanker ... using the **N-to-1 neural network probability**" | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10138644/fullTextXML |

### 5.3 输出精度
* 原版服务器网页显示 **2 位小数**（Figure S3）。
* 第三方论文大量以 **6 位小数**原样抄录（如 `0.641232`、`0.956105`、`0.998699`），
  说明原版服务器的底层输出精度 ≥ 6 位。**建议引擎内部按 6 位以上精度计算，比较时用 ±1e-2 起步。**

---

## 6. `testfile.txt` 15 条序列：逐条检索结果 = **全部未找到**

### 6.1 检索方法（两种独立手段，结果一致）
1. **Europe PMC 全文检索**（覆盖所有 OA 论文全文，含表格）：
   - 检索式 A：`"<序列>"` → 看该序列本身是否出现在文献中；
   - 检索式 B：`"<序列>" AND "PeptideRanker"` → 看是否有论文同时报告该序列与 PeptideRanker。
2. **250 篇 OA 论文全量下载 + 逐字串匹配**：检索 `"PeptideRanker" AND OPEN_ACCESS:Y`，抓取 250 篇
   的 Europe PMC 全文 XML，把本文件 15 条序列在 XML 中直接字符串匹配 → **0 命中**。

### 6.2 逐条结果

| # | 序列 | 长度 | 走哪个模型 | 序列本身在文献中 | 与 PeptideRanker 同现 | 找到分数？ |
|---|---|---|---|---|---|---|
| 1 | ILPILSLIGGLL | 12 | Short | 有（1 篇：PMC10049141 Temporins 综述） | 0 | ❌ 未找到 |
| 2 | RPPGFSPFR | 9 | Short | 有（225 篇，缓激肽） | 1 篇（PMC13054063，但**无分数**） | ❌ 未找到 |
| 3 | FLPIVGKLLSGLSGLL | 16 | Short | 有（3 篇：PMC13276644 / PMC10049141 等） | 0 | ❌ 未找到 |
| 4 | LLPIVGKLLSGLL | 13 | Short | **0 篇** | 0 | ❌ 未找到 |
| 5 | ALLHHGLNCAKGVLA | 15 | Short | 有（6 篇，halocidin 相关） | 0 | ❌ 未找到 |
| 6 | AGIRRPPGFSPLRIA | 15 | Short | 有（1 篇：PMC4379535 缓激肽综述） | 0 | ❌ 未找到 |
| 7 | RENSLPAGLSPLR | 13 | Short | **0 篇** | 0 | ❌ 未找到 |
| 8 | RVISLPAGLSPFR | 13 | Short | **0 篇** | 0 | ❌ 未找到 |
| 9 | EEERDEDEVIEEEVKRGLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC | 54 | Long | **0 篇** | 0 | ❌ 未找到 |
| 10 | GLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC | 33 | Long | 有（1 篇：PMC7073735，蛙皮肤抗菌肽） | 0 | ❌ 未找到 |
| 11 | EQERDADEDEVVEEVKRGLWESIKNLGKKFALNIMEKLKCKFGGGCLP | 48 | Long | **0 篇** | 0 | ❌ 未找到 |
| 12 | GLWESIKNLGKKFALNIMEKLKCKFGGGCLP | 31 | Long | **0 篇** | 0 | ❌ 未找到 |
| 13 | EEERNADEEERRDDLEERDVEVEKRFLSLALAALPKLFCLIFKKC | 46 | Long | **0 篇** | 0 | ❌ 未找到 |
| 14 | FLSLALAALPKLFCLIFKKC | **20** | **Short(脚本) / Long(论文)** | **0 篇** | 0 | ❌ 未找到（边界样本，见 §4） |
| 15 | EEERNVDEERRDDPEERAVEVEKRILPILSLIGGLLGK | 38 | Long | **0 篇** | 0 | ❌ 未找到 |

### 6.3 结构性观察（供判断 `testfile.txt` 的性质）
序列之间有明显构造关系，说明它们是**人工设计/拼接**的而非文献原样引用：

* #10 是 #9 的 C 端片段；#12 是 #11 的 C 端片段；#14 是 #13 的 C 端片段
  （"阴离子 N 端延伸段 + 成熟肽核心"的典型设计模式）；
* #15 = `EEERNVDEERRDDPEERAVEVEKR` + #1 的 `ILPILSLIGGLL` + `GK`；
* #2 RPPGFSPFR（缓激肽）与 #6 `AGIRRPPGFSPLRIA`、#7/#8 疑似同族的 bradykinin 相关变体。

**结论**：这 15 条很可能是原作者为随二进制发布的示例文件（或为某次测试）**自造的肽**，
因此"公开文献里存在它们的原始分数"这一假设大概率不成立。
**验收基准应改为**：用 §2.1（原版服务器截图 15 条）+ §3（679 条）来证明数值等价，
而 `testfile.txt` 则用于证明"端到端可运行、输出格式与原脚本一致"。

---

## 7. 区分：原版服务器 vs 第三方重实现 / 其他工具

| 类别 | 判定依据 | 本报告是否收录 |
|---|---|---|
| **原版 web 服务器**（`distilldeep.ucd.ie/PeptideRanker/`，早期为 `bioware.ucd.ie`） | 论文正文明确给出该 URL，且分数列标注 PeptideRanker | ✅ 全部 679 条均属此类 |
| **原版程序自带截图/正文**（原论文 Figure S3、正文 0.506） | 出自 Mooney 2012 原文 | ✅ §2 共 16 条（15 + 1） |
| **第三方重实现 / 其他工具** | 例如把 PeptideRanker 作为基线对比的机器学习论文（如 MultiPep）、或使用 BIOPEP/UW 的 `FRS` 分数 | ❌ **未收录**（`FRS score`、`PeptideRanker (FRS score)` 等混用行已排除） |
| 无法复核的来源 | ACS 补充材料（Cloudflare 403）、MDPI 网页版（403） | ❌ 剔除，仅在此登记（§8） |

> 注意：有部分论文把 PeptideRanker 分数与 BIOPEP 的 `FRS`（Frequency of Release of Fragments）混写
> 在同一张表里。本报告按**列标题**取数，已避免把 FRS 当成 PeptideRanker。

---

## 8. 未能复核 / 未找到清单（如实登记，**未编造任何数字**）

| 目标 | 状态 | 说明 |
|---|---|---|
| 15 条 testfile 序列的原始分数 | **未找到** | 见 §6 |
| ACS JAFC 补充材料中的 `LYYAPF = 0.878367` | **无法复核**（但已由 PMC11900222 独立复核为同一数值） | `pubs.acs.org` 三路尝试均返回 403 Cloudflare 挑战页（`Just a moment...`），故未作为独立来源；`0.878367` 一条已用 Marine Drugs 论文（PMC11900222）复核通过 |
| 原 PeptideRanker 官网/帮助页的输出格式说明 | **未获取** | `bioware.ucd.ie` / `distilldeep.ucd.ie` 的 Wayback 快照 CDX 查询可返回条目，但页面检索不稳定；不影响结论，因为 §2.1 的截图已直接给出输出示例 |
| 原论文 Table S1–S13 | 已获取但**无用** | 内容为 Spec/Sen/FPR/Q/MCC 等性能指标，**不含任何逐条肽的分数**（已逐份 PDF 提取文本核实） |
| `testfile.txt` 第 14 条 `FLSLALAALPKLFCLIFKKC`（20 aa）的外部分数 | **未找到** | 它是判定 §4 边界规则的决定性样本，但文献中不存在；建议改用 §4 表中的 11 条 20-mer 替代判定 |

---

## 9. 附录

### 9.1 用到的检索式（Europe PMC REST）
```
https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=<QUERY>&format=json&pageSize=100&resultType=core
QUERY 示例：
  "PeptideRanker" AND OPEN_ACCESS:Y
  "VPYPR"
  "<序列>" AND "PeptideRanker"
  DOI:"10.1371/journal.pone.0045012"
  PMCID:PMC3466233 / PMC12651066 ...
```

### 9.2 主要来源 URL
| 内容 | URL |
|---|---|
| 原论文（PLOS ONE） | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0045012 |
| 原论文全文 XML（Europe PMC，PMCID 更正为 **PMC3466233**） | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC3466233/fullTextXML |
| 原论文补充材料打包（含 Figure S2/S3、Table S1–S13） | https://www.ebi.ac.uk/europepmc/webservices/rest/PMC3466233/supplementaryFiles |
| Figure S3（原版服务器结果页截图，15 条分数） | https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0045012.s003&type=supplementary |
| Figure S2（输入页截图，佐证序列列表） | https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0045012.s002&type=supplementary |
| 原论文开放版（UCD 机构库） | https://researchrepository.ucd.ie/server/api/core/bitstreams/27ea7086-358b-4b62-86cf-5dffbf0a71f0/content |

> ⚠️ 提醒：早期检索出现的 `PMC3471936` 是**另一篇无关论文**（纳米颗粒载药），
> 原论文正确 PMCID 是 **PMC3466233** / PMID **23056189**。

### 9.3 交付文件
| 文件 | 内容 | 行数 |
|---|---|---|
| `_re/reference_scores.tsv` | `序列\t分数\t来源URL`；15 条原论文 Fig.S3 + 664 条第三方原版服务器分数 | 679 |
| `_re/reference_scores_boundary.tsv` | `序列\t长度\t分数\t来源URL`；17–23 aa，含 11 条恰好 20 aa 的边界探针 | 50 |
| `_re/reference_scores.md` | 本文件 | — |

### 9.4 引用到的关键第三方文献（DOI）
| PMCID | DOI | 期刊 / 年 | 用途 |
|---|---|---|---|
| PMC13608502 | 10.3390/md24090298 | Marine Drugs 2026 | VPYPR 0.641232 |
| PMC12651066 | 10.3390/foods14223848 | Foods 2025 | VPYPR 0.641232（第二条独立证据） |
| PMC10780882 | 10.3390/nu16010117 | Nutrients 2023 | FIDNIFRF 0.956105 等 10 条 |
| PMC13361991 | 10.3390/foods15132396 | Foods 2026 | FIDNIFRF 0.96（一致） |
| PMC12840617 | 10.3390/foods15020398 | Foods 2026 | YPWTQRFF 0.9556 |
| PMC12469255 | 10.3390/foods14183243 | Foods 2025 | YPWTQRFF 0.956（一致） |
| PMC11900222 | 10.3390/ijms26052119 | IJMS 2025 | FGFDGDF 0.93535、LYYAPF 0.878367 |
| PMC11838108 | 10.1016/j.fochx.2025.102217 | Food Chem X 2025 | VPPF 0.926314、LPYPY 0.829798 等 |
| PMC12681514 | 10.1016/j.fochx.2025.103294 | Food Chem X 2025 | 大量 17–21 aa 连续长度肽（**边界判定首选**） |
| PMC9100645 | 10.3390/molecules27092987 | Molecules 2022 | 大量 >20 aa 长肽分数（Long 模型） |
| PMC9967564 | 10.3390/md21020090 | Marine Drugs 2023 | PeptideRanker 语义/区间说明 + 逐条分数 |
| PMC10093838 | 10.3390/foods12071554 | Foods 2023 | 阈值 0.5 语义 + 6 条分数 |
| PMC13114659 | 10.3390/cimb48040374 | Curr Issues Mol Biol 2026 | "commonly used threshold of 0.5" |

---

*本报告不含任何推测或编造的数值；凡未取得来源的条目一律标注"未找到 / 无法复核"。*
