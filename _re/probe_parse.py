"""按反汇编推出的读取顺序解析 .model 文件，检查是否自洽（消费到 EOF）。"""
import re
import sys

INT_RE = re.compile(r'[+-]?\d+')
DBL_RE = re.compile(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')


class Stream:
    """模拟 C++ istream >>：跳过空白后按字面解析，不要求分隔符。"""

    def __init__(self, text):
        self.t = text
        self.p = 0
        self.n_int = 0
        self.n_dbl = 0

    def _skip(self):
        while self.p < len(self.t) and self.t[self.p] in ' \t\r\n\f\v':
            self.p += 1

    def rd_int(self):
        self._skip()
        m = INT_RE.match(self.t, self.p)
        if not m:
            raise ValueError('int 解析失败 @%d: %r' % (self.p, self.t[self.p:self.p + 20]))
        self.p = m.end()
        self.n_int += 1
        return int(m.group(0))

    def rd_dbl(self):
        self._skip()
        m = DBL_RE.match(self.t, self.p)
        if not m:
            raise ValueError('double 解析失败 @%d: %r' % (self.p, self.t[self.p:self.p + 20]))
        self.p = m.end()
        self.n_dbl += 1
        return float(m.group(0))


def parse_layer(s, tag=''):
    length = s.rd_int()
    dim_in = s.rd_int()
    dim_out = s.rd_int()
    dims = [s.rd_int() for _ in range(dim_in + dim_out)]
    rows = []
    for i in range(length):
        w = []
        for d in dims:
            w.extend(s.rd_dbl() for _ in range(d))
        b = s.rd_dbl()
        rows.append((w, b))
    print('  %-9s length=%d dim_in=%d dim_out=%d dims=%s  (idx: %d)' %
          (tag, length, dim_in, dim_out, dims, s.p))
    return dict(length=length, dim_in=dim_in, dim_out=dim_out, dims=dims, rows=rows)


def parse_net(s, tag, vtables):
    ints = [s.rd_int() for _ in range(7)]
    print('  %s ints(+24,+20,+8,+12,+48,+52,+56) = %s' % (tag, ints))
    for k, vt in zip(range(2), vtables):
        parse_layer(s, tag + '.L%d[%s]' % (k + 1, vt))
    return ints


def main(path):
    s = Stream(open(path).read())
    b8, b16, b24, b32, b48, b56, b64, b40 = (s.rd_int() for _ in range(8))
    print('MModel(+8,+16,+24,+32,+48,+56,+64,+40) =', (b8, b16, b24, b32, b48, b56, b64, b40))
    nd = b16 - 1 if b16 >= 2 else 0
    extra = [s.rd_dbl() for _ in range(nd)]
    print('  arr72 (读 %d 个) =' % nd, extra)
    print('NNto1 8 ints(+0,+4,+8,+12,+16,+20,+24,+28) =', [s.rd_int() for _ in range(8)])
    parse_net(s, 'NN ', ['soft', 'tanh'])
    parse_net(s, 'NNt', ['tanh', 'tanh'])
    s._skip()
    left = s.t[s.p:]
    print('剩余(应为空): %r   int=%d dbl=%d  pos=%d/%d' %
          (left[:60], s.n_int, s.n_dbl, s.p, len(s.t)))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else
         r'C:\Users\wangchenxu\Desktop\PeptideRanker_Share\Models_Short\fold0_v0\trained--20.model')
