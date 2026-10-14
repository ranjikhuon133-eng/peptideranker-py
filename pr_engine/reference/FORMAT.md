# PeptideRanker `.model` 文件格式 与 前向公式（逐条反汇编证据）

本文档描述 **2010 年 Linux x86-64 ELF `PeptideRanker`**（GCC 4.4.3，无调试信息但有完整
`.symtab`）如何读取 `Models_Short/` `Models_Long/` 下的 30 个 `.model` 文件、以及如何把一条
肽序列算成一个 0..1 的分数。所有结论都给出**反汇编行号**，可逐条复核。

## 0. 证据来源与引用约定

* 二进制：`PeptideRanker`（85296 字节，ELF64 x86-64）。
* 反汇编器：`_re/disasm.py`（本机无 objdump/capstone，为该项目手写）。
  * **2026-10-12 已修复 4 处解码错误**（修好后 `<bytes>`/`err`/`db 0x` 全为 0）：
    1. REX.W 位从未被解码（`rex[3]` 里放的其实是 X），导致 `movabs r64, imm64` 只吃 6 字节 → 全线错位；
    2. SIB 的 "无 index" 判定用了 REX.R 而不是 REX.X，导致 `[rax+r12*1]` 被印成 `[rax]`；
    3. `0F 39/01/29/…` 这一族 **r/m 形式**的 ALU 指令（`cmp r/m, r` 等）操作数顺序被印反，
       典型后果是把 `cmp eax, r12d` 印成 `cmp r12d, eax`，**循环边界会读反**；
    4. `F6/F7` 组的 `test r/m, imm` 没有吃 imm，导致 `test r10b, 0x0f` 之后的 `jne` 被拆错。
    另外补登记了 `66 0F 16/17`(movhpd)、`66 0F 28/29`(movapd)、`66 0F 7C/7D`(haddpd/hsubpd)、
    `66/F2/F3 0F C2`(cmp*pd/ss/sd)、`F3 0F E6`(cvtdq2pd) 等操作码。
  * 输出：`_re/dis_layer.txt`（47 个含 "Layer" 的符号）、`_re/dis_all.txt`（`.text` 全部 133 个符号）。
* 外部符号：`_re/elfsym.py` 解析 `.rela.plt` 得到 PLT 名，例如
  `0x401980 = _ZNSirsERi`（`istream::operator>>(int&)`）、
  `0x4018d0 = _ZNSi10_M_extractIdEERSiRT_`（`>>(double&)`）、
  `0x401ab0 = operator>><char>(istream&, char&)`、
  `0x401940 = operator>><char>(istream&, char*)`、
  `0x4017d0 = exp`、`0x4017f0 = tanh`、`0x401a50 = operator new`、`0x401820 = operator new[]`。
* 行号写法：`dis_all.txt:8271` 表示 `_re/dis_all.txt` 第 8271 行（该函数的 `### 符号 @0xVA` 标题行）。

---

## 1. 总体调用链

```
main @0x40d490                       dis_all.txt:12668
 └─ ifstream(Models_Short.txt / Models_Long.txt)          (main 0x40d63b 处 filebuf::open)
 └─ new MModel(istream&) @0x406660   dis_all.txt:5163      ← 读模型清单 + 每个 .model
 └─ ifstream(argv[2] = peptide.dataset)  → 手工解析成 Sequence[]
 └─ evaluate(MModel&, DataSet&, char*, char*) @0x40d360    dis_all.txt:12578
      └─ for each Sequence: MModel::predict(seq, argv[3]) @0x407000   dis_all.txt:5732
           └─ Sequence::generate_profile(flag, 0) @0x407630           dis_all.txt:6092
           └─ for i in 0..N-1:  NNto1::predict(B88[i], profile, len) @0x409860 → jmp Feed @0x409570
                 └─ NNto1::F1_FE(profile, p, len) @0x4081e0  (每个位点一次)
                 └─ NNt::forward @0x40be80
                 └─ NN::forward  @0x40c920
```

最终分数：`main` 把 `Sequence+264[1]` 写进 `<dataset>.predictions` 的第 6 行，
`PeptideRanker.pl` 第 41–49 行 `shift` 5 行后 `split` 取 `$foo[1]`。
→ **分数 = 15 个子模型第二输出单元的平均值**（见 §8.3）。

---

## 2. 数值读法：**文本流 `>>`，不是二进制 `read()`**

`.model` 文件是**纯文本**，用 C++ `operator>>` 逐个提取。证据：

* `Layer::read` @0x403d50 (`dis_layer.txt:2151`)：`lea rsi,[r12+12]; call 0x401980`
  → `0x401980` 是 `_ZNSirsERi`，即 **格式化文本提取**，不是 `read()`/`fread`。
* `Layer::read` @0x403e33：`call 0x4018d0` → `istream::_M_extract<double>`（文本读 double）。
* 全程没有任何 `read(2)`/`fread`/`filebuf::sgetn` 调用（PLT 表里只有 `__sprintf_chk`、
  `__strcpy_chk`、`operator>>` 系列）。
* 文件内容确认为十进制文本，例如
  `Models_Short/fold0_v0/trained--20.model` 前 120 字节：
  `"21 2 5 10\n5 5 0 1\n1.5 \n21 2 5 10 1\n5 5 0\n2 5 1 5 1 1 1\n2\n0\n5\n1 1 1 1 1 \n0.831717 …"`

**注意**：`>>` 对 int 与 double 的分词方式不同（不需要分隔符）。例如文本 `1.5` 若被当作
`int` 读会得到 `1` 且残留 `.5`。本项目的 30 个文件用「按空白切分」也能得到同样结果，
但 `pr_engine/reference/oracle.py` 里实现了与 C++ 等价的取词器（`CxxStream`）以策万全。

---

## 3. `.model` 文件格式

### 3.1 总览（三段）

```
[0] MModel 头部      : 8 个 int  + (int#2 - 1) 个 double
[1] NNto1 头部       : 8 个 int
[2] NN   (内部网络)  : 7 个 int  + Layer + Layer
[3] NNt  (逐位点网)  : 7 个 int  + Layer + Layer
```

`.model` **不是** `Layer::write`/`NNto1::write` 的输出（那两者的换行位置是 5+3 个 int，
实测文件是 4+4；`Layer::write` 会写 `length\ndim_in\ndim_out\n`，实测文件是 `21 2 5 10\n`）。
它由训练程序写出，读取顺序完全由读端代码决定。

### 3.2 MModel 头部：8 个 int + `k` 个 double

