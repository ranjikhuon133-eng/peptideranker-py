"""按符号名过滤，把反汇编结果直接写成 UTF-8 文件（避免 PowerShell 管道编码问题）。"""
import sys, io
sys.path.insert(0, r'C:\Users\wangchenxu\Desktop\PeptideRanker_Share\_re')
import disasm as D
import struct

elf = r'C:\Users\wangchenxu\Desktop\PeptideRanker_Share\PeptideRanker'
pats = sys.argv[1:] if len(sys.argv) > 1 else ['']
out = (r'C:\Users\wangchenxu\Desktop\PeptideRanker_Share\_re\dis_layer.txt'
       if pats == ['Layer'] else
       r'C:\Users\wangchenxu\Desktop\PeptideRanker_Share\_re\dis_all.txt')

b = open(elf, 'rb').read()
e_shoff = struct.unpack_from('<Q', b, 0x28)[0]
e_shentsize = struct.unpack_from('<H', b, 0x3A)[0]
e_shnum = struct.unpack_from('<H', b, 0x3C)[0]
e_shstrndx = struct.unpack_from('<H', b, 0x3E)[0]
secinfo = []
for i in range(e_shnum):
    o = e_shoff + i * e_shentsize
    name, typ = struct.unpack_from('<II', b, o)
    flags, addr, off, size = struct.unpack_from('<QQQQ', b, o + 8)
    secinfo.append((name, addr, off, size))
stro = secinfo[e_shstrndx][2]
def cstr(base, o):
    e = b.index(b'\x00', base + o)
    return b[base + o:e].decode('latin1')
secs = {cstr(stro, n): (a, o, s) for (n, a, o, s) in secinfo}

def v2o(va):
    for (n, a, o, s) in secinfo:
        if a and a <= va < a + s:
            return o + (va - a)
    return None

syms = []
st = secs['.symtab']; sr = secs['.strtab']
for i in range(st[2] // 24):
    o = st[1] + i * 24
    nmo, info, other, shndx, value, size = struct.unpack_from('<IBBHQQ', b, o)
    nm = cstr(sr[1], nmo)
    if nm and size > 0 and (info & 0xf) == 2:
        syms.append((value, size, nm))
syms.sort()

text_addr, text_off, text_size = secs['.text']
lines = []
for (va, size, nm) in syms:
    if not (text_addr <= va < text_addr + text_size):
        continue
    if not any(p in nm for p in pats):
        continue
    fo = v2o(va)
    code = b[fo:fo + size]
    lines.append('=' * 88)
    lines.append('### %s  @0x%x  size=%d' % (nm, va, size))
    lines.append('=' * 88)
    d = D.Decoder(code, va)
    off = 0
    while off < len(code):
        txt, ln, ok = d.decode(off)
        lines.append('  %04x: %-46s ; %s' % (va + off, txt, ' '.join('%02x' % x for x in code[off:off + ln])))
        off += max(1, ln)
    lines.append('')

io.open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
print('wrote', out, 'sections=', sum(1 for l in lines if l.startswith('### ')))
