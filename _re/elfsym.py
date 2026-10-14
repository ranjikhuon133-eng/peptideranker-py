"""解析 ELF 的 PLT/重定位，把 stub 地址映射到外部符号名（供人工分析用）。"""
import struct

ELF = r'C:\Users\wangchenxu\Desktop\PeptideRanker_Share\PeptideRanker'


def load():
    b = open(ELF, 'rb').read()
    e_shoff = struct.unpack_from('<Q', b, 0x28)[0]
    es = struct.unpack_from('<H', b, 0x3A)[0]
    en = struct.unpack_from('<H', b, 0x3C)[0]
    ex = struct.unpack_from('<H', b, 0x3E)[0]
    secinfo = []
    for i in range(en):
        o = e_shoff + i * es
        nm, typ = struct.unpack_from('<II', b, o)
        fl, ad, of, sz = struct.unpack_from('<QQQQ', b, o + 8)
        secinfo.append([nm, ad, of, sz])
    stro = secinfo[ex][2]

    def cs(base, o):
        e = b.index(b'\x00', base + o)
        return b[base + o:e].decode('latin1')
    S = {cs(stro, n): (a, o, s) for (n, a, o, s) in secinfo}
    return b, S, secinfo


def plt_map():
    b, S, secinfo = load()
    d = {}
    dynsym = S['.dynsym']
    dynstr = S['.dynstr']
    names = []
    for i in range(dynsym[2] // 24):
        o = dynsym[1] + i * 24
        nmo, info, other, shndx, value, size = struct.unpack_from('<IBBHQQ', b, o)
        names.append(nmo)
    for secname in ('.rela.plt', '.rela.dyn'):
        if secname not in S:
            continue
        a, o, s = S[secname]
        for i in range(s // 24):
            off, info, add = struct.unpack_from('<QQq', b, o + i * 24)
            sym = info >> 32
            nm = ''
            if sym:
                e = b.index(b'\x00', dynstr[1] + names[sym])
                nm = b[dynstr[1] + names[sym]:e].decode('latin1')
            d[off] = nm
    plt = S['.plt']
    res = {}
    a, o, s = S['.rela.plt']
    for i in range(s // 24):
        off, info, add = struct.unpack_from('<QQq', b, o + i * 24)
        sym = info >> 32
        e = b.index(b'\x00', dynstr[1] + names[sym])
        nm = b[dynstr[1] + names[sym]:e].decode('latin1')
        res[plt[0] + 16 * (i + 1)] = nm
    return res


if __name__ == '__main__':
    for k, v in sorted(plt_map().items()):
        print('0x%x %s' % (k, v))