`MModel::MModel(istream&)` @0x406660 (`dis_all.txt:5163`)：

| 文件顺序 | 写入字段 | 证据 |
|---|---|---|
| 1 | `B8[i]`  | 0x40681f–0x40683e（`add rsi,[rbx+8]` → `call 0x401980`） |
| 2 | `B16[i]` | 0x406843 |
| 3 | `B24[i]` | 0x40684e |
| 4 | `B32[i]` | 0x406859 |
| 5 | `B48[i]` | 0x406867 |
| 6 | `B56[i]` | 0x406888 |
| 7 | `B64[i]` | 0x406893 |
| 8 | `B40[i]` | 0x40689e |

随后读 double：

```
0x4068a9: mov rax,[rbx+16]        ; 个数取自 B16[i]
0x4068b9: movsxd rdi,[rax+r13*1]  ; rdi = B16[i]
0x4068c1: call 0x401820           ; new double[B16[i]]
0x4068ce: cmp [rax+r13*1], 0x1    ; if (B16[i] <= 1) 跳过
0x4068d5: xor ebp,ebp  / 0x4068d7: xor r12d,r12d
0x4068e0: <读 double 到 B72[i][rbp]>
0x4068f7: add r12d,0x1
0x4068ff: mov eax,[rax+r13*1]
0x406903: sub eax,0x1
0x406906: cmp eax,r12d            ; 注意：0x39 是 cmp r/m,r，操作数顺序是 eax - r12d
0x406909: jg 0x4068e0             ; while (B16[i]-1 > r12d)
```

→ **实际只读 `B16[i] - 1` 个 double**（`B16[i] >= 2` 时；`<= 1` 时一个都不读）。
这是最容易踩的坑：按 `B16[i]` 个去读会导致后面全部错位。

实测（fold0_v0）：`B8..B40 = (21, 2, 5, 10, 5, 5, 0, 1)`，`B16[0] = 2` → 只读 **1** 个 double = `1.5`。

**这 8 个字段对前向计算没有作用**（`MModel::predict` 只用了 `B16[0]`，见 §8）。它们是
MModel 自己的训练/统计用数组（`+96/+104/+128/+136/+152/+160/+168`…）。

### 3.3 NNto1 头部：8 个 int

`NNto1::NNto1(istream&)` @0x409870 (`dis_all.txt:8474`)：

| 顺序 | 偏移 | 实测值(Short v0) | 语义（由使用点推出） |
|---|---|---|---|
| 1 | `+0`  | 21 | 每个位点的特征维数（字母表大小） |
| 2 | `+4`  | 2  | 输出单元个数（`Feed` 0x4097b2 用它复制输出） |
| 3 | `+8`  | 5  | 未在前向中使用 |
| 4 | `+12` | 10 | **窗口半宽 W**（`F1_FE` 0x4081f1） |
| 5 | `+16` | 1  | 是否把 profile 在位置上取平均后送 NN（`Feed` 0x409683） |
| 6 | `+20` | 5  | NNt 每个位点的输出维数 = 累加器长度 |
| 7 | `+24` | 5  | 未在前向中使用 |
| 8 | `+28` | 0  | 未在前向中使用 |

证据：0x409880–0x4098d4 依次 `lea rsi,[rbx+0/+4/+8/+12/+16/+20/+24/+28]` + `call 0x401980`。

### 3.4 NN / NNt 头部：7 个 int + 2 个 Layer

`NN::NN(istream&)` @0x40cea0 (`dis_all.txt:12245`) 与 `NNt::NNt(istream&)` @0x40c400
(`dis_all.txt:11462`) 的读取顺序**完全相同**（0x40cea5–0x40cf00 / 0x40c405–0x40c460）：

| 顺序 | 偏移 |
|---|---|
| 1 | `+24` |
| 2 | `+20` |
| 3 | `+8`  |
| 4 | `+12` |
| 5 | `+48` |
| 6 | `+52` |
| 7 | `+56` |

然后各 new 两个 `Layer`（0x88 字节）并调用 `Layer::Layer(istream&)`：
* NN：第一个 Layer 存 `NN+72`，vtable 被改写为 **0x40e1b0 = Layer_soft**（0x40cf20）；
  第二个存 `NN+80`，vtable **0x40e130 = Layer_tanh**（0x40cf59）。
* NNt：两个 Layer 都存进 `NNt+72` / `NNt+80`，vtable 均为 **0x40e130 = Layer_tanh**
  （0x40c480 / 0x40c4b9）。

代码里把**文件中先出现的那个 Layer 记为 L1（对象偏移 +72）**，后出现的记为 L2（+80）。

vtable 判定依据（读 `.rodata`）：
`0x40e1b0 → {0x405cb0, 0x406200, 0x405fb0, 0x405890}` = `Layer_soft::forward(int*)`,
`(double*)`, `(int*,double*)`, `(double*,double*)`；
`0x40e130 → {0x405780, 0x405620, 0x404e00, 0x4053e0}` = `Layer_tanh::forward(int*)`,
`(double*)`, `(int*,double*)`, `(double*,double*)`。

### 3.5 Layer：3 个 int + `dim_in+dim_out` 个 int + 权重 + 偏置

`Layer::Layer(istream&)` @0x404130 (`dis_layer.txt:2416`) 与 `Layer::read(istream&)`
@0x403d50 (`dis_layer.txt:2151`) 语义一致：

```
length  ← >>int     0x40413c
dim_in  ← >>int     0x404157
dim_out ← >>int     0x404163
dims[0 .. dim_in+dim_out-1] ← >>int × (dim_in+dim_out)      0x4041e9–0x4041bb
for i in 0 .. length-1:                                     0x4041c7 起
    for j in 0 .. dim_in+dim_out-1:                         0x404208
        for k in 0 .. dims[j]-1:                            0x404220
            W[i][j][k] ← >>double
    bias[i] ← >>double                                      0x404265–0x40423e
```

* `length` 进了 `Layer+8`；`dim_in` → `Layer+12`；`dim_out` → `Layer+16`；
  `dims[]` 是 `int32` 数组，指针存在 `Layer+24`（0x40418a）。
* 权重指针在 `Layer+72`（0x4042 区、`Layer::alloc` 0x403f93–0x403fa2）；
  偏置数组在 `Layer+96`（0x404269 `add rsi,[rbx+96]`）。
* `Layer+132` = `sum(dims[0..dim_in-1])`（`Layer::read` 0x403eba–0x403ed6）。

