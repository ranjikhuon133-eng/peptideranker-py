"""最小可用的 x86-64 反汇编器：仅覆盖该 ELF 中出现的指令子集。

用途：把 PeptideRanker (2010, GCC 4.4.3 -O2) 的关键函数反汇编出来，
以便确认 Layer::forward / Layer_soft::forward / Layer::read 的数学含义。
"""
import struct
import sys

# ---------- 操作码表 ----------
# 格式: opcode -> (助记符, 操作数类型串, 前缀类别)
#   operand 字符: 'r'=reg, 'm'=rm, 'i'=imm, '1'=常量1(无字节)
ALU = {
    0x00: ('add', 'mr'), 0x01: ('add', 'mr'), 0x02: ('add', 'rm'), 0x03: ('add', 'rm'),
    0x08: ('or', 'mr'), 0x09: ('or', 'mr'), 0x0A: ('or', 'rm'), 0x0B: ('or', 'rm'),
    0x10: ('adc', 'mr'), 0x11: ('adc', 'mr'), 0x18: ('sbb', 'mr'), 0x19: ('sbb', 'mr'),
    0x20: ('and', 'mr'), 0x21: ('and', 'mr'), 0x23: ('and', 'rm'),
    0x28: ('sub', 'mr'), 0x29: ('sub', 'mr'), 0x2A: ('sub', 'rm'), 0x2B: ('sub', 'rm'),
    0x30: ('xor', 'mr'), 0x31: ('xor', 'mr'), 0x32: ('xor', 'rm'), 0x33: ('xor', 'rm'),
    0x38: ('cmp', 'mr'), 0x39: ('cmp', 'mr'), 0x3A: ('cmp', 'rm'), 0x3B: ('cmp', 'rm'),
}
ALU_GRP1 = {0x80: ('i', 1), 0x81: ('i', 4), 0x83: ('i', 1)}
GRP1_NAME = ['add', 'or', 'adc', 'sbb', 'and', 'sub', 'xor', 'cmp']
# SSE 标量双精度 (F2 前缀)
SSE_F2 = {
    0x10: ('movsd', 'rm', 'x'), 0x11: ('movsd', 'mr', 'x'),
    0x12: ('movddup', 'rm', 'x'), 0x13: ('movlpd', 'mr', 'x'), 0x16: ('movhpd', 'rm', 'x'),
    0x17: ('movhpd', 'mr', 'x'),
    0x2A: ('cvtsi2sd', 'rm', 'g2x'), 0x2C: ('cvttsd2si', 'rm', 'x2g'), 0x2D: ('cvtsd2si', 'rm', 'x2g'),
    0x51: ('sqrtsd', 'rm', 'x'), 0x58: ('addsd', 'rm', 'x'), 0x59: ('mulsd', 'rm', 'x'),
    0x5C: ('subsd', 'rm', 'x'), 0x5D: ('minsd', 'rm', 'x'), 0x5E: ('divsd', 'rm', 'x'),
    0x5F: ('maxsd', 'rm', 'x'), 0x2E: ('ucomisd', 'rm', 'x'), 0x2F: ('comisd', 'rm', 'x'),
    0x70: ('pshufd', 'rmi', 'x'), 0x7C: ('haddpd', 'rm', 'x'), 0x7D: ('hsubpd', 'rm', 'x'),
    0xC2: ('cmpsd', 'rmi', 'x'), 0xD0: ('addsubpd', 'rm', 'x'),
    0xE6: ('cvtpd2dq', 'rm', 'x'), 0xF0: ('lddqu', 'rm', 'x'),
}
SSE_F2_38 = {0xF0: ('lddqu', 'rm', 'x'), 0xF1: ('psubd', 'rm', 'x')}
SSE_F3 = {
    0x10: ('movss', 'rm', 'x'), 0x11: ('movss', 'mr', 'x'),
    0x12: ('movsldup', 'rm', 'x'), 0x16: ('movshdup', 'rm', 'x'),
    0x2A: ('cvtsi2ss', 'rm', 'g2x'), 0x2C: ('cvttss2si', 'rm', 'x2g'),
    0x51: ('sqrtss', 'rm', 'x'), 0x58: ('addss', 'rm', 'x'), 0x59: ('mulss', 'rm', 'x'),
    0x5B: ('cvttps2dq', 'rm', 'x'), 0x5C: ('subss', 'rm', 'x'), 0x5D: ('minss', 'rm', 'x'),
    0x5E: ('divss', 'rm', 'x'), 0x5F: ('maxss', 'rm', 'x'),
    0x70: ('pshufw', 'rmi', 'x'), 0x7C: ('haddps', 'rm', 'x'), 0x7D: ('hsubps', 'rm', 'x'),
    0xC2: ('cmpss', 'rmi', 'x'), 0xE6: ('cvtdq2pd', 'rm', 'x'), 0xF0: ('lddqu', 'rm', 'x'),
}
SSE_66 = {
    0x10: ('movupd', 'rm', 'x'), 0x11: ('movupd', 'mr', 'x'),
    0x12: ('movlpd', 'rm', 'x'), 0x13: ('movlpd', 'mr', 'x'),
    0x14: ('unpcklpd', 'rm', 'x'), 0x15: ('unpckhpd', 'rm', 'x'),
    0x16: ('movhpd', 'rm', 'x'), 0x17: ('movhpd', 'mr', 'x'),
    0x28: ('movapd', 'rm', 'x'), 0x29: ('movapd', 'mr', 'x'),
    0x2A: ('cvtsi2sd', 'rm', 'g2x'), 0x2B: ('movntpd', 'mr', 'x'),
    0x2C: ('cvttsd2si', 'rm', 'x2g'), 0x2D: ('cvtsd2si', 'rm', 'x2g'),
    0x2E: ('ucomisd', 'rm', 'x'), 0x2F: ('comisd', 'rm', 'x'),
    0x51: ('sqrtsd', 'rm', 'x'), 0x54: ('andpd', 'rm', 'x'), 0x55: ('andnpd', 'rm', 'x'),
    0x56: ('orpd', 'rm', 'x'), 0x57: ('xorpd', 'rm', 'x'),
    0x58: ('addpd', 'rm', 'x'), 0x59: ('mulpd', 'rm', 'x'), 0x5A: ('cvtpd2ps', 'rm', 'x'),
    0x5B: ('cvtps2dq', 'rm', 'x'), 0x5C: ('subpd', 'rm', 'x'), 0x5D: ('minpd', 'rm', 'x'),
    0x5E: ('divpd', 'rm', 'x'), 0x5F: ('maxpd', 'rm', 'x'),
    0x60: ('punpcklbw', 'rm', 'x'), 0x61: ('punpcklwd', 'rm', 'x'), 0x62: ('punpckldq', 'rm', 'x'),
    0x63: ('packsswb', 'rm', 'x'), 0x64: ('pcmpgtb', 'rm', 'x'), 0x65: ('pcmpgtw', 'rm', 'x'),
    0x66: ('pcmpgtd', 'rm', 'x'), 0x67: ('packuswb', 'rm', 'x'),
    0x68: ('punpckhbw', 'rm', 'x'), 0x69: ('punpckhwd', 'rm', 'x'), 0x6A: ('punpckhdq', 'rm', 'x'),
    0x6C: ('punpcklqdq', 'rm', 'x'), 0x6D: ('punpckhqdq', 'rm', 'x'),
    0x6E: ('movd', 'rm', 'y'), 0x6F: ('movdqa', 'rm', 'x'), 0x70: ('pshufd', 'rmi', 'x'),
    0x74: ('pcmpeqb', 'rm', 'x'), 0x75: ('pcmpeqw', 'rm', 'x'), 0x76: ('pcmpeqd', 'rm', 'x'),
    0x7C: ('haddpd', 'rm', 'x'), 0x7D: ('hsubpd', 'rm', 'x'),
    0x7E: ('movd', 'mr', 'y'), 0x7F: ('movdqa', 'mr', 'x'),
    0xC2: ('cmppd', 'rmi', 'x'), 0xC4: ('pinsrw', 'rmi', 'x'), 0xC6: ('shufpd', 'rmi', 'x'),
    0xD1: ('psrlw', 'rm', 'x'), 0xD2: ('psrld', 'rm', 'x'), 0xD3: ('psrlq', 'rm', 'x'),
    0xD0: ('addsubpd', 'rm', 'x'),
    0xD4: ('paddq', 'rm', 'x'), 0xD5: ('pmullw', 'rm', 'x'), 0xD6: ('movq', 'mr', 'x'),
    0xD7: ('pmovmskb', 'rm', 'x'), 0xD8: ('psubusb', 'rm', 'x'), 0xD9: ('psubusw', 'rm', 'x'),
    0xDA: ('pminub', 'rm', 'x'), 0xDB: ('pand', 'rm', 'x'), 0xDC: ('paddusb', 'rm', 'x'),
    0xDD: ('paddusw', 'rm', 'x'), 0xDE: ('pmaxub', 'rm', 'x'), 0xDF: ('pandn', 'rm', 'x'),
    0xE0: ('pavgb', 'rm', 'x'), 0xE1: ('psraw', 'rm', 'x'), 0xE2: ('psrad', 'rm', 'x'),
    0xE3: ('pavgw', 'rm', 'x'), 0xE4: ('pmulhuw', 'rm', 'x'), 0xE5: ('pmulhw', 'rm', 'x'),
    0xE6: ('cvttpd2dq', 'rm', 'x'), 0xE7: ('movntdq', 'mr', 'x'), 0xE8: ('psubsb', 'rm', 'x'),
    0xE9: ('psubsw', 'rm', 'x'), 0xEA: ('pminsw', 'rm', 'x'), 0xEB: ('por', 'rm', 'x'),
    0xEC: ('paddsb', 'rm', 'x'), 0xED: ('paddsw', 'rm', 'x'), 0xEE: ('pmaxsw', 'rm', 'x'),
    0xEF: ('pxor', 'rm', 'x'), 0xF1: ('psllw', 'rm', 'x'), 0xF2: ('pslld', 'rm', 'x'),
    0xF3: ('psllq', 'rm', 'x'), 0xF4: ('pmuludq', 'rm', 'x'), 0xF5: ('pmaddwd', 'rm', 'x'),
    0xF6: ('psadbw', 'rm', 'x'), 0xF7: ('maskmovdqu', 'rm', 'x'), 0xF8: ('psubb', 'rm', 'x'),
    0xF9: ('psubw', 'rm', 'x'), 0xFA: ('psubd', 'rm', 'x'), 0xFB: ('psubq', 'rm', 'x'),
    0xFC: ('paddb', 'rm', 'x'), 0xFD: ('paddw', 'rm', 'x'), 0xFE: ('paddd', 'rm', 'x'),
}
SSE_NONE = {
    0x10: ('movups', 'rm'), 0x11: ('movups', 'mr'), 0x12: ('movlps', 'rm'),
    0x13: ('movlps', 'mr'), 0x14: ('unpcklps', 'rm'), 0x15: ('unpckhps', 'rm'),
    0x28: ('movaps', 'rm'), 0x29: ('movaps', 'mr'), 0x2A: ('cvtpi2ps', 'rm'),
    0x2B: ('movntps', 'mr'), 0x2C: ('cvttps2pi', 'rm'), 0x2D: ('cvtps2pi', 'rm'),
    0x2E: ('ucomiss', 'rm'), 0x2F: ('comiss', 'rm'),
    0x51: ('sqrtps', 'rm'), 0x52: ('rsqrtps', 'rm'), 0x53: ('rcpps', 'rm'),
    0x54: ('andps', 'rm'), 0x55: ('andnps', 'rm'), 0x56: ('orps', 'rm'), 0x57: ('xorps', 'rm'),
    0x58: ('addps', 'rm'), 0x59: ('mulps', 'rm'), 0x5A: ('cvtps2pd', 'rm'),
    0x5B: ('cvtdq2ps', 'rm'), 0x5C: ('subps', 'rm'), 0x5D: ('minps', 'rm'), 0x5E: ('divps', 'rm'),
    0x5F: ('maxps', 'rm'), 0x60: ('punpcklbw', 'rm'), 0x61: ('punpcklwd', 'rm'),
    0x62: ('punpckldq', 'rm'), 0x63: ('packsswb', 'rm'), 0x64: ('pcmpgtb', 'rm'),
    0x65: ('pcmpgtw', 'rm'), 0x66: ('pcmpgtd', 'rm'), 0x67: ('packuswb', 'rm'),
    0x68: ('punpckhbw', 'rm'), 0x69: ('punpckhwd', 'rm'), 0x6A: ('punpckhdq', 'rm'),
    0x6B: ('packssdw', 'rm'), 0x6C: ('punpcklqdq', 'rm'), 0x6D: ('punpckhqdq', 'rm'),
    0x6E: ('movd', 'rm'), 0x6F: ('movq', 'rm'), 0x70: ('pshufw', 'rmi'),
    0x74: ('pcmpeqb', 'rm'), 0x75: ('pcmpeqw', 'rm'), 0x76: ('pcmpeqd', 'rm'),
    0x77: ('emms', ''), 0x7E: ('movd', 'mr'), 0x7F: ('movq', 'mr'),
    0xC2: ('cmpps', 'rmi'), 0xC3: ('movnti', 'mr'), 0xC4: ('pinsrw', 'rmi'),
    0xC5: ('pextrw', 'rmi'), 0xC6: ('shufps', 'rmi'),
    0xD1: ('psrlw', 'rm'), 0xD2: ('psrld', 'rm'), 0xD3: ('psrlq', 'rm'), 0xD4: ('paddq', 'rm'),
    0xD5: ('pmullw', 'rm'), 0xD6: ('movq', 'mr'), 0xD7: ('pmovmskb', 'rm'),
    0xD8: ('psubusb', 'rm'), 0xD9: ('psubusw', 'rm'), 0xDA: ('pminub', 'rm'),
    0xDB: ('pand', 'rm'), 0xDC: ('paddusb', 'rm'), 0xDD: ('paddusw', 'rm'),
    0xDE: ('pmaxub', 'rm'), 0xDF: ('pandn', 'rm'), 0xE0: ('pavgb', 'rm'), 0xE1: ('psraw', 'rm'),
    0xE2: ('psrad', 'rm'), 0xE3: ('pavgw', 'rm'), 0xE4: ('pmulhuw', 'rm'), 0xE5: ('pmulhw', 'rm'),
    0xE7: ('movntq', 'mr'), 0xE8: ('psubsb', 'rm'), 0xE9: ('psubsw', 'rm'), 0xEA: ('pminsw', 'rm'),
    0xEB: ('por', 'rm'), 0xEC: ('paddsb', 'rm'), 0xED: ('paddsw', 'rm'), 0xEE: ('pmaxsw', 'rm'),
    0xEF: ('pxor', 'rm'), 0xF1: ('psllw', 'rm'), 0xF2: ('pslld', 'rm'), 0xF3: ('psllq', 'rm'),
    0xF4: ('pmuludq', 'rm'), 0xF5: ('pmaddwd', 'rm'), 0xF6: ('psadbw', 'rm'), 0xF7: ('maskmovq', 'rm'),
    0xF8: ('psubb', 'rm'), 0xF9: ('psubw', 'rm'), 0xFA: ('psubd', 'rm'), 0xFB: ('psubq', 'rm'),
    0xFC: ('paddb', 'rm'), 0xFD: ('paddw', 'rm'), 0xFE: ('paddd', 'rm'),
}
SSE3_F2 = {0x12: ('movddup', 'rm'), 0x7C: ('haddpd', 'rm'), 0x7D: ('hsubpd', 'rm')}
SSE3_F3 = {0x12: ('movsldup', 'rm'), 0x16: ('movshdup', 'rm'), 0x7C: ('haddps', 'rm'), 0x7D: ('hsubps', 'rm')}
SSSE3_66 = {0x00: ('pshufb', 'rm'), 0x01: ('phaddw', 'rm'), 0x02: ('phaddd', 'rm'),
            0x05: ('phsubw', 'rm'), 0x06: ('phsubd', 'rm'), 0x07: ('phsubsw', 'rm'),
            0x08: ('psignb', 'rm'), 0x09: ('psignw', 'rm'), 0x0A: ('psignd', 'rm'),
            0x0B: ('pmulhrsw', 'rm'), 0x1C: ('pabsb', 'rm'), 0x1D: ('pabsw', 'rm'), 0x1E: ('pabsd', 'rm')}
