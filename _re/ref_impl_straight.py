"""独立复刻：用**纯 Python 显式循环**、按对象内存布局逐条照抄反汇编，
与 oracle.py 的 numpy 向量化实现交叉验证（互为独立实现）。

刻意不复用 oracle.py 的任何函数（连取词器都自己写一份），
只共享"从 .model 文件读出来的数字"这一事实——若两者在合法输入上逐位一致，
说明 oracle.py 的向量化/索引没有引入偏差。
"""
import math
import os
import re
import sys

ROOT = r'C:\Users\wangchenxu\Desktop\PeptideRanker_Share'
INTS = re.compile(r'[+-]?\d+')
DBLS = re.compile(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')


class S:
    def __init__(self, t):
        self.t = t
        self.p = 0

    def _sk(self):
        while self.p < len(self.t) and self.t[self.p] in ' \t\r\n\f\v':
            self.p += 1

    def i(self):
        self._sk()
        m = INTS.match(self.t, self.p)
        assert m, self.p
        self.p = m.end()
        return int(m.group(0))

    def d(self):
        self._sk()
        m = DBLS.match(self.t, self.p)
        assert m, self.p
        self.p = m.end()
        return float(m.group(0))


def read_layer(s, kind):
    """Layer::read @0x403d50：length dim_in dim_out dims[] ; 每行 weights + bias。"""
    length, dim_in, dim_out = s.i(), s.i(), s.i()
    dims = [s.i() for _ in range(dim_in + dim_out)]
    W = []
    bias = []
    for _ in range(length):
        row = []
        for d in dims:
            row.append([s.d() for _ in range(d)])
        W.append(row)
        bias.append(s.d())
    return dict(length=length, dim_in=dim_in, dim_out=dim_out, dims=dims, W=W, bias=bias, kind=kind)


def read_net(s, kinds):
    ints = [s.i() for _ in range(7)]          # 顺序 +24,+20,+8,+12,+48,+52,+56（对前向无用）
    return dict(ints=ints, L1=read_layer(s, kinds[0]), L2=read_layer(s, kinds[1]))


def read_nnto1(s):
    ints = [s.i() for _ in range(8)]           # +0,+4,+8,+12,+16,+20,+24,+28
    return dict(ints=ints, nn=read_net(s, ('soft', 'tanh')), nnt=read_net(s, ('tanh', 'tanh')))


def load_models(kind):
    path = os.path.join(ROOT, 'Models_Short.txt' if kind == 'short' else 'Models_Long.txt')
    s = S(open(path).read())
    n = s.i()
    names = []
    for _ in range(n):
        s._sk()
        m = re.match(r'\S+', s.t[s.p:])
        names.append(m.group(0))
        s.p += m.end()
    out = []
    for nm in names:
        p = os.path.join(ROOT, nm)
        ms = S(open(p).read())
        hdr = [ms.i() for _ in range(8)]
        nd = hdr[1] - 1 if hdr[1] >= 2 else 0
        for _ in range(nd):
            ms.d()
        out.append(read_nnto1(ms))
        assert ms.p >= len(ms.t.rstrip()) - 1, (nm, ms.t[ms.p:ms.p + 20])
    return out


# ---- Layer::forward @0x401d60（显式循环版） ----
def layer_lin(L, in_vec, out_vec):
    y = []
    for i in range(L['length']):
        acc = L['bias'][i]
        off = 0
        for j in range(L['dim_in']):
            row = L['W'][i][j]
            for k in range(L['dims'][j]):
                acc += row[k] * in_vec[off + k]
            off += L['dims'][j]
        off = 0
        for j in range(L['dim_in'], L['dim_in'] + L['dim_out']):
            row = L['W'][i][j]
            for k in range(L['dims'][j]):
                acc += row[k] * out_vec[off + k]
            off += L['dims'][j]
        y.append(acc)
    return y


def layer_fwd(L, in_vec, out_vec):
    v = layer_lin(L, in_vec, out_vec)
    if L['kind'] == 'tanh':
        return [math.tanh(x) for x in v]
    # Layer_soft::forward @0x405890
    denom = 0.0
    best = v[0] if v else 0.0
    bi = 0
    big = False
    for i, x in enumerate(v):
        if x > 85.0:
            big = True
        else:
            denom += math.exp(x)
        if x > best:
            best = x
            bi = i
    if not big:
        return [math.exp(x) / denom for x in v]
    n = len(v)
    y = [1e-4] * n
    y[bi] = 1.0 - (n - 1) * 1e-4
    return y


def net_fwd(net, in_vec, out_vec):
    """NN::forward @0x40c920：先 L2 再 L1，L1 的 in/out 都是 L2 的输出。"""
    h = layer_fwd(net['L2'], in_vec, out_vec)
    return layer_fwd(net['L1'], h, h)


def make_profile(seq):
    """generate_profile @0x407630（无 .flatblast）。"""
    L = len(seq)
    prof = [[0.0] * 21 for _ in range(L + 1)]
    for i, ch in enumerate(seq, start=1):
        r = 'ACDEFGHIKLMNPQRSTVWYX'.find(ch)
        if 0 <= r <= 20:
            prof[i][r] += 1.0
    for i in range(1, L + 1):
        s20 = sum(prof[i][:20])
        old20 = prof[i][20]
        if s20 != 0.0:
            prof[i] = [x / s20 for x in prof[i]]
        denom = s20 + old20
        if denom == 0.0:
            prof[i][20] = float('nan') if prof[i][20] == 0.0 else math.copysign(float('inf'), prof[i][20])
        else:
            prof[i][20] = prof[i][20] / denom
    return prof


def feed(m, prof, L):
    """NNto1::Feed @0x409570 + F1_FE @0x4081e0。"""
    nf, ns = m['ints'][0], m['ints'][5]
    W = m['ints'][3]
    use_mean = m['ints'][4]
    states = []
    for p in range(1, L + 1):
        vec = [0.0] * ((2 * W + 1) * nf + 2)
        for t in range(2 * W + 1):
            q = p - W + t
            if 1 <= q <= L:
                for k in range(nf):
                    vec[t * nf + k] = prof[q][k]
        vec[-2] = p * 0.001
        vec[-1] = (L - p) * 0.001
        states.append(net_fwd(m['nnt'], vec, [0.0] * 8)[:ns])
    acc = [0.0] * ns
    for st in states:
        for k in range(ns):
            acc[k] += st[k] / 30.0
    buf = [0.0] * 8192
    if use_mean and nf > 0 and L > 0:
        for k in range(nf):
            buf[k] = sum(prof[p][k] for p in range(1, L + 1)) / L
    out = net_fwd(m['nn'], buf, acc)
    return out[:m['ints'][1]]


def score(seq, kind=None):
    if kind is None:
        kind = 'short' if len(seq) <= 20 else 'long'
    models = load_models(kind)
    prof = make_profile(seq)
    n = len(models)
    acc = [0.0] * models[0]['ints'][1]
    for m in models:
        o = feed(m, prof, len(seq))
        for j in range(len(acc)):
            acc[j] += o[j] / n
    return acc[1]


if __name__ == '__main__':
    sys.path.insert(0, os.path.join(ROOT, 'pr_engine', 'reference'))
    import oracle
    seqs = [l.strip() for l in open(os.path.join(ROOT, 'testfile.txt')) if l.strip()]
    seqs += ['A' * 8, 'ACDEFGHIKLMNPQRSTVWY' * 3, 'GLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC']
    worst = 0.0
    for s in seqs:
        a = score(s)
        b = oracle.score_sequence(s)
        rel = abs(a - b) / max(1e-300, abs(b))
        worst = max(worst, rel)
        print('  %-52s literal=%.15f  numpy=%.15f  rel=%.2e' % (s, a, b, rel))
    print('最大相对偏差 = %.3e' % worst)
    assert worst < 1e-12, worst
    print('两套独立实现在 15+3 条合法序列上一致（rel < 1e-12）')