**结论（第 5 项要求）**：
* 文件里每一"行"= 一个输出单元 `i`（`length` 行）。
* 行内顺序 = `W[i][0][0..dims[0]-1]`, `W[i][1][0..]`, …, 最后是 `bias[i]`。
* 也就是 **`W[i][j][k]`**（`i` 最外层、`j` 次之、`k` 最内），`bias` 单独一个数组、
  按 `i` 递增顺序紧跟在第 `i` 行权重之后。
* `Layer+72` 的类型是"指针的指针的数组"：`Layer+72[i]` 是 `double**`，
  `Layer+72[i][j]` 是长度 `dims[j]` 的 `double*`（`Layer::alloc` @0x403ef0，
  `dis_layer.txt:2264`，0x404010–0x404101 逐层 new）。

### 3.6 实测：30 个文件共有 6 种结构（不是"15 个结构相同"）

由 `_re/verify_oracle.py` 自动扫描得到（`ints = [NNto1+0,+4,+8,+12,+16,+20,+24,+28]`）：

**Models_Short（`+12 = 10` → 窗口 21 个位点）**

| 文件 | NNto1 ints | NN.L1 (soft) | NN.L2 (tanh) | NNt.L1 (tanh) | NNt.L2 (tanh) |
|---|---|---|---|---|---|
| `*_v0` | `[21,2,5,10,1,5,5,0]`  | (2,0,5,`[1]×5`)  | (5,1,5,`[21,1,1,1,1,1]`)  | (5,0,5,`[1]×5`)  | (5,23,0,`[21]×21+[1,1]`) |
| `*_v1` | `[21,2,6,10,1,6,6,0]`  | (2,0,6,`[1]×6`)  | (6,1,6,`[21,1]×…`)         | (6,0,6,`[1]×6`)  | (6,23,0,`[21]×21+[1,1]`) |
| `*_v2` | `[21,2,7,10,1,7,7,0]`  | (2,0,7,`[1]×7`)  | (7,1,7,`[21,1]×…`)         | (7,0,7,`[1]×7`)  | (7,23,0,`[21]×21+[1,1]`) |

**Models_Long（`+12 = 20` → 窗口 41 个位点，`+16 = 0` → 不做平均组成那一路）**

| 文件 | NNto1 ints | NN.L1 (soft) | NN.L2 (tanh) | NNt.L1 (tanh) | NNt.L2 (tanh) |
|---|---|---|---|---|---|
| `*_v0` | `[21,2,10,20,0,10,10,0]` | (2,0,10,`[1]×10`) | (10,**0**,10,`[1]×10`) | (10,0,10,`[1]×10`) | (10,43,0,`[21]×41+[1,1]`) |
| `*_v1` | `[21,2,9,20,0,9,9,0]`   | (2,0,9,`[1]×9`)   | (9,**0**,9,`[1]×9`)     | (9,0,9,`[1]×9`)   | (9,43,0,`[21]×41+[1,1]`) |
| `*_v2` | `[21,2,11,20,0,11,11,0]`| (2,0,11,`[1]×11`) | (11,**0**,11,`[1]×11`)  | (11,0,11,`[1]×11`)| (11,43,0,`[21]×41+[1,1]`) |

（`(length, dim_in, dim_out, dims)`；`[x]×n` 表示 n 个 x。）
NN/NNt 的 7 个 int 在实测中恒为 `[+24]=hidden`, `[+20]=1`, `[+8]=1`, `[+12]=1`, `[+48]=1`, `[+52]=0/1`, `[+56]=1`
——它们不参与前向（`NN::forward`/`NNt::forward` 只摸 `+72`/`+80`）。

> **重要**：Long 模型的 `dims` 里没有 `21`，**全局组成那一路被关掉**（`+16=0`），
> NN.L2 的 `dim_in=0` 也不再读 `in`。任何"抄死 21 维输入"的实现都会在长肽上算错。

---

## 4. `Layer::forward(double* in, double* out)` @0x401d60

`dis_layer.txt:2` / `dis_all.txt:135`。伪代码（**去掉了向量化，语义等价**）：

```
for i in 0 .. length-1:
    acc = bias[i]
    # 第 1 段：j < dim_in，从 in 取
    off = 0
    for j in 0 .. dim_in-1:
        for k in 0 .. dims[j]-1:
            acc += W[i][j][k] * in[off + k]
            buf[off + k] = in[off + k]          # 0x405998–0x40599b 的拷贝
        off += dims[j]
    # 第 2 段：j >= dim_in，从 out 取，偏移从 0 重新开始
    off = 0
    for j in dim_in .. dim_in+dim_out-1:
        for k in 0 .. dims[j]-1:
            acc += W[i][j][k] * out[off + k]
            buf[Layer+132 + off + k] = out[off + k]
        off += dims[j]
    Layer[+40][i] = acc                          # 0x4055c1
    Layer[+32][i] = acc                          # 0x4055c7
```

关键行：
* 累加起点 `xmm0 = [bias + 8i]`：0x401df1（Layer::forward）/ 0x405935（Layer_soft）/
  0x40547b（Layer_tanh）。
* 矩阵乘 `mulsd xmm1,[rdx]` + `addsd xmm0,xmm1`：0x401e6c/0x401e77。
* 第二段用 `Layer+132` 作为写 `buf` 的基址：0x405a0c / 0x401ecc。
* `out` 的偏移在第二段**从 0 重新开始**（`xor r10d,r10d` @0x401ea3 / 0x4059e3）。
* 结果同时写 `Layer+40`（pre-activation，供反向传播）与 `Layer+32`（激活后，供前向）。

`Layer+32/+40/+48/+56/+64` 由 `Layer::alloc` @0x403ef0 分配：`+32/+40/+56` 长度 `length`，
`+48/+64` 长度 `sum(dims)`（0x403f47–0x403f86）。

### 4.1 激活：`Layer_tanh::forward(double*,double*)` @0x4053e0

`dis_layer.txt:3700`。线性部分与 `Layer::forward` 完全相同，之后（0x4055dc–0x405602）：

```
r12 = length*8 ; rbp = Layer+40 ; r13 = Layer+32 ; rbx = 0
loop:
    xmm0 = [rbp+rbx]        ; pre-activation
    call 0x4017f0           ; = tanh(double)  ← libm tanh
    [r13+rbx] = xmm0
    rbx += 8; until rbx == r12
```

→ **`Layer+32[i] = tanh(Layer+40[i])`，双曲正切，直接调用 libm `tanh`**（PLT 0x4017f0）。
不是 sigmoid，也不做缩放（`Layer_tanh::f1` @0x403240 里能读到 `1 - tanh^2` 的导数）。