UNARY = {
    0xF2: ('not', 'm'), 0xF3: ('neg', 'm'), 0xF6: ('mul/imul/div/idiv', 'm'),
    0xF7: ('mul/imul/div/idiv', 'mq'), 0xFE: ('inc/dec', 'm'), 0xFF: ('inc/dec/call/jmp/push', 'm'),
}
UNARY_NAMES = {0xF6: ['test', 'test', 'not', 'neg', 'mul', 'imul', 'div', 'idiv'],
               0xF7: ['test', 'test', 'not', 'neg', 'mul', 'imul', 'div', 'idiv'],
               0xFE: ['inc', 'dec', 'inc', 'dec', 'inc', 'dec', 'inc', 'dec'],
               0xFF: ['inc', 'dec', 'call', 'call', 'jmp', 'jmp', 'push', 'push']}
SHIFT = {0xC0: ('i', 1), 0xC1: ('i', 1), 0xD0: ('1', 0), 0xD1: ('1', 0),
         0xD2: ('cl', 0), 0xD3: ('cl', 0)}
SHIFT_NAMES = ['rol', 'ror', 'rcl', 'rcr', 'shl', 'shr', 'sal/shl', 'sar']
FLAGOPS = {0x98: ('cwde', ''), 0x99: ('cdq', ''), 0x9C: ('pushf', ''), 0x9D: ('popf', ''),
           0x9E: ('sahf', ''), 0x9F: ('lahf', ''), 0x90: ('nop', ''),
           0xC9: ('leave', ''), 0xCB: ('retf', ''), 0xCC: ('int3', ''), 0xF4: ('hlt', ''),
           0xF5: ('cmc', ''), 0xF8: ('clc', ''), 0xF9: ('stc', ''), 0xFA: ('cli', ''), 0xFB: ('sti', ''),
           0xFC: ('cld', ''), 0xFD: ('std', ''), 0x6C: ('insb', ''), 0x6D: ('insd', ''),
           0x6E: ('outsb', ''), 0x6F: ('outsd', ''), 0xA4: ('movsb', ''), 0xA5: ('movsd-str', ''),
           0xAA: ('stosb', ''), 0xAB: ('stosd', ''), 0xAC: ('lodsb', ''), 0xAD: ('lodsd', ''),
           0xAE: ('scasb', ''), 0xAF: ('scasd', '')}
