"""PeptideRanker 2010 Linux ELF 的数值等价 Python 参考实现。

仅依赖 numpy。所有公式与读取顺序均来自对 `PeptideRanker` (ELF64 x86-64, GCC 4.4.3)
的反汇编，证据（函数 VA 与行号）见同目录 FORMAT.md。

对外接口::

    score_sequence(seq, models="short") -> float            # 0..1
    score_sequence_detailed(seq, models="short") -> dict

约定：
  * 字母表（.rodata @0x40e570 字符串，索引表 @0x40e380）：
        A C D E F G H I K L M N P Q R S T V W Y X      (index 0..20)
  * 长度 <= 20 用 Models_Short，> 20 用 Models_Long（与 PeptideRanker.pl 第 30-35 行一致）。
"""

from __future__ import annotations

import math
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))

ALPHABET = 'ACDEFGHIKLMNPQRSTVWYX'
RES_INDEX = {c: i for i, c in enumerate(ALPHABET)}

# ---------------------------------------------------------------------------
# 字符 -> 残基索引：精确复刻原程序的**表查找行为**，而不是"按字母表 upper()"。
#
# main 的做法（dis_all.txt:12838-12846）：
#     edx = (int8)ch ; edx -= 0x41 ('A') ; edx = int32[0x40e500 + 4*edx]
#     然后 generate_profile 里 `cmp edi,0x14 / ja`（**无符号**比较）决定是否计入。
#
# .rodata 0x40e500 只有 26 个有效条目（A..Z），表中 -1 表示非法。但只要 ch-'A'
# 落在 [0,25] 之外，原程序就会去读 0x40e500+4*(ch-'A') —— 对可打印 ASCII 而言
# 落在 0x40e47c..0x40e5f8，仍在已加载的只读段内（.rodata / .eh_frame_hdr），
# 于是得到**确定但不直观**的值：例如 'c' → 0（当成 'A'），'*' → 0（'A'），
# 'a' → 1498895956（>20，跳过）。下面这张表就是从二进制里逐字节抄出来的。
#
# 只列 ch-'A' 的**无符号值 <= 20** 的字符；其余一律按原程序的 `ja` 跳过。
# （空白字符在 main 里由 `operator>><char>` 直接跳过，永远不会到达这张表。）
# ---------------------------------------------------------------------------
CHAR_TO_RESIDUE = {
    0x20: 0, 0x22: 0, 0x24: 0, 0x26: 0, 0x27: 0, 0x28: 0, 0x2a: 0, 0x2c: 0,
    0x34: 0, 0x40: 0, 0x41: 0, 0x43: 1, 0x44: 2, 0x45: 3, 0x46: 4, 0x47: 5,
    0x48: 6, 0x49: 7, 0x4b: 8, 0x4c: 9, 0x4d: 10, 0x4e: 11, 0x50: 12,
    0x51: 13, 0x52: 14, 0x53: 15, 0x54: 16, 0x56: 17, 0x57: 18, 0x58: 20,
    0x59: 19, 0x5b: 0, 0x5c: 0, 0x63: 0,
}


def residue_index(ch):
    """返回残基索引 0..20；无法映射时返回 None（等价于原程序的 `ja` 跳过）。

    A..Z 走 .rodata 0x40e500 的 26 项表；其余可打印字符走上面那张"越界读"的实测表。
    0x20..0x7E 之外的字符在原程序里会读到未映射内存（未定义行为），这里一律跳过。
    """
    o = ord(ch)
    if 0x41 <= o <= 0x5A:
        return RES_INDEX.get(ch)
    return CHAR_TO_RESIDUE.get(o)

# 反汇编里出现的浮点常量
CONST_SOFTMAX_BIG = 85.0          # .rodata 0x40e338，Layer_soft 溢出阈值
CONST_EPS = 1e-4                  # .rodata 0x40e340 / movabs 0x3f1a36e2eb1c432d
CONST_POS_SCALE = 0.001           # .rodata 0x40e3e8，F1_FE 位置特征系数
CONST_ACC_DIV = 30.0              # .rodata 0x40e3f0，NNto1::Feed 中状态平均的除数
CONST_PROFILE_ADD = 1.0           # .rodata 0x40e300，generate_profile 每残基计数增量

MODEL_LISTS = {
    'short': os.path.join(ROOT, 'Models_Short.txt'),
    'long': os.path.join(ROOT, 'Models_Long.txt'),
}


