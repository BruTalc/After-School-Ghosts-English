#!/usr/bin/env python3
"""unlzexe.py - unpack an LZEXE 0.91 ("LZ91") compressed DOS MZ executable.

Usage: python unlzexe.py PACKED.EXE UNPACKED.EXE
"""
import struct
import sys


def unlzexe(data):
    hdr = list(struct.unpack('<16H', data[:32]))
    if data[0x1C:0x20] != b'LZ91':
        raise ValueError('not an LZEXE 0.91 file')
    cparhdr, e_cs = hdr[4], hdr[0x0B]
    infpos = (cparhdr + e_cs) << 4
    inf = struct.unpack('<8H', data[infpos:infpos + 16])

    # relocation table (compressed, LZ91 flavour)
    pos = infpos + 0x158
    relocs = []
    off = seg = 0
    while True:
        c = data[pos]; pos += 1
        if c == 0:
            c = struct.unpack_from('<H', data, pos)[0]; pos += 2
            if c == 0:
                seg += 0x0FFF
                continue
            if c == 1:
                break
        off += c
        seg += (off & ~0x0F) >> 4
        off &= 0x0F
        relocs.append((off, seg & 0xFFFF))

    # body
    pos = (e_cs - inf[4] + cparhdr) << 4
    out = bytearray()
    state = {'pos': pos}

    def getb():
        b = data[state['pos']]; state['pos'] += 1
        return b

    def getw():
        w = struct.unpack_from('<H', data, state['pos'])[0]; state['pos'] += 2
        return w

    bits = [getw(), 16]

    def getbit():
        b = bits[0] & 1
        bits[1] -= 1
        if bits[1] == 0:
            bits[0] = getw(); bits[1] = 16
        else:
            bits[0] >>= 1
        return b

    while True:
        if getbit():
            out.append(getb())
            continue
        if not getbit():
            ln = getbit() << 1
            ln |= getbit()
            ln += 2
            span = getb() - 0x100
        else:
            lo = getb(); hi = getb()
            span = (lo | ((hi & ~0x07) << 5)) - 0x2000
            ln = (hi & 0x07) + 2
            if ln == 2:
                ln = getb()
                if ln == 0:
                    break
                if ln == 1:
                    continue
                ln += 1
        for _ in range(ln):
            out.append(out[span])

    # new header
    relsize = len(relocs) * 4
    hsize = (0x1C + relsize + 0x1FF) & ~0x1FF
    total = hsize + len(out)
    nh = [0] * 14
    nh[0] = 0x5A4D
    nh[1] = total & 0x1FF
    nh[2] = (total + 0x1FF) >> 9
    nh[3] = len(relocs)
    nh[4] = hsize >> 4
    dec = inf[5] + ((inf[6] + 15) >> 4) + 9
    nh[5] = max(hdr[5] - dec, 0)
    nh[6] = hdr[6] if hdr[6] == 0xFFFF else max(hdr[6] - dec, 0)
    nh[7] = inf[3]  # SS
    nh[8] = inf[2]  # SP
    nh[9] = 0
    nh[10] = inf[0]  # IP
    nh[11] = inf[1]  # CS
    nh[12] = 0x1C
    nh[13] = 0
    # BSS that used to be covered by the packed image's load size
    # minalloc: keep original memory need = (orig load + minalloc) - new load
    orig_need = ((hdr[2] * 512 - (hdr[4] << 4)) >> 4) + hdr[5]
    new_load = (len(out) + 15) >> 4
    nh[5] = max(orig_need - new_load, nh[5])
    h = bytearray(struct.pack('<14H', *nh))
    for o, s in relocs:
        h += struct.pack('<HH', o, s)
    h = h.ljust(hsize, b'\0')
    return bytes(h) + bytes(out)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    open(sys.argv[2], 'wb').write(unlzexe(open(sys.argv[1], 'rb').read()))