JCC = {0x70: 'jo', 0x71: 'jno', 0x72: 'jb', 0x73: 'jae', 0x74: 'je', 0x75: 'jne',
       0x76: 'jbe', 0x77: 'ja', 0x78: 'js', 0x79: 'jns', 0x7A: 'jp', 0x7B: 'jnp',
       0x7C: 'jl', 0x7D: 'jge', 0x7E: 'jle', 0x7F: 'jg'}
R8 = ['al', 'cl', 'dl', 'bl', 'spl', 'bpl', 'sil', 'dil']
R16 = ['ax', 'cx', 'dx', 'bx', 'sp', 'bp', 'si', 'di']
R32 = ['eax', 'ecx', 'edx', 'ebx', 'esp', 'ebp', 'esi', 'edi']
R64 = ['rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi']
XMM = ['xmm%d' % i for i in range(16)]


def reg_name(idx, size, hi=0, xmm=False, rex_present=False):
    """size: 操作数宽度(1/2/4/8)；hi: 寄存器编号的 bit3（来自 REX.R / REX.B / REX.X，取值 0/1）"""
    full = (idx & 7) | ((hi & 1) << 3)
    if xmm:
        return XMM[full]
    if size == 1:
        if rex_present:
            # 有 REX 前缀时，4..7 变为 spl/bpl/sil/dil，不再有 ah/ch/dh/bh
            return (R8 + ['r8b', 'r9b', 'r10b', 'r11b', 'r12b', 'r13b', 'r14b', 'r15b'])[full]
        return (['al', 'cl', 'dl', 'bl', 'ah', 'ch', 'dh', 'bh']
                + ['r8b', 'r9b', 'r10b', 'r11b', 'r12b', 'r13b', 'r14b', 'r15b'])[full]
    if size == 2:
        return (R16 + ['r%dw' % i for i in range(8, 16)])[full]
    if size == 4:
        return (R32 + ['r%dd' % i for i in range(8, 16)])[full]
    return (R64 + ['r%d' % i for i in range(8, 16)])[full]