### 4.2 激活：`Layer_soft::forward(double*,double*)` @0x405890

`dis_layer.txt:4024`。线性部分同上（0x40592b–0x405a96），之后：

```
denom = 0.0                                     # [rsp+32] @0x405ab4
max   = Layer[+40][0]                           # @0x405aa3
flag  = 0                                       # r13d  @0x405aaa
for i in 0..length-1:
    v = Layer[+40][i]
    if v <= 85.0:                               # 0x405adf ucomisd + jbe
        denom += exp(v)                         # 0x405c2b call 0x4017d0 = exp
    else:
        flag = 1                                # 0x405ae9
    if v > max: max = v ; argmax = i            # 0x405aef ja → 0x405ac4

if flag == 0:                                   # 0x405b07
    for i: Layer[+32][i] = exp(Layer[+40][i]) / denom        # 0x405c79–0x405c88
else:                                           # 数值兜底分支
    for i: Layer[+32][i] = 1e-4                              # 0x405b36–0x405bac
    Layer[+32][argmax] = 1.0 - (length-1)*1e-4               # 0x405bbc–0x405bd0
    for i: if 1e-4 > Layer[+32][i]: Layer[+32][i] = 1e-4     # 0x405bf3–0x405c0f
```

数值细节：
* 就是**普通 softmax**，**不减最大值**（因为 85 是 exp 的安全上界：`exp(85)≈8e36`）。
* 阈值常量 `85.0` 在 `.rodata 0x40e338`（0x405aba `movsd xmm2, rip+34934` → 0x405ac2+0x8876）。
* `1e-4` 以立即数形式编码：`movabs 0x3f1a36e2eb1c432d`（0x405b3b / 0x405b96 / 0x405bfa）。
* 兜底分支保证 `Σ_i out[i] = 1.0`（一个 `1-(n-1)ε`，其余 `ε`）。
* `argmax` 用**严格大于**更新，取第一个最大值（`ucomisd; ja`）——与 `np.argmax` 一致。
* `Layer::softmax()` @0x4044f0 是另一支（训练用），**不在前向路径上**。

---

## 5. `NN::forward` / `NNt::forward`：**先 L2 再 L1**

`NN::forward(double*,double*)` @0x40c920 (`dis_all.txt:11834`)，全文 39 字节：

```
40c924: rdi = [rdi+80]        ; L2
40c92b: call [rax+24]         ; L2->forward(rsi=in, rdx=out)
40c92e: rax = this[+80]
40c932: rdi = this[+72]       ; L1
40c937: rsi = [rax+32]        ; in  = L2 的输出 (L2+32)
40c93e: rdx = rsi             ; out = 同一个向量
40c945: jmp [rax+24]          ; L1->forward(L2.out, L2.out)
```

`NNt::forward(double*,double*)` @0x40be80 (`dis_all.txt:11051`) 结构完全一致。

→ 层间衔接**不是**"L1 输出拼 21 维新特征"，而是：
1. `L2` 先跑，它的 `out` 参数是调用者给的缓冲区；`L2` 的 `dim_out` 决定它从 `out` 取多少维。
2. 然后把 **L2 的输出**同时当作 `L1` 的 `in` 和 `out` 再跑 `L1`。
3. `L1` 的 `dim_in` 决定它从 `in`（即 L2 输出）取多少维，`dim_out` 决定从 `out`（同一块内存）再取多少维。
   实测 `L1.dim_in = 0`，所以只从 `out` 取 `dim_out = L2.length` 个数——即"L1 吃掉 L2 的全部输出"。
4. 网络的最终输出 = **L1 的 `Layer+32`**（`NNto1::Feed` 0x4097c7–0x4097ea 从 `[NN+72]+32` 复制）。

---

## 6. `NNto1::Feed(double* in, int dim)` @0x409570

`dis_all.txt:8271`；`NNto1::predict(double*,int)` @0x409860 只是 `jmp 0x409570`（`dis_all.txt:8469`）。

```
0x409590-0x40959c: buf[8192] = 0
0x4095a1-0x4095c0: rbx = new double[NNto1+20] ; memset 0
0x4095c5-0x4095f1: if NNto1+20 > 0: NNto1[+48][0][k] = NNto1[+64][k]   (实测全 0)
0x4095fb-0x40961f: for p = 1 .. dim:  F1_FE(this, in, p, dim)          ← 每步一次
                   （edx = p, ecx = dim；0x40961c cmp ebp,r14d / jge）
0x409680-0x40979a: 横向两段累加（见下）
0x4097a0-0x4097ad: NN::forward(NNto1+32, buf, rbx)
0x4097b2-0x4097ea: for i = 0..NNto1+4-1: NNto1[+72][i] = [NN+72]+32[i]
```

### 6.1 两段累加（0x409680 之后）

由 `r9d = p = 1..dim`、`r10 = 8p` 驱动：

1. **平均组成**（仅当 `NNto1+16 != 0` 且 `NNto1+0 > 0`，0x409680/0x409689）：
   ```
   rax = in + 8*(p * NNto1[+0])          ; 0x409698 imul r11d,esi ; esi = NNto1[+0] = 21
   for k in 0 .. NNto1[+0]-1:
       buf[k] += in[p*21 + k] / dim      ; 0x4096fa/0x4096fe divpd ; 0x409816 标量尾巴
   ```
   → `buf[k] = (1/L) * Σ_{p=1..L} profile[p][k]`，即**整条肽的氨基酸组成**（21 维）。
   `in` 就是 `Sequence+296` 的 profile，第 `p` 行从 `21*p` 开始。

2. **逐位点状态的平均**（仅当 `NNto1+20 > 0`，0x409759）：
   ```
   rcx = NNto1[+48][p]
   for k in 0 .. NNto1[+20]-1:
       rbx[k] += rcx[k] / 30.0           ; 0x409778 divsd xmm0, xmm4
   ```
   `xmm4` 在 0x409658 从 `rip+19856` 装入 → **`.rodata 0x40E3F0 = 30.0`**。

   ⚠ **除数是硬编码常量 30.0，不是序列长度**。所以 `acc[k] = (1/30)·Σ_{p=1..L} state[p][k]`。
   （可能源自训练时把序列补齐到 30，但在发布版里它就是常量。）

> Short 模型 `+16 = 1`，所以两段都做；**Long 模型 `+16 = 0`，第一段被跳过，`buf` 保持全 0**，
> 且 Long 的 `NN.L2.dim_in = 0` 也不再读 `buf`——两处互相印证。

