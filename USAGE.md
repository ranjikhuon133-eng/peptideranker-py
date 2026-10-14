# PeptideRanker — User Guide (for the person who just unzipped this folder)

**English** | [中文](使用说明.md)

Technical documentation for developers: [README.md](README.md) (English) ·
[README.zh-CN.md](README.zh-CN.md) (中文技术文档)

---

## What this tool is

This is a **peptide bioactivity scoring tool** (a rebuilt PeptideRanker): you give it
amino-acid sequences, and it gives each one a score between 0 and 1 saying how likely
that peptide is to be bioactive. You do not need Linux, you do not need to type any
commands, and — apart from a possible one-time numpy install on the first launch — it
does not need the internet: you just double-click one file.

---

## How to open it

1. **Extract the whole folder** to any location you like (for example your Desktop).
   ⚠️ Do not copy just a few files out of the zip — the program needs the **30 model
   files** stored under `Models_Short/` and `Models_Long/`. A partially extracted
   folder cannot score anything.
2. Double-click **`启动网页.bat`** in that folder.
3. Wait a few seconds. Your browser opens <http://127.0.0.1:8737/> automatically.
   If it does not open by itself, read the address printed in the black console
   window and open that address manually.

> The first launch may try to install a small component called **numpy**, which needs
> internet access once. If this computer is offline, see
> [numpy install failed](#numpy-install-failed) in the FAQ below.

---

## Closing the program properly (important)

**Closing the browser tab does not close the program.** The program itself is the
service running inside the **black console window**; the browser is only its user
interface. That is why Task Manager (or a packaging tool) may still show the program
running after you have closed the page.

There are three equivalent ways to shut it down cleanly — pick any one:

| Way | What to do | When it suits you |
|---|---|---|
| **Recommended** | In the web page, click **「退出程序」 / "Quit"** at the top right, then confirm | You are using the page and just want to close it |
| Most direct | **Close the black console window** (or press `Ctrl+C` in it) | You can still see that window |
| Automatic | **Close every browser tab** and wait for the idle timeout | You forgot about it and do not want to bother |

Two details about these ways:

- The **「退出程序」 / "Quit"** button works by sending `POST /api/shutdown` to the
  local server, so it stops exactly the same service as closing the console window.
- The automatic way is time-based: while the page is open it sends a "I am still
  here" **heartbeat to the server every 20 seconds**. As soon as the page is gone the
  heartbeats stop, and after the configured idle time the service exits by itself and
  releases the port. That idle time is the `--idle-exit-minutes` setting, **10 minutes
  by default**, and **the page footer shows the value currently in effect**.

**Fallback:** if the console window was closed by accident, or the service is stuck
and did not exit cleanly, double-click **`停止程序.bat`** in the folder. It first asks
the service to exit gracefully and, if the service is still running a few seconds
later, forces the process to stop and frees the port.

---

## How to use it

### Entering peptide sequences (three ways, pick one)

| Way | What to do |
|---|---|
| Paste | One sequence per line — just paste into the input box |
| Upload a file | Drag a `.txt` / `.fasta` / `.fa` / `.csv` file onto the dashed box, or click it to choose a file (`选择文件` / "Choose file") |
| Try the examples | Click **`载入示例` / "Load sample"** to fill in 15 example peptides |

Then press **`Ctrl + Enter`**, or click the **`开始打分` / "Start scoring"** button.

### Supported input notations

Plain lines, one sequence per line (the most common form):

```
ILPILSLIGGLL
RPPGFSPFR
```

FASTA format — a line starting with `>` gives the name (sequence ID) of the record
that follows:

```
>pep1 bradykinin
RPPGFSPFR
```

CSV / TSV without a header — the column that looks like a sequence is picked
automatically, and the first column is used as the ID:

```
p1,RPPGFSPFR,test
p2,ILPILSLIGGLL,test
```

CSV with an `id,sequence,note` header — the `sequence` column is recognised
automatically:

```
id,sequence,note
p1,RPPGFSPFR,test
```

---

## Reading the results

- Results are sorted by score **from high to low**. `rank 1` is the peptide most
  likely to be bioactive.
- **The score ranges from 0 to 1; the higher the score, the more likely the peptide
  is bioactive. A score ≥ 0.5 is conventionally read as "probably bioactive"** — note
  that 0.5 is just the usual cut-off from the original paper, not an absolute
  standard.
- The table shows six columns: rank (`排名`), sequence ID (`ID`), sequence (`序列`),
  length (`长度`), score (`分数`) and which model was used (`模型` — short-peptide or
  long-peptide model).
- The cards above are a statistical overview (`结果概览` / "Result overview"), and
  below them is a score-distribution histogram (`分数分布` / "Score distribution",
  10 equal-width bins).
- You can filter by **`全部` / "all"**, **`≥ 0.50`** or **`< 0.50`**, and click a
  column header to re-sort the table by that column.
- Click **`导出 CSV` / "Export CSV"** to get a spreadsheet file that
  **Excel / WPS can open by double-clicking** (it is written with a UTF-8 BOM, so
  Chinese and other non-ASCII text displays correctly instead of turning into
  garbage).
- Click **`复制 TSV` / "Copy TSV"** to copy the results and paste them straight into
  Excel.

---

## Switching the interface language (中文 / EN)

- The top bar has a **`中文 / EN`** control.
- On your first visit the interface follows your browser's language; after that your
  choice is remembered for next time.
- Switching languages re-renders the whole page immediately — including any warnings
  and pop-up messages — so there is no need to reload.
- Note that messages printed in the **black console window** are always in Chinese,
  regardless of the interface language.

Handy reference for the labels of the on-screen controls, so you can find the same
button in either mode:

| Chinese mode | English mode |
|---|---|
| `序列输入` | "Sequence input" |
| `载入示例` | "Load sample" |
| `选择文件` | "Choose file" |
| `清空输入` | "Clear input" |
| `开始打分` | "Start scoring" |
| `结果概览` | "Result overview" |
| `分数分布` | "Score distribution" |
| `排序结果` | "Ranked results" |
| `复制 TSV` | "Copy TSV" |
| `导出 CSV` | "Export CSV" |
| `清空` | "Clear" |
| `重试连接` | "Retry" |
| `退出程序` | "Quit" |
| `关闭` | "Close" |

---

## Where the score comes from

The scores come from the **30 model weight files published by the original authors**
(15 for short peptides, 15 for long peptides), combined by averaging exactly the way
the original program does — this is **not a retrained model**. Sequences of **20
residues or fewer use the short-peptide model, longer ones use the long-peptide
model**, which matches the original Perl script. The implementation was validated
against the scores from the original public PeptideRanker server on 729 published
scores: **92.3% agree to within ±0.01, and 86.1% are bit-identical**. The original
binary and the original model files are kept untouched in this folder.

---

## Frequently asked questions

### The window flashes and disappears / "no usable Python found"

This computer does not have Python installed. Download and install it from
<https://www.python.org/downloads/> — **during installation, be sure to tick
"Add python.exe to PATH"** — then double-click `启动网页.bat` again. The launcher
needs Python **3.9 or newer**.

If installing sends you to the Microsoft Store, that is because the `python` on this
system is only a placeholder stub (a `WindowsApps` entry), not a real Python.
Install Python as described above.

### numpy install failed

This computer has no internet access. The fix: on a machine that *is* online, install
Python plus numpy (`pip install numpy`), and then copy the whole Python environment
over together with this folder.

### I closed the web page, so why is there still a process running?

This is normal and by design: **closing the page is not closing the program.** The
program itself is the service in the console window opened by the launcher. Exit it
using any of the ways in
[Closing the program properly](#closing-the-program-properly-important):
**「退出程序」 / "Quit"** at the top right of the page, close the black window, or
close every page and let it exit by itself. If all else fails, double-click
`停止程序.bat`.

### Can I make it exit immediately after closing the page?

Yes — lower `--idle-exit-minutes` in the launch script. For example, change the last
line to

```
!PY! "app\server.py" --open --idle-exit-minutes 1
```

to exit one minute after the page is closed. Setting it to `0` means it never exits
automatically, so you always shut it down by hand.

### The console says port 8737 is already in use

Nothing to do — the program automatically switches to another free port. Just use the
address shown in the console window / opened in your browser.

### Can several computers use it at the same time?

Yes: copy the folder to each computer and double-click the launcher on each one (the
program only runs on the local machine, so the copies do not interfere with each
other). Do not have several people access the same window on one computer at the same
time — this is a single-user, local version.

### The browser will not open / the page is blank

First make sure the **black console window is still open** — closing it stops the
service. Then try another browser (Edge and Chrome both work). The page itself does
not need internet access.

### A result says `[警告] 含非法字符 ... 已跳过`

That line is not a valid amino-acid sequence (for example it contains digits or
punctuation). The program **does not** silently edit your sequence: it skips that line
and tells you, so you can fix it and try again.

### Why do some sequences score very high?

The 15 sequences in the sample file are themselves known bioactive peptides, so high
scores are expected. To get a feel for "random peptide" scores, type in a few random
sequences — most of them will come out below 0.5.

---

## What is in this folder

| File / directory | Description |
|---|---|
| **`启动网页.bat`** | **Double-click this one** |
| `app/` | The web application |
| `pr_engine/` | The scoring engine (Python) |
| `Models_Short/` `Models_Long/` | The 30 model weight files — **do not delete** |
| `Models_Short.txt` `Models_Long.txt` | Model manifests — **do not delete** |
| `PeptideRanker` `PeptideRanker.pl` | The original authors' 2010 program, kept as-is (for use under Linux) |
| `testfile.txt` | The original authors' example sequences |
| `pr_cli.py` | Command-line batch scoring (optional, for people comfortable with a terminal) |
| `README.md` | Full technical description and verification evidence for developers |
| `README.zh-CN.md` | 中文技术文档 |
| `使用说明.md` `USAGE.md` | The end-user guide in Chinese / English |
| `停止程序.bat` | Fallback "force stop" launcher (Windows) |
| `_re/` | Reverse-engineering working files and validation data (**safe to delete**, does not affect use) |
| `scripts/` | Various self-check / validation scripts (**safe to delete**, does not affect use) |
| `app/static/_mock/` | Mock server and front-end test harness (**safe to delete**, does not affect use) |

> Want the smallest possible copy? Keep just these 7 items — `启动网页.bat`, `app/`,
> `pr_engine/`, `Models_Short/`, `Models_Long/`, `Models_Short.txt` and
> `Models_Long.txt`. Everything else can be deleted; the result is about 2 MB.

---

## On Linux or macOS

`启动网页.bat` and `停止程序.bat` are **Windows-only**. On Linux or macOS, open a
terminal in the folder and run

```
python app/server.py --open
```

which starts the same local service and opens the same page in your browser. As on
Windows, the service listens only on `127.0.0.1` (this machine) and needs Python 3.9+
with numpy.
