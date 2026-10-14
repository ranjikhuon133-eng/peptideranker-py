# PeptideRanker Local — a pure-Python re-implementation of the original bioactivity scorer

> Score peptide bioactivity offline with a from-scratch NumPy re-implementation of PeptideRanker, verified numerically against the original 2010 binary and the authors' published server outputs.

**English** | [中文](README.zh-CN.md)

![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-required-013243?logo=numpy&logoColor=white)
![Extra runtime dependencies](https://img.shields.io/badge/extra%20runtime%20deps-0-2ea043)
![Local only](https://img.shields.io/badge/listens%20on-127.0.0.1-6e56cf)
![License](https://img.shields.io/badge/license-MIT%20(new%20code)-3da639)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555555)

**Bilingual documentation:** [README.md](README.md) (English) · [README.zh-CN.md](README.zh-CN.md) (中文) · [USAGE.md](USAGE.md) (English usage guide) · [使用说明.md](使用说明.md) (中文使用指南)

## Table of contents

- [What this is](#what-this-is)
- [Why this re-implementation exists](#why-this-re-implementation-exists)
- [Quick start](#quick-start)
  - [1. Web UI](#1-web-ui)
  - [2. Command line](#2-command-line)
  - [3. Python API](#3-python-api)
  - [4. HTTP API](#4-http-api)
- [The bilingual UI](#the-bilingual-ui)
- [Scoring semantics](#scoring-semantics)
- [The 0.5 threshold is a convention, not a branch](#the-05-threshold-is-a-convention-not-a-branch)
- [Intentional differences from the original](#intentional-differences-from-the-original)
- [Directory layout](#directory-layout)
- [Supported input formats](#supported-input-formats)
- [Reproducible verification](#reproducible-verification)
- [Honest limitations](#honest-limitations)
- [Environment requirements](#environment-requirements)
- [Attribution, third-party notice and license](#attribution-third-party-notice-and-license)
- [Citation](#citation)

## What this is

The original `PeptideRanker` is a 2010 Linux x86-64 binary (plus a Perl wrapper) that predicts whether a
peptide is likely to be bioactive. It cannot run on Windows, it needs Perl, it writes a temporary file per
sequence, and it only returns scores as text that has to be parsed.

This repository keeps that original binary and its 30 neural-network weight files **completely unmodified**
as a numerical ground-truth reference, and adds:

- a **from-scratch pure-Python (NumPy) re-implementation** of the same network
  (`pr_engine/reference/oracle.py`), derived by disassembling the binary;
- a **zero-dependency local web UI** served by a stdlib-only HTTP server (`app/server.py`, `app/static/`);
- a **command-line batch scorer** (`pr_cli.py`);
- a **verification suite** (`scripts/`) that checks the re-implementation against the original binary's
  disassembled semantics and against scores published by the original web server.

Nothing is retrained. The shipped weights are the authors' weights, read by a new forward pass.

## Why this re-implementation exists

| Problem with the original | How this repository solves it |
| --- | --- |
| `PeptideRanker` is a Linux x86-64 ELF and **cannot run on Windows at all** (and no WSL was available) | The same network is re-implemented in NumPy and runs as pure Python |
| `PeptideRanker.pl` hard-codes `$pipeline_dir="."`; moving the folder breaks it | All paths are resolved by the code itself; it works from any directory |
| Every sequence requires **rewriting** `peptide.dataset` and then `rm`-ing it | Inference happens in memory — no temporary files (safe for concurrent or batched subprocesses) |
| The score must be pulled out of `.predictions` by `shift`-ing the header lines and `split`-ing on spaces — pure text parsing | A float in `0..1` and structured JSON are returned directly |
| One file per run; the result is two columns `<score>\t<sequence>` | Any number of sequences per run; output includes rank, length, model source, summary statistics and a histogram |
| You had to install Perl and hand-edit the script's path | Double-click `启动网页.bat` on Windows |

The original distribution's own `README` file (kept unmodified as `README`) documents the first two rows of
that table: it tells the user to set `$pipeline_dir` to the full path of the executable before running
`./PeptideRanker.pl input_file output_file`.

The original workflow still works unchanged on Linux:

```bash
./PeptideRanker.pl testfile.txt testfile.ranked
```

## Quick start

The folder is about **3.6 MB** as shipped. Unpack it completely — the 30 weights under `Models_Short/` and
`Models_Long/` are required.

### 1. Web UI

Windows: double-click **`启动网页.bat`**. It locates a usable Python, installs `numpy` if it is missing,
starts the local service and opens <http://127.0.0.1:8737/> in the browser.

Any platform, manually:

```bash
python app/server.py --open          # default 127.0.0.1:8737; if the port is taken it walks forward
python app/server.py --port 9000     # pick a port explicitly
python app/server.py --idle-exit-minutes 15   # auto-exit after this many minutes without a page; 0 = never
```

`启动网页.bat` and `停止程序.bat` are **Windows-only double-click launchers**. On Linux/macOS the
equivalent is:

```bash
python app/server.py --open
```

The server is stdlib-only (`http.server`). It binds **only** to `127.0.0.1`, needs no network, no Perl,
no Linux and no Docker.

The page supports multi-line pasting, drag-and-drop or picking a file (`.txt/.fasta/.fa/.fna/.csv`), one-click
loading of the bundled 15-sequence sample, sorting by any column, filtering by `all / ≥0.5 / <0.5`, a
10-bin score histogram, a summary card row, copy-as-TSV and CSV export (UTF-8 BOM, opens directly in
Excel/WPS). `Ctrl + Enter` starts scoring.

**Exiting.** Closing the browser tab does **not** stop the service — the service is the process in the
launcher's console window. Three equivalent ways to shut it down cleanly (all release the port):

| Way | How |
| --- | --- |
| Recommended | Click **退出程序** in the top-right corner of the page (calls `POST /api/shutdown`) |
| Most direct | Close the launcher's console window, or press `Ctrl+C` in it |
| Automatic | Close every page and wait: the page sends a heartbeat every 20 s, and the server exits after `--idle-exit-minutes` (default 10) without one |

On Windows, `停止程序.bat` is a fallback: it requests the HTTP shutdown first and falls back to `taskkill`
if the window was closed by mistake or the service is stuck.

### 2. Command line

```bash
python pr_cli.py testfile.txt                              # score the bundled sample
python pr_cli.py testfile.txt -o scores.csv                # write a CSV instead of printing
python pr_cli.py --sequence ILPILSLIGGLL RPPGFSPFR         # score sequences given inline
python pr_cli.py testfile.txt --length-handling long --threshold 0.8 --quiet
python pr_cli.py - < testfile.txt                          # read from stdin
```

On Windows cmd the last line is `type testfile.txt | python pr_cli.py -`.

Useful flags: `--length-handling auto|short|long` (default `auto`), `--threshold` (default `0.5`; only
controls the `*` marker and the `n_above_threshold` counter), `--quiet`, and `--strict-case`, which
reproduces the original binary's case behaviour instead of treating lowercase as uppercase.

### 3. Python API

```python
from pr_engine import scoring

report = scoring.score_sequences([
    {"id": "P1", "sequence": "ILPILSLIGGLL"},
    {"id": "P2", "sequence": "EEERDEDEVIEEEVKRGLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC"},
])

for r in report.results:
    print(r.rank, r.id, r.sequence, f"{r.score:.4f}", r.model)   # model is "short" or "long"

print(report.as_dict()["summary"])   # count/mean/median/min/max/n_above_threshold/threshold
print(report.warnings)               # every skipped or rewritten line is reported here

csv_text = scoring.results_to_csv(report)   # UTF-8 BOM + CRLF, columns rank,id,sequence,length,score,model
tsv_text = scoring.results_to_tsv(report)   # for clipboard pasting
```

`scoring.parse_sequences(text)` uses the same parser as the web UI and the CLI. Invalid lines are skipped
with an explicit warning; they are never silently rewritten.

### 4. HTTP API

`app/server.py` exposes the contract that the UI uses (server banner `PeptideRankerLocal/1.0`):

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/status` | Engine readiness, model counts, the `0.5` `threshold` value, `idle_exit_minutes`. Always answers `200`; an unavailable engine is reported as `ready: false` plus `error` |
| `GET` | `/api/heartbeat` | Page heartbeat; drives the idle auto-exit |
| `POST` | `/api/score` | JSON body: `{"text": "..."}` or `{"sequences": [...]}`, optional `length_handling` (`auto`/`short`/`long`) and `strict_case`. Returns `results`, `warnings`, `skipped`, `summary`, `histogram`, `elapsed_ms` |
| `POST` | `/api/export` | Same input plus `format: "csv"`; returns a `text/csv; charset=utf-8` attachment with a UTF-8 BOM |
| `POST` | `/api/shutdown` | Gracefully stops the local service and releases the port |

Request bodies are capped at 8 MB, a batch at 20 000 sequences and a sequence at 4 000 residues — guards
this implementation adds (the original had none). Unknown `/api/*` paths return `404`; malformed input
returns `400`; an unavailable engine returns `503`.

## The bilingual UI

The web UI ships a language switch — a `中文 / EN` segmented control in the top bar.

- On a first visit the language follows the browser (`navigator.language`: `zh*` ⇒ Chinese, anything else ⇒
  English).
- The user's choice is persisted in `localStorage` and restored on later visits.
- Switching language re-renders **every** string live, including dynamic ones: warnings (both the ones the
  front end generates and the per-sequence notices returned by the engine), toasts, error banners, table
  headers, summary labels, empty states, the input placeholder and `aria-label`s, and `document.title`.
  The `<html lang>` attribute is updated as well.
- No page reload is needed.
- `?lang=zh` / `?lang=en` on the URL forces the language for that visit only (it is not written to
  `localStorage`). Handy for sharing a link or for browser-automation runs.
- The engine is bilingual too: the front end sends `lang` in the `/api/score` and `/api/export` request
  bodies (`zh` / `en`, default `zh`), and `GET /api/status` follows the `Accept-Language` header, so server
  notices are never a mix of languages. See [`pr_engine/i18n.py`](pr_engine/i18n.py).

Bilingual coverage stops deliberately at the **machine-readable data contract**: the exported CSV keeps the
fixed header row `rank,id,sequence,length,score,model` and the fixed filename `peptideranker_scores.csv`
regardless of interface language. A data file's schema should not change with the UI language — that would
break every downstream script. Only human-readable UI text is translated.

## Scoring semantics

- **Alphabet:** `ACDEFGHIKLMNPQRSTVWYX` — 21 letters. `X` is the 21st, real channel (unknown residue,
  with its own weights). `B/J/O/U/Z` are **not** in the alphabet and have no channel of their own.
- **Model selection:** length `<= 20` residues ⇒ `Models_Short`; length `> 20` ⇒ `Models_Long`. This matches
  `PeptideRanker.pl` exactly, and the length is counted in characters (including any skipped characters),
  not in valid residues.
- **Ensemble:** each group holds 15 sub-models. Every sub-model is run forward separately, the 15 output
  vectors are averaged **element-wise** (arithmetic mean), and the `argmax` of the mean vector gives the
  predicted class.
- **Score:** the score is **component index 1** of that mean vector — the positive-class probability.
  This matches the original: `MModel::predict` writes the averaged vector into `Sequence+264`, `main` prints
  it as text into `<dataset>.predictions`, and `PeptideRanker.pl` skips the header lines and `split(/ /)`s
  the remaining fields, taking `$foo[1]`, i.e. `acc[1]`.
- **Range:** `0..1`; the larger, the more likely the peptide is bioactive. Every sub-model's output is a
  softmax-normalised vector, so the averaged vector still sums to 1.

The semantics above come from disassembling `MModel::predict`, `NNto1::Feed`, `NNto1::F1_FE`,
`Sequence::generate_profile` and `Layer::*`. Each claim is backed by a disassembly line number in
[`pr_engine/reference/FORMAT.md`](pr_engine/reference/FORMAT.md), which also records the `.model` file
format, the forward formulas, the numeric constants read out of `.rodata`, and the remaining uncertainties.

## The 0.5 threshold is a convention, not a branch

> ⚠️ **There is no `0.5` branch anywhere in the binary.** The original prediction path only computes an
> `argmax`; `0.5` is a presentation convention used by the paper and by the web server. This application
> uses it as a UI marker for "possibly bioactive" (the value is readable from the `threshold` field of
> `/api/status`).

`--threshold` on the CLI and the `≥0.5 / <0.5` filters in the UI are therefore display-side conveniences
only; they never change a score.

## Intentional differences from the original

For non-standard input the original's behaviour is really a latent bug: its character lookup table is
indexed **without a range check**, so an illegal residue leaves that profile column empty, the
normalisation then computes `0/0`, and **the score for the whole sequence becomes `NaN`**. This
implementation fixes those cases by default — and says so every time, **never silently**:

| Difference | Original behaviour | Default behaviour here | How to get the original behaviour back |
| --- | --- | --- | --- |
| Lowercase input | Out-of-range table lookup → `0/0` → **NaN** (i.e. no result) | Treated as the corresponding uppercase residue; `rppgfspfr` → 0.9558 | CLI `--strict-case`; HTTP `"strict_case": true` |
| Ambiguous residues `B/J/O/U/Z` | Also `0/0` → **NaN** | Mapped onto the `X` channel (a genuine ambiguous-residue channel, more useful than rejecting the whole sequence) | Same as above |
| Digits/punctuation (e.g. `ILP1LS`) | Also `0/0` → **NaN** | Reported as an error and skipped, **the sequence is never silently altered** | None (intentionally stricter) |

Note that `X` and `B/Z` are **not** equivalent: `X` is a real 21st channel with dedicated weights, and an
all-`X` peptide scores 0.9767, whereas `B/J/O/U` are outside the alphabet in the original. That is why this
implementation maps the latter onto the former instead of dropping them.

Everything else is bit-for-bit: the product engine and the reverse-engineered reference agree on all 113
test cases (homopolymers, the 19/20/21/22 length boundary, unknown residues, random sequences) with a
deviation `< 1e-12`.

```bash
python scripts/compare_with_oracle.py
```

## Directory layout

```text
PeptideRanker                     # original 2010 Linux x86-64 ELF, byte-identical (ground-truth reference)
PeptideRanker.pl                  # original Perl wrapper, byte-identical
README                            # original authors' setup/run note, byte-identical
testfile.txt                      # original sample input (15 peptides)
Models_Short/ Models_Long/        # the 30 .model weight files (15 + 15), unmodified
Models_Short.txt Models_Long.txt  # model manifests read by the original binary, unmodified

README.md                         # English technical README (this file)
README.zh-CN.md                   # Chinese technical README
USAGE.md                          # English usage guide
使用说明.md                        # Chinese end-user guide

app/
  server.py                       # zero-dependency HTTP service (stdlib only, binds 127.0.0.1)
  static/
    index.html                    # page markup (inline SVG icons, no CDN, no build step)
    app.js                        # all UI logic: i18n, parsing, rendering, errors, export
    style.css                     # dark theme, no external fonts or imports
    _mock/                        # frontend self-test scaffolding (dev only, safe to delete)

pr_engine/
  __init__.py
  scoring.py                      # the only public scoring API: validation, batching, ranking, stats, export
  reference/
    oracle.py                     # reverse-engineered numerical engine (faithful to the binary, NaN included)
    FORMAT.md                     # .model format + forward formulas + disassembly evidence

pr_cli.py                         # command-line batch scoring
启动网页.bat                       # Windows: double-click launcher (finds Python, installs numpy if missing)
停止程序.bat                       # Windows: fallback stop (HTTP shutdown, then taskkill)

scripts/
  compare_with_oracle.py          # product engine vs reference engine, bit-for-bit (113 cases)
  validate_published.py           # published original-server scores + the 20aa boundary verdict
  validate_against_original.py    # simpler entry point over the same truth .tsv
  detect_table_shift.py           # tell data-quality problems apart from genuine algorithmic deviation
  triage_reference_rows.py        # triage dirty truth rows (three-letter codes, protein names)
  check_distribution.py           # distribution sanity: random peptides vs known actives
  selftest.py                     # service layer end-to-end (HTTP / parsing / stats / export)
  verify_frontend_integration.py  # frontend against the real backend (44 checks)
  final_acceptance.py             # final acceptance run (41 checks), archives _re/acceptance_report.txt
  check_shutdown.py               # verifies the three shutdown paths
  check_delivery.py               # verifies the Windows launcher on a recipient machine
  run_original.sh                 # run the original binary under Linux/Docker to produce golden output
  Dockerfile.original             # image used by run_original.sh
  run_server_with_stub.py         # start the server against a stub engine (development)

_re/                              # reverse-engineering workspace: hand-written x86-64 disassembler,
                                  # disassembly dumps, reference score tables, acceptance report
                                  # (all of it is safe to delete; none of it is needed to score)
```

A minimal distributable copy needs only seven entries (about 2 MB): `启动网页.bat`, `app/`, `pr_engine/`,
`Models_Short/`, `Models_Long/`, `Models_Short.txt`, `Models_Long.txt`. `_re/`, `scripts/` and
`app/static/_mock/` can all be deleted without affecting scoring.

## Supported input formats

All three entry points (web paste, file upload, CLI) share a single parser:

| Input shape | Example | Result |
| --- | --- | --- |
| Plain sequences, one per line | `ILPILSLIGGLL` | ✅ each line is one sequence |
| FASTA (multi-line sequences) | `>pep1 description` ⏎ `RPPGFSPFR` | ✅ the FASTA header becomes the ID; a sequence may span lines |
| Numbered / bulleted rows | `1  ILPILSLIGGLL` | ✅ the prefix is stripped only when the remainder is still a valid sequence |
| Labelled rows | `seq3: RPPGFSPFR` | ✅ |
| CSV/TSV with a header | `id,sequence,note` ⏎ `p1,RPPGFSPFR,x` | ✅ the sequence column is located by header name; the first column becomes the ID |
| CSV/TSV without a header | `p1,RPPGFSPFR` | ✅ the column that looks like a sequence is picked automatically |
| Header columns in any order | `note,peptide,score` | ✅ located by column name |

Rows containing illegal characters (such as `ILP1LS`) **are always reported and skipped** — characters are
never silently deleted and the sequence is never scored as if it were valid.

## Reproducible verification

This is the most important part of the repository, and the reason the original binary is shipped at all.
Every number below was produced by the scripts named next to it, from the files in this repository, offline.

| Check | Result | Reproduce with |
| --- | --- | --- |
| `.model` parsing | **30/30 files parsed, all consumed to EOF, zero leftover bytes** | `_re/probe_parse.py`, `_re/verify_oracle.py` |
| Product engine vs reverse-engineered reference implementation | **113 cases bit-identical** (deviation `< 1e-12`): homopolymers, the 19/20/21/22 boundary, unknown residues, random sequences | `python scripts/compare_with_oracle.py` |
| vs the original public server's published outputs | **729 rows → 673 within ±0.01 (92.3%), 628 bit-identical (86.1%), median deviation 0.000000** | `python scripts/final_acceptance.py` (section H); `python scripts/validate_published.py` and `python scripts/validate_against_original.py` print the same comparison over the 679 published rows |
| vs the authors' paper Figure S3 | **13/15 within ±0.01 and 15/15 within ±0.02 (max deviation 0.018)** | `python scripts/validate_published.py` (the 15 Figure S3 rows are part of its truth set); the raw values with per-row source URLs are listed in `_re/reference_scores.md` §2.1 |
| 20-residue model-switch boundary | **11 published 20aa probes all match the Short model bit-for-bit (Δ = 0.0000), none match the Long model ⇒ confirms `<=20 → Short`** | `python scripts/validate_published.py` (boundary section); `python scripts/final_acceptance.py` (section I) |
| Distribution sanity | Random 8/12/15/20/25/35/50-mers, 200 each: mean 0.35–0.49, share `≥0.5` 31%–46%; bradykinin `RPPGFSPFR` 0.9558 | `python scripts/check_distribution.py` |
| Frontend integration | **44/44 checks pass** | `python scripts/verify_frontend_integration.py` |
| Final acceptance | **41/41 checks pass** (report archived to `_re/acceptance_report.txt`) | `python scripts/final_acceptance.py` |
| Service layer | All checks pass | `python scripts/selftest.py` |
| Shutdown paths | 18/18 checks pass across the three exit routes | `python scripts/check_shutdown.py` |
| Windows launcher on a recipient machine | 11/11 checks pass (missing Python, Microsoft Store placeholder, incomplete unpack) | `python scripts/check_delivery.py` |

A note on the word "bit-identical": `scripts/final_acceptance.py` counts a row as an exact match when
`|Δ| ≤ 5e-5`, i.e. identical at the precision the published values are quoted at. The 729-row truth set is
made up of `_re/reference_scores.tsv` (679 rows) plus `_re/reference_scores_boundary.tsv` (50 boundary
probes).

### Where the truth values come from

- `_re/reference_scores.tsv` — 679 rows, **all of them outputs of the original
  `distilldeep.ucd.ie/PeptideRanker` web server**, extracted row by row from Europe PMC full-text XML, each
  row carrying a verifiable source URL. 15 of the rows are the authors' paper Figure S3; 664 come from
  third-party papers that report original-server scores.
- `_re/reference_scores_boundary.tsv` — 50 probes of length 17–23, including the 20aa boundary probes.
- `_re/reference_scores.md` records the collection criteria, the per-row sources, and the rows that were
  deliberately excluded (mixing PeptideRanker scores with BIOPEP `FRS` scores, or unverifiable sources).

### How the original binary was reproduced

The reverse-engineering evidence itself is in the repository: `_re/disasm.py` is an x86-64 disassembler
written for this project (the machine had neither `objdump` nor `capstone`), and
`pr_engine/reference/FORMAT.md` quotes a disassembly line number for every claim about the file format and
the forward pass.

To generate new golden output from the original binary in an isolated Linux container:

```bash
# Windows cmd
docker build -f scripts/Dockerfile.original -t peptideranker-original .
docker run --rm -v "%cd%:/w" -w /w peptideranker-original \
    bash scripts/run_original.sh testfile.txt > _re/golden_original.txt

# Linux/macOS
docker build -f scripts/Dockerfile.original -t peptideranker-original .
docker run --rm -v "$(pwd):/w" -w /w peptideranker-original \
    bash scripts/run_original.sh testfile.txt > _re/golden_original.txt
```

Then compare:

```bash
python scripts/validate_against_original.py                  # comparison against published/original scores, ±0.01 by default
python scripts/validate_against_original.py --tolerance 0.001
python scripts/compare_with_oracle.py                        # product engine vs reference implementation, bit-for-bit
python scripts/validate_published.py                         # all published truth rows + the 20aa boundary verdict
python scripts/detect_table_shift.py                         # tell data-quality problems from real algorithmic deviation
python scripts/triage_reference_rows.py                      # triage dirty truth rows
python scripts/check_distribution.py                         # distribution sanity
python scripts/final_acceptance.py                           # 41-item acceptance run
python scripts/selftest.py                                   # service layer
python scripts/verify_frontend_integration.py                # frontend + real backend
```

## Honest limitations

**Where the ~7.8% deviation comes from.** The 673/729 in-tolerance figure leaves 56 rows outside ±0.01. They
can be located on the data side, and they fall into three groups (`scripts/detect_table_shift.py`,
`scripts/triage_reference_rows.py`, and the source notes in `_re/reference_scores.md`):

1. The paper's Figure S3 is a **screenshot showing only 2 decimals**, and that screenshot corresponds to a
   **later rebuilt web server**, which differs from the 2010 binary in our hands by roughly ±0.02.
2. A few literature tables **concatenated row labels with the sequence** (e.g. `ACEI` + `DPPIV` + `I` →
   `ACEIDPPIVI`). The reported score actually belongs to `DPPIVI`, not to the concatenated string.
3. **Low-complexity / repeat sequences deviate more** than average.

**`testfile.txt` has no external ground truth.** The 15 sequences in the original sample file could not be
found with scores anywhere in the literature — a verbatim search across 250 open-access full texts returned
0 hits. They are therefore used to demonstrate that the end-to-end pipeline runs and that the output format
matches the original script, **not** for numerical equivalence. This is stated rather than papered over:
`_re/reference_scores.md` §6 lists the per-sequence search result.

**Unresolved uncertainties are listed, not hidden.** `pr_engine/reference/FORMAT.md` §10–§11 records them,
including:

- The original's `.flatblast` alignment path is **not supported**. Every input in this repository takes the
  no-alignment path, but a `<sequence name>.flatblast` file in the working directory would change the
  original's result.
- Some header fields of `MModel`/`NNto1` are read but never used in the forward pass; their meaning is
  unknown. They are parsed faithfully and otherwise ignored.
- Printable ASCII characters outside `A`–`Z` hit out-of-range reads in the original with deterministic but
  unintuitive results; bytes outside `0x20..0x7E` are **undefined behaviour** there. This implementation
  skips them and the product layer rejects them.
- Empty input: the original returns one fixed score (`0.4531538853`) for any zero-length sequence; the
  product layer rejects empty input instead.
- A defensive `85.0` overflow branch exists in `Layer_soft::forward`, but it is **unreachable with the
  shipped weights** (the largest possible pre-activation is `max(|bias| + Σ|W|) = 13.509229`), so scores are
  always genuine softmax values and never `1e-4`/`0.9999` placeholders.
- The original's `0.5` threshold, and the "expected class" label that `PeptideRanker.pl` writes into
  `peptide.dataset`, are bookkeeping conventions of the published pipeline — do not derive the score from
  `acc[0]` because of them.

## Environment requirements

- **Python 3.9+** with **NumPy**. `启动网页.bat` attempts to install `numpy` automatically when it is
  missing (that one step needs a network connection; everything else works offline).
- No network, no Perl, no Linux, no Docker, no build step, no CDN, no external fonts.
- The service binds **only to `127.0.0.1`** — it is never exposed to the network. Each machine runs its own
  copy; several people should not share one running instance.
- `启动网页.bat` and `停止程序.bat` are Windows-only double-click launchers. On Linux/macOS use
  `python app/server.py --open`.
- The `.bat` files must stay **GBK-encoded with CRLF line endings**, otherwise `cmd` mangles the commands.
  `scripts/check_delivery.py` verifies the launcher behaviour, including the missing-Python path and the
  Microsoft Store `python` placeholder.

## Attribution, third-party notice and license

**New code — MIT.** The new re-implementation in this repository (the Python engine under `pr_engine/`, the
web UI under `app/static/`, `app/server.py`, `pr_cli.py` and the scripts under `scripts/`) is released under
the **MIT License**. A `LICENSE` file is present at the repository root.

**Third-party artifacts — not covered by that license.** The following files are the original authors'
work. They are redistributed here **unmodified**, solely so that the numerical verification in this
repository can be reproduced, and they remain the property of their original authors
(University College Dublin / Shields lab):

- the 2010 Linux ELF binary `PeptideRanker`;
- the `PeptideRanker.pl` wrapper;
- the 30 `.model` weight files under `Models_Short/` and `Models_Long/`;
- the model manifests `Models_Short.txt` / `Models_Long.txt`;
- the sample input `testfile.txt`;
- the original `README` file from the original distribution.

**The MIT license does not cover those artifacts**, and no license is claimed for them here. Anyone reusing
them must respect the original authors' own terms.

The "unmodified" claim is checkable: `scripts/final_acceptance.py` (section G) asserts the byte sizes of the
original artifacts against their recorded values — `PeptideRanker` 85296, `PeptideRanker.pl` 1266, `README`
415, `testfile.txt` 385, `Models_Short.txt` 603, `Models_Long.txt` 588 bytes — and that all 30 `.model`
files are present.

## Citation

Original method and data:

- Mooney C, Haslam NJ, Pollastri G, Shields DC.
  *Towards the Improved Discovery and Design of Functional Peptides: Common Features of Diverse Classes
  Permit Generalized Prediction of Bioactivity.*
  PLoS ONE 7(10): e45012, 2012.
  <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0045012>
- The original PeptideRanker web server hosted at University College Dublin is the source of the published
  scores collected in `_re/reference_scores.tsv`; per-row source URLs are recorded alongside the data in
  `_re/reference_scores.md`.

If you use this re-implementation in academic work, please cite the original paper above.