### 6.2 `NNto1::F1_FE(double* in, int p, int dim)` @0x4081e0

`dis_all.txt:6934`。对位点 `p` 构造一条长 `(2W+1)*21 + 2` 的向量（W = `NNto1+12`）：

```
0x4081f1: r11d = -[rdi+12]                       ; -W
0x40821c: r11d += p                              ; q = p - W
0x40826a: r8 = in + 8*21*(p-W)                   ; 窗口第 0 个位点的 profile 行
0x408280-0x408358: 循环 t = 0..2W:               ; 21(Short)/41(Long) 次
     q = p - W + t
     if (1 <= q <= dim):  把 in[21*q .. 21*q+20] 拷到 local[21*t .. 21*t+20]
     else:                local[21*t .. 21*t+20] = 0
0x40835e-0x40839e: local[21*(2W+1)]   = p * 0.001        ; 0x40836a/0x408375
                   local[21*(2W+1)+1] = (dim - p) * 0.001
0x4083a4: tmp = new double[8]                            ; edi = 0x40
0x4083b9: NNt::forward(NNto1+40, local, tmp)             ; 0x40be80
0x4083c2-0x408402: for i = 0..NNto1+20-1:
                      NNto1[+48][p][i] = [NNt+72]+32[i]
```

* 窗口是 **`[p-W, p+W]`，步长 1 位点**（不是滑窗 flatten 之外的别的花样）；越界位置补 **0**
  （注意：这里的 `q < 1` 或 `q > dim` 补 0，而 `q = 0` 也被当越界处理）。
* 位置编码常量 `0.001` 在 `.rodata 0x40e3e8`（0x408362 `movsd xmm1, rip+24702` → 0x40836a+0x607e）。
* 每个位点独立跑一次 NNt，结果写进 `NNto1[+48][p]`（`p` 从 1 开始，`[0]` 槽被 §6 开头初始化为 0）。
* 窗口扁平化顺序 = **先 t（位点）后 k（21 维特征）**，即 `local[t*21 + k]`；
  与 `NNt.L2` 的 `dims = [21]×(2W+1) + [1,1]` 逐段对应（0x4082e0 的向量化拷贝同样是 2 个 double 一组）。

---

## 7. `Sequence::generate_profile(char*, int)` @0x407630

`dis_all.txt:6092`。`MModel::predict` 调它时 int 参数 = 0（0x407059 `xor edx,edx`），
于是 `load_alignments(seq, char*, 0)` @0x407240 走
`strcpy(name_buf, Sequence::name)` + `strcat(name_buf, ".flatblast")`（0x407288–0x4072ba，
`.rodata 0x40e370 = ".flatblast"`），即打开 **`<序列名>.flatblast`**。

* 若该文件不存在 → `0x407454: [r12+284] = 0` → 对齐那一支整体跳过（本仓库的输入就是这种情况）。
* 发布版 `PeptideRanker.pl` 传进来的第 4 个参数（`"./"`）只在 int 参数非 0 时才会被当作文件名，
  而 `MModel::predict` 传的 int 恒为 0，**所以那个目录字符串不影响结果**。

无 `.flatblast` 时：

```
0x407665: profile = new double[(L+1)*21]      → Sequence+296 ; memset 0
0x40767a: colsum  = new double[L+1]                           ; memset 0
0x4076e3-0x407743: for i = 1..L:
        r = Sequence[+256][i]                  ; 残基索引数组（1-based！[0] 未初始化）
        if (unsigned)r <= 20:                  ; 0x407705 cmp edi,0x14 / ja  (r = -1 会被 ja 吃掉)
            profile[21*i + r] += 1.0           ; .rodata 0x40e300 = 1.0
            colsum[i]         += 1.0
0x4077ee-0x407b41: for i = 1..L:               ; 逐位点归一化
        s = Σ_{k=0..19} profile[21*i+k]        ; 0x407838 恰好 20 次（cmp eax,0x14）
        old20 = profile[21*i+20]               ; 0x407855
        if s != 0: for j = 0..20: profile[21*i+j] /= s     ; 0x407c10 分支
        profile[21*i+20] = profile[21*i+20] / (s + old20)  ; 0x40788a/0x4078a3
0x407bb0: Sequence+304 = 1                     ; 幂等标志
```

对普通残基（索引 0..19）结果是**逐位点 one-hot**：`profile[i][r_i] = 1`，其余 0；
索引 20（字母表里的 `X`）走 `s == 0` 分支，同样得到 1。
→ `Feed` 第 1 段算出来的 `buf[k]` 就是**氨基酸频率**。

字母表（`.rodata 0x40e570` 字符串，长度 21）：`"ACDEFGHIKLMNPQRSTVWYX"`，即
`A C D E F G H I K L M N P Q R S T V W Y X` → 索引 0..20（注意 **19 = Y，20 = X**）。

`char → 残基索引` 表有两份**内容完全相同**的副本：
* `main` 用的是 **`.rodata 0x40e500`**（`dis_all.txt:12845` 的立即数 `4252928 = 0x40E500`）；
* `load_alignments` 用的是 **`.rodata 0x40e380`**（`dis_all.txt:6042` 的立即数 `4252544 = 0x40E380`）。

26 项内容（下标 = `ch - 'A'`）：

```
A B  C D E F G H I J  K L M  N  O  P  Q  R  S  T  U  V  W  X  Y  Z
0 -1 1 2 3 4 5 6 7 -1 8 9 10 11 -1 12 13 14 15 16 -1 17 18 20 19 -1
```

`generate_profile` 的判断是 `cmp edi,0x14; ja`（**无符号**），所以 `-1` 会被当作 `0xFFFFFFFF` 跳过。
`main` 的读字符循环（0x40d865–0x40d8ab）用 `operator>><char>`，会**跳过所有空白**；
随后 `Sequence+256[1..L]` 存残基索引，`[0]` 从不写入。

`Sequence+256[0]` 从不被写（`main` 0x40d865 起始偏移是 4），残基存在 `[1..L]`。

### 7.1 非 A–Z 字符：原程序会越界读表（本实现按实测值精确复刻）

`main` 只做 `edx = ch - 0x41` 就直接查表，**不检查范围**。于是：
* `ch - 'A' ∈ [0,25]`（即 `A`..`Z`）→ 正常查表；
* 其他可打印字符 → 读 `0x40e500 + 4*(ch-'A')`，地址落在 `0x40e47c .. 0x40e5f8`，
  仍在已加载只读段内（`.rodata` + `.eh_frame_hdr`），因此**结果确定但不直观**：