# --------------------------------------------------------------------------
# 1. 模拟 C++ istream operator>> 的取词器
# --------------------------------------------------------------------------
class CxxStream:
    """模拟 `is >> int` / `is >> double`：跳过空白后按字面最长匹配，不需要分隔符。"""

    _INT = re.compile(r'[+-]?\d+')
    _DBL = re.compile(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')

    def __init__(self, text):
        self.t = text
        self.p = 0

    def _skip(self):
        n = len(self.t)
        p = self.p
        while p < n and self.t[p] in ' \t\r\n\f\v':
            p += 1
        self.p = p

    def rd_int(self):
        self._skip()
        m = self._INT.match(self.t, self.p)
        if not m:
            raise ValueError('整数解析失败 @%d: %r' % (self.p, self.t[self.p:self.p + 24]))
        self.p = m.end()
        return int(m.group(0))

    def rd_dbl(self):
        self._skip()
        m = self._DBL.match(self.t, self.p)
        if not m:
            raise ValueError('浮点解析失败 @%d: %r' % (self.p, self.t[self.p:self.p + 24]))
        self.p = m.end()
        return float(m.group(0))

    def eof(self):
        self._skip()
        return self.p >= len(self.t)


# --------------------------------------------------------------------------
# 2. Layer（Layer::Layer(istream&) @0x404130, Layer::read @0x403d50）
# --------------------------------------------------------------------------
class Layer:
    """一个 Layer 对象。

    文件格式（Layer::write @0x404c00 的逆）::

        length dim_in dim_out <dims[0..dim_in+dim_out-1]>
        <第 0 行: dims[0] 个 w, dims[1] 个 w, ... , bias[0]>
        ...
        <第 length-1 行: ... , bias[length-1]>

    前向（Layer::forward(double*,double*) @0x401d60）::

        y[i] = bias[i] + sum_{j<dim_in}   sum_k W[i][j][k] * in [off_in_j  + k]
                        + sum_{j>=dim_in} sum_k W[i][j][k] * out[off_out_j + k]

    其中 off_in_j = sum_{j'<j} dims[j']，off_out_j = sum_{dim_in<=j'<j} dims[j']。
    激活由派生类施加。
    """

    __slots__ = ('length', 'dim_in', 'dim_out', 'dims', 'W', 'bias',
                 'off_in', 'off_out', 'kind')

    def __init__(self, length, dim_in, dim_out, dims, W, bias, kind=''):
        self.length = length
        self.dim_in = dim_in
        self.dim_out = dim_out
        self.dims = dims
        self.W = W                # (length, sum(dims))
        self.bias = bias          # (length,)
        self.kind = kind
        self.off_in = int(sum(dims[:dim_in]))
        self.off_out = int(sum(dims[dim_in:]))

    @classmethod
    def read(cls, s: CxxStream, kind=''):
        length = s.rd_int()
        dim_in = s.rd_int()
        dim_out = s.rd_int()
        dims = [s.rd_int() for _ in range(dim_in + dim_out)]
        nw = sum(dims)
        W = np.empty((length, nw), dtype=np.float64) if (length > 0 and nw > 0) \
            else np.zeros((length, max(nw, 0)))
        bias = np.empty(length, dtype=np.float64) if length > 0 else np.zeros(0)
        for i in range(length):
            for c in range(nw):
                W[i, c] = s.rd_dbl()
            bias[i] = s.rd_dbl()
        return cls(length, dim_in, dim_out, dims, W, bias, kind)

    # --- 线性部分 ---
    def linear(self, in_vec, out_vec):
        y = self.bias.copy()
        if self.off_in:
            y += self.W[:, :self.off_in] @ np.asarray(in_vec, dtype=np.float64)[:self.off_in]
        if self.off_out:
            y += self.W[:, self.off_in:] @ np.asarray(out_vec, dtype=np.float64)[:self.off_out]
        return y

    # --- tanh 层（Layer_tanh::forward(double*,double*) @0x4053e0） ---
    def forward_tanh(self, in_vec, out_vec):
        return np.tanh(self.linear(in_vec, out_vec))

    # --- softmax 层（Layer_soft::forward(double*,double*) @0x405890） ---
    def forward_softmax(self, in_vec, out_vec):
        v = self.linear(in_vec, out_vec)
        if v.size == 0:
            return v
        # 逐元素复刻 0x405a9c-0x405b07 的那一圈扫描：
        #   ucomisd v, 85.0 ; jbe -> denom += exp(v)      (0x405adf/0x405ae3/0x405c2b)
        #   ucomisd v, best ; ja  -> best = v ; idx = i   (0x405aef/0x405af3/0x405ac4)
        # 关键：x86 的 `ucomisd` 对 NaN 会置 CF=ZF=PF=1，于是 `jbe` **成立**
        #      （NaN 走 exp 分支），而 `ja` **不成立**（NaN 不会成为最大值）。
        #      numpy 的 `NaN <= 85` 是 False，直接照抄会走错分支——必须显式写成
        #      "只有当 v > 85 为真才算溢出"。
        denom = 0.0
        best = v[0]
        best_i = 0
        big = False
        for i in range(v.size):
            vi = v[i]
            if vi > CONST_SOFTMAX_BIG:
                big = True
            else:
                denom += math.exp(vi)
            if vi > best:
                best = vi
                best_i = i
        if not big:
            e = np.exp(v)
            with np.errstate(invalid='ignore'):
                return e / denom
        # 分支：存在 pre-activation > 85 时用 "1-(n-1)eps / eps" 的近似替代
        # （0x405b36-0x405bd0；0x405bf3 的 clamp 对已赋的值无影响）
        n = v.size
        y = np.full(n, CONST_EPS)
        y[best_i] = 1.0 - (n - 1) * CONST_EPS
        return y

    def forward(self, in_vec, out_vec):
        if self.kind == 'soft':
            return self.forward_softmax(in_vec, out_vec)
        return self.forward_tanh(in_vec, out_vec)


# --------------------------------------------------------------------------
# 3. NN / NNt（NN::NN(istream&) @0x40cea0, NNt::NNt(istream&) @0x40c400）
# --------------------------------------------------------------------------
class TwoLayerNet:
    """NN 与 NNt 结构相同：7 个 int + 2 个 Layer。forward 调用顺序是 **L2 再 L1**。

    NN::forward(double*,double*) @0x40c920:
        L2->forward(in, out);  L1->forward(L2.out, L2.out)
    NNt::forward(double*,double*) @0x40be80 同构。
    """

    __slots__ = ('ints', 'L1', 'L2')

    def __init__(self, ints, L1, L2):
        self.ints = ints
        self.L1 = L1          # 文件里先读到的层（对象 +72）
        self.L2 = L2          # 文件里后读到的层（对象 +80）

    @classmethod
    def read(cls, s: CxxStream, kinds):
        # 读取顺序: +24, +20, +8, +12, +48, +52, +56   (0x40cea0 / 0x40c400)
        ints = [s.rd_int() for _ in range(7)]
        L1 = Layer.read(s, kinds[0])
        L2 = Layer.read(s, kinds[1])
        return cls(ints, L1, L2)

    def forward(self, in_vec, out_vec):
        h = self.L2.forward(in_vec, out_vec)
        return self.L1.forward(h, h)


# --------------------------------------------------------------------------
# 4. NNto1（NNto1::NNto1(istream&) @0x409870, Feed(double*,int) @0x409570,
#            F1_FE(double*,int,int) @0x4081e0）
# --------------------------------------------------------------------------
class NNto1:
    """一个子模型。

    文件格式::
        8 个 int（+0,+4,+8,+12,+16,+20,+24,+28）
        NN    = 7 int + 2 Layer（L1 为 Layer_soft, L2 为 Layer_tanh）
        NNt   = 7 int + 2 Layer（两层都是 Layer_tanh）

    槽位含义（由 Feed / F1_FE 的使用点推出）::

        +0  = 21   每位置的特征维数（字母表大小）
        +4  = 2    输出个数
        +8  = 5    （未在前向中使用）
        +12 = 10   窗口半宽 W（窗口 = 2W+1 = 21 个位置）
        +16 = 1    是否把输入 profile 在位置上取平均后送 NN
        +20 = 5    NNt 每位置输出维数 / 累加器长度
        +24 = 5    （未在前向中使用）
        +28 = 0    （未在前向中使用）
    """

    __slots__ = ('ints', 'nn', 'nnt', 'halfwin', 'n_feat', 'n_out',
                 'n_state', 'use_mean')

    def __init__(self, ints, nn, nnt):
        self.ints = ints
        self.nn = nn
        self.nnt = nnt
        self.n_feat = ints[0]
        self.n_out = ints[1]
        self.halfwin = ints[3]
        self.use_mean = ints[4]
        self.n_state = ints[5]

    @classmethod
    def read(cls, s: CxxStream):
        ints = [s.rd_int() for _ in range(8)]
        nn = TwoLayerNet.read(s, ('soft', 'tanh'))
        nnt = TwoLayerNet.read(s, ('tanh', 'tanh'))
        return cls(ints, nn, nnt)

    # -- F1_FE：把位置 p 周围的 (2W+1) 个 profile 行拼成一条向量，送 NNt --
    def _window(self, profile, p, L):
        W = self.halfwin
        nf = self.n_feat
        vec = np.zeros((2 * W + 1) * nf + 2, dtype=np.float64)
        for t in range(2 * W + 1):
            q = p - W + t
            if 1 <= q <= L:
                vec[t * nf:(t + 1) * nf] = profile[q]
        vec[-2] = p * CONST_POS_SCALE
        vec[-1] = (L - p) * CONST_POS_SCALE
        return vec

    def feed(self, profile, L):
        """profile: (L+1, n_feat) 逐位置归一化后的矩阵（第 0 行不使用）。"""
        nf = self.n_feat
        ns = self.n_state
        win = 2 * self.halfwin + 1

        # 每位置一条 (win*nf+2) 向量；一次算完（F1_FE 逐个位置调用）
        idx = np.arange(1, L + 1)
        big = np.zeros((L, win * nf + 2), dtype=np.float64)
        for t in range(win):
            q = idx - self.halfwin + t
            ok = (q >= 1) & (q <= L)
            if ok.any():
                big[ok, t * nf:(t + 1) * nf] = profile[q[ok]]
        if L > 0:
            big[:, -2] = idx * CONST_POS_SCALE
            big[:, -1] = (L - idx) * CONST_POS_SCALE

        # NNt 逐位置；L2 只用 in（dim_out=0），L1 只用 L2 的输出
        states = np.empty((L, ns), dtype=np.float64)
        tmp = np.zeros(8, dtype=np.float64)
        for i in range(L):
            states[i] = self.nnt.forward(big[i], tmp)[:ns]

        # NNto1::Feed 中的累加与平均
        acc = states.sum(axis=0) / CONST_ACC_DIV if L > 0 else np.zeros(ns)
        buf = np.zeros(8192, dtype=np.float64)
        if self.use_mean and nf > 0 and L > 0:
            buf[:nf] = profile[1:L + 1, :nf].sum(axis=0) / L
        out = self.nn.forward(buf, acc)
        return out[:self.n_out]


# --------------------------------------------------------------------------
# 5. MModel（MModel::MModel(istream&) @0x406660, MModel::predict @0x407000）
# --------------------------------------------------------------------------
class MModel:
    """一组子模型的算术平均。

    模型列表文件: 第一行是模型个数 N，随后 N 行是 .model 路径。
    每个 .model 文件::

        8 个 int（+8,+16,+24,+32,+48,+56,+64,+40）
        (ints[+16] - 1) 个 double      （ints[+16] >= 2 时；见下）
        NNto1

    注意 .model 头部的 double 个数是 `ints[+16] - 1`：反汇编里的循环
    （0x4068e0..0x406909）在 `eax = count - 1; cmp eax, r12d; jg loop` 下
    实际只读 count-1 个 double。
    """

    def __init__(self, names, models, hdr):
        self.names = names
        self.models = models
        self.hdr = hdr            # 每个文件头部的 8 个 int
        self.n = len(models)

    @classmethod
    def read_list(cls, list_path):
        with open(list_path, 'r') as fh:
            text = fh.read()
        s = CxxStream(text)
        n = s.rd_int()
        base = os.path.dirname(os.path.abspath(list_path))
        names = []
        for _ in range(n):
            s._skip()
            m = re.match(r'\S+', s.t[s.p:])
            names.append(m.group(0))
            s.p += m.end()
        models = []
        hdr = []
        for nm in names:
            path = nm if os.path.isabs(nm) else os.path.join(base, nm)
            with open(path, 'r') as fh:
                ms = CxxStream(fh.read())
            h = [ms.rd_int() for _ in range(8)]
            # 读取顺序 +8,+16,+24,+32,+48,+56,+64,+40；第 2 个（+16）是 double 个数
            ndbl = h[1] - 1 if h[1] >= 2 else 0
            extra = [ms.rd_dbl() for _ in range(ndbl)]
            models.append(NNto1.read(ms))
            hdr.append((h, extra))
        return cls(names, models, hdr)

    def _profile(self, seq):
        """Sequence::generate_profile @0x407630（无 .flatblast 文件时的路径）。"""
        L = len(seq)
        profile = np.zeros((L + 1, len(ALPHABET)), dtype=np.float64)
        for i, ch in enumerate(seq, start=1):
            r = residue_index(ch)
            if r is None:
                continue                      # 与表里 -1 / >20 的 `ja` 跳过一致
            profile[i, r] += CONST_PROFILE_ADD
        # 逐位点归一化：先除以 index 0..19 的和，再单独处理 index 20。
        # 精确复刻 generate_profile @0x4077ee-0x4078ab：
        #   s20 = Σ_{k=0..19} profile[i][k]              (0x407838, 恰好 20 次)
        #   old20 = profile[i][20]                       (0x407855, **除法之前**读)
        #   if s20 != 0:  profile[i][0..20] /= s20       (0x407c10)
        #   profile[i][20] /= (s20 + old20)              (0x40788a addsd + 0x4078a3 divsd)
        # ⚠ 当整列全 0（该位点是 B/J/O/U/Z 等非法残基）时 s20=old20=0
        #    → 0.0/0.0 = **NaN**，原程序没有做任何保护（0x4078a3 `divsd`）。
        #    这个 NaN 会顺着 F1_FE 的窗口传进 NNt → acc → 最终分数。
        #    这是一处**原程序的潜在 bug**，只在非法残基上暴露；本实现如实复刻。
        with np.errstate(divide='ignore', invalid='ignore'):
            for i in range(1, L + 1):
                s20 = profile[i, :20].sum()
                old20 = profile[i, 20]
                if s20 != 0.0:
                    profile[i, :] /= s20
                profile[i, 20] = profile[i, 20] / (s20 + old20)
        return profile

    def predict(self, seq):
        profile = self._profile(seq)
        L = len(seq)
        n_out = self.models[0].n_out
        acc = np.zeros(n_out, dtype=np.float64)
        per_model = []
        for m in self.models:
            out = m.feed(profile, L)
            per_model.append(np.array(out, dtype=np.float64))
            acc += out / self.n
        best = 0
        bestv = 0.0
        for j in range(n_out):
            if acc[j] > bestv:
                bestv = acc[j]
                best = j
        return {
            'sequence': seq,
            'length': L,
            'per_model': np.array(per_model),   # (N, n_out)
            'mean': acc,
            'argmax': best,
            'score': float(acc[1]) if n_out > 1 else float(acc[0]),
        }


# --------------------------------------------------------------------------
# 6. 对外接口
# --------------------------------------------------------------------------
_CACHE = {}


def load_mmodel(models='short'):
    if isinstance(models, MModel):
        return models
    key = models
    if key not in _CACHE:
        path = MODEL_LISTS[models]
        _CACHE[key] = MModel.read_list(path)
    return _CACHE[key]


def pick_models(seq):
    """与 PeptideRanker.pl 第 30-35 行一致：长度<=20 用 Short，否则 Long。"""
    return 'short' if len(seq) <= 20 else 'long'


def score_sequence_detailed(seq, models=None):
    """返回完整中间量：每个子模型的输出向量、平均向量、argmax、最终分数。"""
    # PeptideRanker.pl 只去掉行尾空白；原程序用 `operator>><char>` 逐字符读取时会跳过
    # 所有空白，所以这里把空白整体去掉，长度 L 即残基个数。
    seq = ''.join(seq.split())
    if models is None:
        models = pick_models(seq)
    mm = load_mmodel(models)
    d = mm.predict(seq)
    d['models'] = models if isinstance(models, str) else 'custom'
    d['n_models'] = mm.n
    return d


def score_sequence(seq, models=None):
    """PeptideRanker.pl 实际使用的分数：15 个子模型第二输出单元的平均值（0..1）。"""
    return float(score_sequence_detailed(seq, models)['score'])


def model_info():
    """供服务层展示：每组可用模型个数（读取清单文件，不强求权重全部载入）。"""
    info = {}
    for kind, path in MODEL_LISTS.items():
        try:
            with open(path) as fh:
                first = fh.readline().strip()
            info[kind] = int(first)
        except Exception:
            info[kind] = 0
    return info


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        for line in open(sys.argv[1]):
            line = line.strip()
            if line:
                print('%.6f\t%s' % (score_sequence(line), line))
    else:
        for s in ['ILPILSLIGGLL', 'RPPGFSPFR', 'FLPIVGKLLSGLSGLL']:
            print('%.6f\t%s' % (score_sequence(s), s))
