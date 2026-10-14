"""oracle.py 自检：30 个模型解析、结构一致性、边界用例、误差统计。"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pr_engine', 'reference'))
import numpy as np
import oracle
from oracle import CONST_SOFTMAX_BIG

ROOT = oracle.ROOT


def struct_of(mm):
    out = []
    for m in mm.models:
        out.append((
            tuple(m.ints),
            (m.nn.L1.length, m.nn.L1.dim_in, m.nn.L1.dim_out, tuple(m.nn.L1.dims), m.nn.L1.kind),
            (m.nn.L2.length, m.nn.L2.dim_in, m.nn.L2.dim_out, tuple(m.nn.L2.dims), m.nn.L2.kind),
            (m.nnt.L1.length, m.nnt.L1.dim_in, m.nnt.L1.dim_out, tuple(m.nnt.L1.dims), m.nnt.L1.kind),
            (m.nnt.L2.length, m.nnt.L2.dim_in, m.nnt.L2.dim_out, tuple(m.nnt.L2.dims), m.nnt.L2.kind),
        ))
    return out


def main():
    print('=' * 78)
    print('1) 全部 30 个 .model 解析 + 结构一致性')
    print('=' * 78)
    for kind in ('short', 'long'):
        t = time.time()
        mm = oracle.load_mmodel(kind)
        st = struct_of(mm)
        uniq = set(st)
        print('%s: N=%d  解析耗时 %.2fs  结构种类=%d' % (kind, mm.n, time.time() - t, len(uniq)))
        for u in uniq:
            print('   ints            =', u[0])
            print('   NN .L1          =', u[1])
            print('   NN .L2          =', u[2])
            print('   NNt.L1          =', u[3])
            print('   NNt.L2          =', u[4])
        # 权重非空 & 有限
        for i, m in enumerate(mm.models):
            for nm, L in (('nn.L1', m.nn.L1), ('nn.L2', m.nn.L2), ('nnt.L1', m.nnt.L1), ('nnt.L2', m.nnt.L2)):
                assert np.isfinite(L.W).all() and np.isfinite(L.bias).all(), (kind, i, nm)
        print('   所有权重/偏置均为有限值 OK')

    print()
    print('=' * 78)
    print('2) testfile 15 条打分（与 PeptideRanker.pl 的模型选择规则一致）')
    print('=' * 78)
    seqs = [l.strip() for l in open(os.path.join(ROOT, 'testfile.txt')) if l.strip()]
    t = time.time()
    rows = []
    for s in seqs:
        d = oracle.score_sequence_detailed(s)
        rows.append((d['score'], s, d['models'], d['argmax'], float(d['mean'].sum())))
    for sc, s, mk, am, sm in rows:
        print('%8.6f  L=%2d  %-5s argmax=%d  sum=%.9f  %s' % (sc, len(s), mk, am, sm, s))
    print('15 条耗时 %.2fs' % (time.time() - t))
    assert all(0.0 <= r[0] <= 1.0 for r in rows), '分数越界'
    assert all(abs(r[4] - 1.0) < 1e-12 for r in rows), 'softmax 向量和不为 1'
    print('全部分数 ∈ [0,1] 且 mean 和为 1  OK')

    print()
    print('=' * 78)
    print('3) 模型选择规则边界（<=20 short, >20 long）')
    print('=' * 78)
    base = 'A' * 20
    for L in (1, 2, 19, 20, 21, 22, 60):
        s = (base * 4)[:L]
        d = oracle.score_sequence_detailed(s)
        print('  L=%2d -> %s  score=%.6f' % (L, d['models'], d['score']))
        assert d['models'] == ('short' if L <= 20 else 'long')
    print('OK')

    print()
    print('=' * 78)
    print('4) 字母表边界：未知残基 / 非标准字母 / 小写')
    print('=' * 78)
    for s in ('ACDEFGHIKLMNPQRSTVWYX', 'ACDEFGHIKLMNPQRSTVWYX' * 2, 'acdefghiklmnpqrstvwyx',
              'ACDEFGHIKLMNPQRSTVWYB', 'ACDEFGHIKLMNPQRSTVWY*', 'XXXXXXXXXX'):
        try:
            d = oracle.score_sequence_detailed(s)
            print('  %-44s L=%2d %-5s score=%.6f' % (s[:44], len(s), d['models'], d['score']))
        except Exception as e:
            print('  %-44s ERROR %s' % (s[:44], e))

    print()
    print('=' * 78)
    print('5) 单条 vs 批量一致性 / 幂等')
    print('=' * 78)
    s = 'RPPGFSPFR'
    a = oracle.score_sequence(s)
    b = oracle.score_sequence(s)
    c = oracle.score_sequence_detailed(s)['score']
    print('  repeat=%.12f %.12f detailed=%.12f  identical=%s' % (a, b, c, a == b == c))
    assert a == b == c

    print()
    print('=' * 78)
    print('6) 每个子模型的输出向量（RPPGFSPFR, Models_Short）')
    print('=' * 78)
    d = oracle.score_sequence_detailed('RPPGFSPFR')
    for i, v in enumerate(d['per_model']):
        print('  model %2d: [%.9f, %.9f]  (sum=%.9f)' % (i, v[0], v[1], v.sum()))
    print('  mean     :', d['mean'], ' argmax =', d['argmax'], ' score =', d['score'])

    print()
    print('=' * 78)
    print('7) 非法残基：profile 层只留空该位置；分数层原程序给 NaN')
    print('=' * 78)
    mm = oracle.load_mmodel('short')
    p_ok = mm._profile('ILPILSLIGGLL')
    p_bad = mm._profile('ILJILSLIGGLL')
    diff_rows = [i for i in range(1, 13) if not np.array_equal(p_ok[i], p_bad[i])]
    print('  ILPILSLIGGLL vs ILJILSLIGGLL 的 profile 不同行 =', diff_rows)
    assert diff_rows == [3], diff_rows
    print('  -> 只有被替换的那一列不同（第 3 位），说明其余残基照常生效 OK')
    print('     该列内容 =', p_bad[3])
    assert np.all(p_bad[3][:20] == 0.0) and np.isnan(p_bad[3][20])
    print('  -> 全 0 列 -> 归一化时 0.0/0.0 -> NaN（原程序 @0x4078a3 divsd 无保护）')
    for ch in 'JBZ1!':
        s = 'IL' + ch + 'ILSLIGGLL'
        v = oracle.score_sequence(s)
        print('  IL%sILSLIGGLL -> %s' % (ch, v))
        assert math.isnan(v), (ch, v)
    star = oracle.score_sequence('IL*ILSLIGGLL')
    print("  IL*ILSLIGGLL -> %.9f  （'*' 的表值是 0，当成 'A'，所以仍然有限）" % star)
    assert math.isfinite(star)
    print('  J/B/Z/1/! -> NaN；\'*\' -> 有限 OK')

    print()
    print('=' * 78)
    print('8) 全小写 / 全非法输入：原程序给出 NaN（不是"只与长度有关"的常数）')
    print('=' * 78)
    up = oracle.score_sequence('RPPGFSPFR')
    print('  RPPGFSPFR -> %.12f' % up)
    for name, s in (('rppgfspfr', 'rppgfspfr'), ('aaaaaaaaa', 'aaaaaaaaa'),
                    ('JJJJJJJJJ', 'JJJJJJJJJ'), ('!!!!!!!!!', '!!!!!!!!!')):
        v = oracle.score_sequence(s)
        print('  %-12s -> %s' % (name, v))
        assert math.isnan(v), (name, v)
    assert math.isfinite(up)
    print('  小写/全非法 -> 全是 NaN；大写合法 -> 有限 OK')
    print('  （因此产品层"统一转大写"不只是改进，而是**避免 NaN 的必要步骤**）')

    print()
    print('=' * 78)
    print('9) Layer_soft 的 85.0 溢出分支是否有机会触发')
    print('=' * 78)
    worst = 0.0
    for kind in ('short', 'long'):
        for m in oracle.load_mmodel(kind).models:
            L = m.nn.L1
            for i in range(L.length):
                worst = max(worst, abs(L.bias[i]) + float(np.abs(L.W[i]).sum()))
    print('  max(|bias| + Σ|W|) over 30 个 softmax 层 = %.6f' % worst)
    assert worst < CONST_SOFTMAX_BIG, '溢出分支可能触发！'
    print('  < 85.0，且 softmax 层输入是 tanh 输出(|.|<=1) -> 该分支对随包权重**不可达** OK')

    print()
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