| 字符 | 表值 | 后果 |
|---|---|---|
| `*` (0x2A) | 0 | 当成 `A` |
| `c` (0x63) | 0 | 当成 `A` |
| `"` `$` `&` `'` `(` `,` `4` `@` `[` `\` | 0 | 当成 `A` |
| `a` (0x61) | 1498895956 | >20，跳过 |
| `b` (0x62) | 88 | >20，跳过 |
| `d`..`z`、`{`..`}` 等 | 各种非 0..20 值 | 跳过 |
| `B J O U Z` | -1 | 无符号比较 >20，跳过 |

`pr_engine/reference/oracle.py` 里的 `CHAR_TO_RESIDUE` 就是从上表逐字节抄出来的，
**没有**做 `upper()`（`upper()` 会错：原程序里 `a` 被跳过，而 `A` 计为 0）。
`0x20..0x7E` 之外的字符（含非 ASCII）在原程序里会读到未映射内存 —— **未定义行为**，
本实现一律按"跳过"处理并在此标注。

---

## 8. `MModel::predict(Sequence*, char*)` @0x407000 与最终分数

`dis_all.txt:5732`。

### 8.1 集成

```
0x40701d-0x407040: acc = new double[N_out]; memset 0
                   N_out = [MModel+16][0]            ; = 2
0x407045-0x40704a: if N <= 0 → 结束
0x407050: 每轮 i:
    0x407059-0x407061: generate_profile(seq, flag, 0)     ; 有 Sequence+304 幂等，实际只跑一次
    0x407066-0x40707c: NNto1::predict(B88[i], seq+296, seq+280)
    0x40708b-0x4070bc: for j in 0..N_out-1:
                           acc[j] += B88[i]->out[j] / (double)N
0x4070c2: r12 += 8 ; 0x4070c6 cmp r14d,[rbp+0] / jg 0x407050
```

→ **`acc[j] = (1/N) · Σ_{i=0..N-1} out_i[j]`**，N = 清单文件第一行的模型个数（15）。
`out_i` = `NNto1+72`，由 §6 的 `NN.L1(Layer_soft)` 给出。

### 8.2 argmax 与回写

```
0x4070d6-0x407113: r8 = Sequence+264
                   for j: Sequence+264[j] = acc[j]
                          if acc[j] > best: best = acc[j]; bestidx = j     ; 初值 best = 0.0