SPECIAL_ADDR = {
    (0, 4, 5): 'rip',
}


class Decoder:
    def __init__(self, code, base):
        self.code = code
        self.base = base

    def _modrm(self, i, size, rex, xmm=False, addr64=False, rm_xmm=None, rm_size=None):
        if rm_xmm is None:
            rm_xmm = xmm
        if rm_size is None:
            rm_size = size
        m = self.code[i]
        i += 1
        mod = m >> 6
        reg = (m >> 3) & 7
        rm = m & 7
        rp = bool(rex[0])
        # rex 数组按 [present, B, R, X, W] 存储，寄存器编号 bit3 分别来自 B / R / X
        rexR = rex[2]
        rexB = rex[1]
        rexX = rex[3]
        regn = reg_name(reg, size, rexR, xmm, rp)
        # SIB / disp
        if mod == 3:
            rmstr = reg_name(rm, rm_size, rexB, rm_xmm, rp)
            return regn, rmstr, i, False
        parts = []
        addr_size = 4
        rip = False
        if rm == 4:
            sib = self.code[i]
            i += 1
            ss = sib >> 6
            index = (sib >> 3) & 7
            base_r = sib & 7
            idxn = reg_name(index, 8, rexX, False, True)
            if index == 4 and rexX == 0:
                idxn = None
            disp = 0
            has_disp = False
            if base_r == 5 and mod == 0:
                basen = None
                disp = struct.unpack_from('<i', self.code, i)[0]
                i += 4
                has_disp = True
            else:
                basen = reg_name(base_r, 8, rexB, False, True)
                if mod == 1:
                    disp = struct.unpack_from('<b', self.code, i)[0]
                    i += 1
                    has_disp = True
                elif mod == 2:
                    disp = struct.unpack_from('<i', self.code, i)[0]
                    i += 4
                    has_disp = True
            if basen:
                parts.append(basen)
            if idxn:
                parts.append('%s*%d' % (idxn, 1 << ss))
            if has_disp:
                parts.append('%+d' % disp if parts else str(disp))
            if not parts:
                parts.append('0')
            return regn, '[' + '+'.join(parts) + ']', i, rip
        if rm == 5 and mod == 0:
            disp = struct.unpack_from('<i', self.code, i)[0]
            i += 4
            rip = True
            return regn, 'rip%+d' % disp, i, True
        basen = reg_name(rm, 8, rexB, False, True)
        off = ''
        if mod == 1:
            d = struct.unpack_from('<b', self.code, i)[0]
            i += 1
            off = '%+d' % d
        elif mod == 2:
            d = struct.unpack_from('<i', self.code, i)[0]
            i += 4
            off = '%+d' % d
        return regn, '[%s%s]' % (basen, off), i, False

    def decode(self, off):
        """从 off 处解码一条指令，返回 (文本, 长度, 是否有效)"""
        start = off
        # rex 数组布局: [present, B, R, X, W]
        rex = [0, 0, 0, 0, 0]
        prefix66 = prefixF2 = prefixF3 = False
        lock_rep = ''
        while off < len(self.code):
            b = self.code[off]
            if 0x40 <= b <= 0x4F:
                # REX = 0100WRXB
                rex = [1, b & 1, (b >> 2) & 1, (b >> 1) & 1, (b >> 3) & 1]
                off += 1
                continue
            if b == 0x66:
                prefix66 = True
                off += 1
                continue
            if b == 0xF2:
                prefixF2 = True
                off += 1
                continue
            if b == 0xF3:
                prefixF3 = True
                off += 1
                continue
            if b in (0xF0,):
                lock_rep = 'lock '
                off += 1
                continue
            if b in (0x2E, 0x36, 0x3E, 0x26, 0x64, 0x65):
                off += 1
                continue
            break
        if off >= len(self.code):
            return None, 1, False
        op = self.code[off]
        off += 1
        rexW = rex[4]
        size = 8 if rexW else (2 if prefix66 else 4)
        pfx = ''

        def rel(disp):
            return '0x%x' % (self.base + off + disp)

        try:
            # --- 段/控制流 ---
            if op in JCC:
                d = struct.unpack_from('<b', self.code, off)[0]
                off += 1
                return '%s 0x%x' % (JCC[op], self.base + off + d), off - start, True
            if op == 0xEB:
                d = struct.unpack_from('<b', self.code, off)[0]
                off += 1
                return 'jmp 0x%x' % (self.base + off + d), off - start, True
            if op == 0xE9:
                d = struct.unpack_from('<i', self.code, off)[0]
                off += 4
                return 'jmp 0x%x' % (self.base + off + d), off - start, True
            if op == 0xE8:
                d = struct.unpack_from('<i', self.code, off)[0]
                off += 4
                return 'call 0x%x' % (self.base + off + d), off - start, True
            if op == 0xE3:
                d = struct.unpack_from('<b', self.code, off)[0]
                off += 1
                return 'jrcxz 0x%x' % (self.base + off + d), off - start, True
            if op == 0xC3:
                return 'ret', off - start, True
            if op == 0xC2:
                off += 2
                return 'ret imm16', off - start, True
            if op in (0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57):
                return 'push %s' % reg_name(op & 7, 8, rex[1]), off - start, True
            if op in (0x58, 0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F):
                return 'pop %s' % reg_name(op & 7, 8, rex[1]), off - start, True
            if op == 0x68:
                off += 4
                return 'push imm32', off - start, True
            if op == 0x6A:
                off += 1
                return 'push imm8', off - start, True
            if op == 0x63:
                rn, rm, off, _ = self._modrm(off, size, rex)
                return 'movsxd %s, %s' % (rn, rm), off - start, True
            # --- ALU ---
            if op in ALU:
                mn, fmt = ALU[op]
                if fmt == 'mr':
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    return '%s %s, %s' % (mn, rm, rn), off - start, True
                rn, rm, off, _ = self._modrm(off, size, rex)
                return '%s %s, %s' % (mn, rn, rm), off - start, True
            if op in (0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C):
                mn = ALU[op & 0x38 if op & 0x38 in ALU else (op - 4)][0]
                mn = {0x04: 'add', 0x0C: 'or', 0x14: 'adc', 0x1C: 'sbb',
                      0x24: 'and', 0x2C: 'sub', 0x34: 'xor', 0x3C: 'cmp'}[op]
                imm = self.code[off]
                off += 1
                return '%s al, 0x%x' % (mn, imm), off - start, True
            if op in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
                mn = {0x05: 'add', 0x0D: 'or', 0x15: 'adc', 0x1D: 'sbb',
                      0x25: 'and', 0x2D: 'sub', 0x35: 'xor', 0x3D: 'cmp'}[op]
                if rexW:
                    imm = struct.unpack_from('<i', self.code, off)[0]
                    off += 4
                    return '%s rax, 0x%x' % (mn, imm & 0xFFFFFFFFFFFFFFFF), off - start, True
                imm = struct.unpack_from('<I', self.code, off)[0]
                off += 4
                return '%s eax, 0x%x' % (mn, imm), off - start, True
            if op in ALU_GRP1:
                kind, ilen = ALU_GRP1[op]
                m = self.code[off]
                sub = (m >> 3) & 7
                rn, rm, off, _ = self._modrm(off, size, rex)
                if ilen == 1:
                    imm = struct.unpack_from('<b', self.code, off)[0]
                    off += 1
                else:
                    imm = struct.unpack_from('<i', self.code, off)[0]
                    off += 4
                return '%s %s, 0x%x' % (GRP1_NAME[sub], rm, imm & 0xFFFFFFFF), off - start, True
            if op in (0x84, 0x85):
                rn, rm, off, _ = self._modrm(off, size, rex)
                return 'test %s, %s' % (rm, rn), off - start, True
            if op in (0xA8, 0xA9):
                if op == 0xA8:
                    imm = self.code[off]
                    off += 1
                    return 'test al, 0x%x' % imm, off - start, True
                imm = struct.unpack_from('<I', self.code, off)[0]
                off += 4
                return 'test eax, 0x%x' % imm, off - start, True
            if op in UNARY:
                m = self.code[off]
                sub = (m >> 3) & 7
                sz = 1 if op == 0xF6 else size
                rn, rm, off, _ = self._modrm(off, sz, rex)
                nm = UNARY_NAMES.get(op, ['?'] * 8)[sub]
                if op in (0xF6, 0xF7) and sub in (0, 1):
                    if op == 0xF6:
                        imm = self.code[off]
                        off += 1
                    elif rexW:
                        imm = struct.unpack_from('<q', self.code, off)[0]
                        off += 8
                    elif prefix66:
                        imm = struct.unpack_from('<H', self.code, off)[0]
                        off += 2
                    else:
                        imm = struct.unpack_from('<I', self.code, off)[0]
                        off += 4
                    return 'test %s, 0x%x' % (rm, imm & 0xFFFFFFFFFFFFFFFF), off - start, True
                if op == 0xFF and sub in (2, 4):
                    nm = 'call' if sub == 2 else 'jmp'
                    return '%s %s' % (nm, rm), off - start, True
                return '%s %s' % (nm, rm), off - start, True
            if op in SHIFT:
                kind, ilen = SHIFT[op]
                m = self.code[off]
                sub = (m >> 3) & 7
                rn, rm, off, _ = self._modrm(off, size, rex)
                if ilen == 1:
                    imm = self.code[off]
                    off += 1
                    return '%s %s, %d' % (SHIFT_NAMES[sub], rm, imm), off - start, True
                return '%s %s, %s' % (SHIFT_NAMES[sub], rm, kind), off - start, True
            # --- mov ---
            if op in (0x88, 0x89):
                rn, rm, off, _ = self._modrm(off, size, rex)
                return 'mov %s, %s' % (rm, rn), off - start, True
            if op in (0x8A, 0x8B):
                rn, rm, off, _ = self._modrm(off, size, rex)
                return 'mov %s, %s' % (rn, rm), off - start, True
            if op in (0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7):
                imm = self.code[off]
                off += 1
                return 'mov %s, 0x%x' % (reg_name(op & 7, 1, rex[1], False, bool(rex[0])), imm), off - start, True
            if 0xB8 <= op <= 0xBF:
                r = reg_name(op & 7, size, rex[1])
                if rexW:
                    imm = struct.unpack_from('<q', self.code, off)[0]
                    off += 8
                elif prefix66:
                    imm = struct.unpack_from('<H', self.code, off)[0]
                    off += 2
                else:
                    imm = struct.unpack_from('<I', self.code, off)[0]
                    off += 4
                return 'mov %s, 0x%x' % (r, imm & 0xFFFFFFFFFFFFFFFF), off - start, True
            if op in (0xC6, 0xC7):
                m = self.code[off]
                rn, rm, off, _ = self._modrm(off, size, rex)
                if op == 0xC6:
                    imm = self.code[off]
                    off += 1
                else:
                    imm = struct.unpack_from('<i', self.code, off)[0]
                    off += 4
                return 'mov %s, 0x%x' % (rm, imm & 0xFFFFFFFF), off - start, True
            if op in (0x0F,):
                op2 = self.code[off]
                off += 1
                # SSE 分支
                if op2 in (0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x28, 0x29, 0x2A, 0x2B,
                           0x2C, 0x2D, 0x2E, 0x2F, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57,
                           0x58, 0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60, 0x61, 0x62,
                           0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D,
                           0x6E, 0x6F, 0x70, 0x74, 0x75, 0x76, 0x77, 0x7C, 0x7D, 0x7E, 0x7F,
                           0xC2, 0xC3,
                           0xC4, 0xC5, 0xC6, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8,
                           0xD9, 0xDA, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF, 0xE0, 0xE1, 0xE2, 0xE3,
                           0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE,
                           0xEF, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA,
                           0xFB, 0xFC, 0xFD, 0xFE):
                    table = None
                    fmt = 'x'
                    if prefixF2:
                        table = SSE_F2
                    elif prefixF3:
                        table = SSE_F3
                    elif prefix66:
                        table = SSE_66
                    else:
                        table = SSE_NONE
                    ent = table.get(op2)
                    if ent is None:
                        return 'db 0x0f 0x%02x (?)' % op2, off - start, False
                    mn, fmtv = ent[0], ent[1]
                    if fmtv == '':
                        return mn, off - start, True
                    if fmtv == 'rmi':
                        rn, rm, off, _ = self._modrm(off, 4, rex, xmm=True)
                        imm = self.code[off]
                        off += 1
                        return '%s %s, %s, 0x%x' % (mn, rn, rm, imm), off - start, True
                    if fmtv == 'mr':
                        rn, rm, off, _ = self._modrm(off, 4, rex, xmm=True)
                        return '%s %s, %s' % (mn, rm, rn), off - start, True
                    if fmtv == 'y':
                        rn, rm, off, _ = self._modrm(off, 4, rex, xmm=True,
                                                     rm_xmm=False, rm_size=4)
                        return '%s %s, %s' % (mn, rn, rm), off - start, True
                    if fmtv == 'q':
                        rn, rm, off, _ = self._modrm(off, 4, rex, xmm=True)
                        return '%s %s, %s' % (mn, rn, rm), off - start, True
                    if fmtv == 'g2x':
                        # cvtsi2sd/cvtsi2ss: reg=xmm, rm=GPR
                        rn, rm, off, _ = self._modrm(off, 4, rex, xmm=True,
                                                     rm_xmm=False, rm_size=8 if rexW else 4)
                        return '%s %s, %s' % (mn, rn, rm), off - start, True
                    if fmtv == 'x2g':
                        # cvttsd2si/cvtsd2si: reg=GPR, rm=xmm
                        rn, rm, off, _ = self._modrm(off, 8 if rexW else 4, rex, xmm=False,
                                                     rm_xmm=True, rm_size=4)
                        return '%s %s, %s' % (mn, rn, rm), off - start, True
                    rn, rm, off, _ = self._modrm(off, 4, rex, xmm=True)
                    return '%s %s, %s' % (mn, rn, rm), off - start, True
                # 通用 0F 指令
                if op2 == 0x05:
                    return 'syscall', off - start, True
                if op2 == 0x0F:
                    # 3DNow!: 0F 0F /r imm8
                    rn, rm, off, _ = self._modrm(off, 4, rex, xmm=True)
                    imm = self.code[off]
                    off += 1
                    return '3dnow 0x%02x %s, %s' % (imm, rn, rm), off - start, True
                if op2 in (0x1F,):
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    return 'nop %s' % rm, off - start, True
                if op2 in (0x31, 0xA2):
                    return 'rdtsc' if op2 == 0x31 else 'cpuid', off - start, True
                if 0x80 <= op2 <= 0x8F:
                    d = struct.unpack_from('<i', self.code, off)[0]
                    off += 4
                    nm = JCC[op2 - 0x10]
                    return '%s 0x%x' % (nm, self.base + off + d), off - start, True
                if op2 == 0x40 <= op2 <= 0x4F:
                    pass
                if 0x40 <= op2 <= 0x4F:
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    return 'cmov%s %s, %s' % (JCC[0x70 + (op2 - 0x40)][1:][:2], rn, rm), off - start, True
                if op2 in (0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99,
                           0x9A, 0x9B, 0x9C, 0x9D, 0x9E, 0x9F):
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    return 'set%s %s' % (JCC[0x70 + (op2 - 0x90)][1:], rm), off - start, True
                if op2 in (0xA3, 0xAB, 0xB3, 0xBB):
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    nm = {0xA3: 'bt', 0xAB: 'bts', 0xB3: 'btr', 0xBB: 'btc'}[op2]
                    return '%s %s, %s' % (nm, rm, rn), off - start, True
                if op2 in (0xA4, 0xA5, 0xAC, 0xAD):
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    nm = {0xA4: 'shld', 0xA5: 'shld', 0xAC: 'shrd', 0xAD: 'shrd'}[op2]
                    return '%s %s, %s, cl' % (nm, rm, rn), off - start, True
                if op2 in (0xAF,):
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    return 'imul %s, %s' % (rn, rm), off - start, True
                if op2 in (0xB6, 0xB7, 0xBE, 0xBF):
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    nm = {0xB6: 'movzx', 0xB7: 'movzx', 0xBE: 'movsx', 0xBF: 'movsx'}[op2]
                    return '%s %s, %s' % (nm, rn, rm), off - start, True
                if op2 == 0xB1:
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    return 'cmpxchg %s, %s' % (rm, rn), off - start, True
                if op2 == 0xC0:
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    return 'xadd %s, %s' % (rm, rn), off - start, True
                if op2 == 0xC1:
                    rn, rm, off, _ = self._modrm(off, size, rex)
                    return 'xadd %s, %s' % (rm, rn), off - start, True
                if op2 in (0xE7, 0xD7, 0x6E, 0x7E, 0x6F, 0x7F, 0xEF, 0x74, 0x75, 0x76, 0xFC,
                           0xFD, 0xFE, 0xFA, 0xF8, 0xF9, 0xFB, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5,
                           0xF6, 0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
                           0x6A, 0x6B, 0x6C, 0x6D):
                    pass
                return 'db 0x0f 0x%02x (?)' % op2, off - start, False
            if op == 0x8D:
                rn, rm, off, _ = self._modrm(off, size, rex)
                return 'lea %s, %s' % (rn, rm), off - start, True
            if op == 0x8F:
                rn, rm, off, _ = self._modrm(off, size, rex)
                return 'pop %s' % rm, off - start, True
            if op == 0x87:
                rn, rm, off, _ = self._modrm(off, size, rex)
                return 'xchg %s, %s' % (rm, rn), off - start, True
            if op == 0x86:
                rn, rm, off, _ = self._modrm(off, 1, rex)
                return 'xchg %s, %s' % (rm, rn), off - start, True
            if op == 0x69:
                rn, rm, off, _ = self._modrm(off, size, rex)
                imm = struct.unpack_from('<i', self.code, off)[0]
                off += 4
                return 'imul %s, %s, 0x%x' % (rn, rm, imm & 0xFFFFFFFF), off - start, True
            if op == 0x6B:
                rn, rm, off, _ = self._modrm(off, size, rex)
                imm = struct.unpack_from('<b', self.code, off)[0]
                off += 1
                return 'imul %s, %s, 0x%x' % (rn, rm, imm & 0xFFFFFFFF), off - start, True
            if op in FLAGOPS:
                return FLAGOPS[op][0], off - start, True
            if op == 0x0F:
                pass
            if 0x91 <= op <= 0x97:
                return 'xchg eax, %s' % reg_name(op & 7, size, rex[1]), off - start, True
            return 'db 0x%02x (?)' % op, off - start, False
        except Exception as e:
            return 'db ? (err %s)' % e, max(1, off - start), False