0x40711c: Sequence+272 = bestidx                     ; 预测类别
0x407115: Sequence+276 = 期望类别
```

注意 `best` 初值为 **0.0**（`xorpd xmm1,xmm1` @0x4070e1），所以若所有 `acc[j] <= 0`
则返回 0；正常情况 `acc` 是 softmax 平均、恒 ≥ 0 且和为 1。

### 8.3 最终分数取哪一个

`main` @0x40daf1–0x40db3a 写 `<dataset>.predictions` 的第 6 行：
`"<期望类别> <预测类别>\n"`，第 7 行才是 `"<Sequence+264[0]> <Sequence+264[1]> \n"`。
`PeptideRanker.pl` 第 41–49 行 `shift` 5 行后取 `split(/ /)` 的 `$foo[1]`
→ 命中第 7 行的第 2 个数 → **`Sequence+264[1]` = `acc[1]`**。

因此：**分数 = 15 个子模型"第 2 个输出单元"的算术平均**，取值 ∈ [0,1]
（每个子模型的 softmax 和为 1，平均后仍为 1）。

---

## 9. 数值常量总表（`.rodata`，均按小端 double 读出）

| 地址 | 值 | 用途 | 证据 |
|---|---|---|---|
| 0x40e300 | `1.0`   | `generate_profile` 每个残基的计数增量；softmax 兜底分支的 `+1.0` | 0x4076ea / 0x405bc8 |
| 0x40e338 | `85.0`  | Layer_soft 的 exp 安全阈值 | 0x405aba |
| 0x40e340 | `1e-4`  | 兜底分支的 epsilon | 0x405be1；等值立即数 0x3f1a36e2eb1c432d |
| 0x40e348 | `-1e-4` | `1.0 - (n-1)*ε` 里的 `-ε` | 0x405bc0 |
| 0x40e360 | `(1e-4,1e-4)` | 向量化填充 | 0x405b65 |
| 0x40e3e8 | `0.001` | `F1_FE` 位置编码系数 | 0x408362 |
| 0x40e3f0 | `30.0`  | `NNto1::Feed` 状态平均的除数 | 0x409658 |
| 0x40e380 | int[26] | `char-'A' →` 残基索引（-1 = 非法） | `main` 0x40d89b；`load_alignments` 0x407555 |
| 0x40e570 | `"ACDEFGHIKLMNPQRSTVWYX"` | 字母表 | 0x4076b2 附近字符串引用 |
| 0x40e370 | `".flatblast"` | 对齐文件名后缀 | 0x4072b2 |
| 0x40e4bd | `".predictions"` | 输出文件名后缀 | 0x40d923 |
| 0x40e104 | `"\n"` | 文本分隔 | 0x404c26 等 |
| 0x40e4bb | `" "`  | 文本分隔 | 0x404ca2 等 |

---

## 10. 不确定与假设（如实列出）

1. **`.flatblast` 文件不存在**是本实现的前提。若工作目录下存在 `<序列名>.flatblast`，
   原程序会读入对齐信息并改变 profile（`generate_profile` 0x407753 之后那一大段），
   本实现**不支持**该路径。本仓库的 `testfile.txt` / `PeptideRanker.pl` 流程不会产生该文件。
   *证据*：`load_alignments` 0x4072bf 打开 `<name>.flatblast`，失败则 0x407454 置 `Sequence+284 = 0`。
   *不确定点*：`std::filebuf::open` 在文件不存在时必然返回 NULL（0x4072d4 `test rax,rax; je 0x407454`），
   因此这一步是确定的；但如果目录里**恰好**有同名文件，行为会不同。

2. **`NNto1+8 / +24 / +28`、`MModel` 头部 8 个 int、`arr72` 那 1 个 double 的语义不明**。
   已确认它们**不进入前向**（`Feed`/`F1_FE`/`forward` 中没有任何读取点），
   本实现照读、不使用。

3. **`NNto1::Feed` 里 `NNto1[+48][0]` 槽**被 §6 开头初始化为 `NNto1[+64]`（实测全 0），
   但 `p` 的累加只覆盖 `1..dim`，所以该槽对结果无影响。已如实复刻（无影响）。

4. **`F6/F7` 等已修好，但仍可能有未被本文件覆盖的指令**：`_re/dis_layer.txt` 与
   `_re/dis_all.txt` 现在 `<bytes>`/`err`/`db 0x` 均为 0，说明 `.text` 里 133 个符号全部解码成功；
   但"能解码"不等于"每条都语义正确"，本次已额外核对了所有出现在关键路径上的指令。

5. **字符集边界**：见 §7.1 与 §11.1。`A`..`Z` 之外的字符在原程序里会**越界查表**，
   对可打印 ASCII 是确定值（已逐字节复刻进 `CHAR_TO_RESIDUE`），
   对 `0x20..0x7E` 之外的字符是未定义行为（本实现按"跳过"处理）。
   本实现**不做 `upper()`**，因为那与实测行为不符。
   而任何被跳过的残基会让该 profile 列全 0，进而在归一化时 `0.0/0.0` 产生 **NaN**，
   最终整条分数为 NaN（原程序的潜在 bug，已如实复刻）。

6. **数值等价性未与"真值"比对过**：本机**没有 Docker，也没有已安装的 WSL 发行版**
   （`wsl -l -v` 返回"没有已安装的分发"），因此无法执行原 ELF 取得标准答案。
   目前的自证是：30 个模型全部解析到 EOF（`_re/probe_parse.py`、`_re/verify_oracle.py`）、
   所有子模型输出向量和为 1、`testfile.txt` 15 条分数均落在 [0,1]。
   逐条与公开文献分数比对见 `_re/reference_scores.md`（由 `ref-hunter` 收集）。

7. `Layer::softmax()` @0x4044f0（含 0.0001 常量与 1e-4）是**训练/归一化辅助函数**，
   `Layer_soft::forward` **没有**调用它（0x405890 全程无 `call 0x4044f0`）。不要误用。

---

## 11. 与原程序的差异 / 已知不确定性（产品层需知）

本节是**行为级**差异清单：引擎 `oracle.py` 逐字复刻原程序；而产品层（`pr_engine/scoring.py`、
前端、`pr_cli.py`）出于可用性做了一些**有意的改进**，必须在文档里说清楚，否则用户会以为
"Python 版"和"原版"在边界输入上一致。

### 11.1 小写输入（以及任何非法残基）：原程序输出 **NaN**（已实测确认）

**三步机制**：

1. `main` @0x40d87b–0x40d8a2：`movsx edx,[rsp+319]; sub edx,0x41; mov edx,[rdx*4+0x40e500]`
   —— **无范围检查**。小写字母 `ch-'A' ∈ [32,57]`，于是读到 `0x40e580..0x40e5e4`
   （表外，落在 `.eh_frame_hdr`），实测这些字节全部 `> 20`；`B/J/O/U/Z` 的表值是 `-1`。
2. `generate_profile` @0x407705：`cmp edi,0x14; ja 0x407737`
   —— 无符号比较，`-1` 与 `>20` 都被跳过 → **该位点的整列 21 个值全为 0**
   （位置本身仍占一行，见 §11.2）。
3. 逐位点归一化 @0x4077ee–0x4078ab：
   ```
   407838: addsd xmm0,[rdx]         ; s20 = Σ_{k=0..19} profile[i][k]  (20 次)
   407855: movsd xmm2,[rcx+rdi+160] ; old20 = profile[i][20]
   407848: ucomisd xmm0,[rsp+72]    ; 与 0.0 比较
   40785e: jne 0x407c10             ; s20 != 0 -> 先整体除以 s20
   407864: jp  0x407c10             ; 无序(NaN) -> 同上
   40788a: addsd xmm0,xmm2          ; xmm0 = s20 + old20  = 0 + 0 = 0
   4078a3: divsd xmm1,xmm0          ; xmm1 = 0.0 / 0.0 = **NaN**（无任何保护）
   4078a7: movsd [rdx],xmm1         ; profile[i][20] = NaN
   ```
   这个 NaN 顺 `F1_FE` 的窗口 → `NNt`（tanh）→ `acc` → `NN` → `Layer_soft` 一路传播，
   最终整个分数变成 **NaN**。

**⚠ x86 语义陷阱（本实现专门为此改了写法）**：`Layer_soft::forward` @0x405adf 用
`ucomisd v, 85.0; jbe` 判断是否"没超过 85"。`ucomisd` 遇到 NaN 会置 `CF=ZF=PF=1`，
于是 `jbe` **成立** → NaN 走"累加 `exp`"的那条路（`exp(NaN)=NaN` → 输出 NaN），
**不会**走 85.0 溢出分支。而用高级语言写 `if v <= 85` 时 NaN 得到 `False`，
会走到**错误**的分支。`oracle.py::Layer.forward_softmax` 因此写成
`if vi > 85: big = True else: denom += exp(vi)`，与硬件完全一致
（最大值扫描同样用显式循环 + 严格 `>`，因为 `ucomisd; ja` 对 NaN 不成立）。

**实测**（`_re/verify_oracle.py` 第 8 节）：
```
RPPGFSPFR  0.955813909825      rppgfspfr  nan
aaaaaaaaa  nan                 JJJJJJJJJ  nan
!!!!!!!!!  nan
```
→ 原程序**不支持小写输入**：给的是 `NaN`（不是某个无意义的有限数，也不是"只与长度有关"的常数）。

* **产品层决定（有意差异）**：统一转大写后再打分。这**不只是可用性改进，而是避免 NaN 的必要步骤**。
* 引擎本身**不做 `upper()`**（`CHAR_TO_RESIDUE` 忠实复刻越界查表），大小写归一由上层负责。

### 11.2 非法残基：profile 层"只留空该位置"，但**分数层是 NaN**

* 位置机制：`ja 0x407737` 跳到的是**循环尾部**，`i` 照常自增 → 该位点仍然占据 profile 的一行，
  只是这一行在归一化前全为 0；**其余残基照常写入**，`L` 也不变。
* profile 层实测（`_re/verify_oracle.py` 第 7 节）：
  `ILPILSLIGGLL` 与 `ILJILSLIGGLL` 的 profile **只有第 3 行不同**，那一行是
  `[0×20, nan]`（见 §11.1 第 3 步）。
* 分数层实测：
  ```
  ILJILSLIGGLL  nan      ILBILSLIGGLL  nan      ILZILSLIGGLL  nan
  IL1ILSLIGGLL  nan      IL!ILSLIGGLL  nan
  IL*ILSLIGGLL  0.741922248   ← '*' 的表值是 0（当成 'A'），所以仍然有限
  ```
* ⚠ **纠正一个容易搞错的推论**："非法残基被跳过、其余照常生效，所以分数仍然有限"是**错的**：
  profile 层确实只跳过该位置，但那个全 0 列在归一化时产生 NaN，把整条分数污染成 NaN。
* **产品层决定（有意差异）**：`scoring.py` 直接**拒绝**含非字母字符的输入（如 `ILP1LS`），
  比原版严格（原版不报错、给 NaN）。
  `B/J/O/U/Z` 是**字母**，若原样送进引擎 → NaN → `scoring.py` 会命中 `math.isfinite`
  检查并跳过该条并给警告。**若产品希望给这类肽一个数**，最合理且可辩护的做法是在
  **预处理阶段把 `B/J/O/U/Z` 映射到 `X`（通道 20）**，并把这条明确写成有意差异。
* **`X` 与它们性质不同**：表值 = 20，是字母表第 21 个、**有独立权重**的真实通道。
  `s20==0` 时它走 0x40786a 分支得到 `profile[i][20] = 1`（0+1 → 1/1），不是 NaN。
  实测 `XXXXXXXXXX` = 0.976745，`X` 串与全非法输入的行为完全不同。

### 11.3 分数为什么取 `acc[1]`（并确认它就是阳性类）

证据链：
1. `Layer_soft::forward` 输出 2 维、和为 1 的概率向量（§4.2）；`MModel::predict` 把
   15 个子模型的输出逐元素平均，写进 `Sequence+264`：`Sequence+264[j] = acc[j]`（0x4070f4）。
2. `main` @0x40db3f–0x40db8d 把 `Sequence+264[0]`、`Sequence+264[1]` 依次用
   `operator<<(double)` 加空格写进 `.predictions` 的**第 6 行**，
   第 5 行才是 `"<期望类别> <预测类别>"`（0x40daf1–0x40db3a）。
3. `PeptideRanker.pl` 第 41–49 行 `shift` 5 行 → `$prediction` 正好是第 6 行
   `"<acc[0]> <acc[1]> "` → `split(/ /)` → `$foo[1]` = **`acc[1]`**。
4. `argmax`（写进 `Sequence+272`，0x40711c）与打印出来的是**类别下标**（+1 后写成 1-based），
   它**不是**分数；分数只是同一个向量里的第 2 个分量。两者不要混淆。
5. 从数据看 index 1 就是阳性类：缓激肽 `RPPGFSPFR` = 0.9558、`FLSLALAALPKLFCLIFKKC` = 0.9427，
   而随机肽平均 ≈ 0.35–0.49、`≥0.5` 占比 31%–46%（见 `scripts/check_distribution.py`），
   与论文"0.5 为活性阈值"的语义一致。
6. 一个**原程序自身的记账瑕疵**（不影响排序，仅供知情）：`peptide.dataset` 里
   `PeptideRanker.pl` 写死的标签是 `"1"`，`main` 会 `sub [rbx+276],1` 存成 **0**，
   即"期望类别 = 0"，而取出来当分数的却是 `acc[1]`。二者下标不一致，说明这个标签在发布版里
   只是个占位符（混淆矩阵在发布流程中不被使用）。**不要**因此把分数改取 `acc[0]`。

### 11.4 `Layer_soft` 的 85.0 溢出分支：对随包权重**不可达**

* 分支逻辑见 §4.2（`.rodata 0x40e338 = 85.0`）。要触发它，必须有某个 softmax 层的
  pre-activation `> 85.0`。
* softmax 层的输入是 `NN.L2` 的 `tanh` 输出，`|h| <= 1`，所以
  `pre = bias[i] + Σ_j W[i][j]·h[j] <= |bias[i]| + Σ_j |W[i][j]|`。
* 实测（`_re/verify_oracle.py` 第 9 节）：把 30 个模型的所有 softmax 输出单元都算一遍，
  `max(|bias| + Σ|W|) = 13.509229`（出现在 `Models_Long/fold3_v2`，清单里第 12 个模型、输出单元 0）。
  `13.51 < 85` → **该分支在这 30 个权重下永远进不去**，是训练代码留下的防御性死代码。
* 因此"分数会变成 1e-4 / 0.9999"**不会发生**；分数总是真正的 softmax 值。

### 11.5 其他边界

* **空序列 / 长度 0**：`generate_profile` 与 `Feed` 的所有循环都被 `L > 0` 档住，
  于是 profile 全 0、`buf` 全 0、`acc` 全 0 → NN 给出一个固定分数
  （实测空串 = 0.4531538853，任何 0 长度输入都一样）。产品层应直接拒绝空输入。
* **`.flatblast`**：见 §7 / §10 第 1 条。目录里存在 `<序列名>.flatblast` 时结果会变，
  本实现不支持该路径。
* **非字母字符的越界读**：可打印 ASCII 已逐字节复刻（§7.1）；`0x20..0x7E` 之外
  （含非 ASCII 字节）在原程序里会读到更远的、可能未映射的内存 —— **未定义行为**，
  本实现按"跳过"处理。产品层直接拒绝这类输入是最稳的。
* **长度路由**：`<=20` → Short，`>20` → Long，与 `.pl` 第 30–35 行一致；
  注意这是**字符数**（含被跳过的非法字符），不是有效残基数。

---

## 12. 实现对照表

| 反汇编 | `pr_engine/reference/oracle.py` |
|---|---|
| `Layer::read` @0x403d50 / `Layer::Layer` @0x404130 | `Layer.read` |
| `Layer::forward` @0x401d60 | `Layer.linear` |
| `Layer_tanh::forward` @0x4053e0 | `Layer.forward_tanh`（`np.tanh`） |
| `Layer_soft::forward` @0x405890 | `Layer.forward_softmax` |
| `NN::forward` @0x40c920 / `NNt::forward` @0x40be80 | `TwoLayerNet.forward` |
| `NNto1::F1_FE` @0x4081e0 | `NNto1.feed` 里构造 `big` 的部分 |
| `NNto1::Feed` @0x409570 | `NNto1.feed` 的累加 + `self.nn.forward` |
| `Sequence::generate_profile` @0x407630 | `MModel._profile` |
| `MModel::predict` @0x407000 | `MModel.predict` |
| `main` 的输出行 | `score_sequence` 取 `acc[1]` |