def main():
    elf = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\wangchenxu\Desktop\PeptideRanker_Share\PeptideRanker'
    b = open(elf, 'rb').read()
    e_shoff = struct.unpack_from('<Q', b, 0x28)[0]
    e_shentsize = struct.unpack_from('<H', b, 0x3A)[0]
    e_shnum = struct.unpack_from('<H', b, 0x3C)[0]
    e_shstrndx = struct.unpack_from('<H', b, 0x3E)[0]
    secs = {}
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
    for (name, addr, off, size) in secinfo:
        secs[cstr(stro, name)] = (addr, off, size)
    text_addr, text_off, text_size = secs['.text']
    rodata_addr, rodata_off, rodata_size = secs['.rodata']
    data_addr, data_off, data_size = secs['.data']

    def v2o(va):
        for (name, addr, off, size) in secinfo:
            if addr and addr <= va < addr + size:
                return off + (va - addr)
        return None

    # 符号表
    syms = []
    symtab = secs['.symtab']
    strtab = secs['.strtab']
    n = symtab[2] // 24
    for i in range(n):
        o = symtab[1] + i * 24
        nmo, info, other, shndx, value, size = struct.unpack_from('<IBBHQQ', b, o)
        nm = cstr(strtab[1], nmo)
        if nm and size > 0:
            syms.append((value, size, nm))
    syms.sort()

    import re
    pat = sys.argv[2] if len(sys.argv) > 2 else 'Layer'
    dec = Decoder(None, 0)
    for (va, size, nm) in syms:
        if pat not in nm:
            continue
        if not (text_addr <= va < text_addr + text_size):
            continue
        fo = v2o(va)
        code = b[fo:fo + size]
        print('=' * 90)
        print('### %s  @0x%x  size=%d' % (nm, va, size))
        print('=' * 90)
        dec = Decoder(code, va)
        # 快速扫描：先确定合法指令边界集合
        off = 0
        while off < len(code):
            txt, ln, ok = dec.decode(off)
            if ok:
                print('  %04x: %-52s ; %s' % (va + off, txt, ' '.join('%02x' % x for x in code[off:off + ln])))
            else:
                print('  %04x: <bytes> %s' % (va + off, ' '.join('%02x' % x for x in code[off:off + 8])))
            off += max(1, ln)
        print()


if __name__ == '__main__':
    main()
