#!/usr/bin/env python3
"""
find_exe_strings.py - (developer tool, needs `pip install capstone`)

Scans the *unpacked* RPG.EXE for Japanese strings in the data segment and for
every place in code/data that points at them, and writes tools/exe_strings.json.
The normal dump/build pipeline only reads that JSON, so translators never need
to run this.  Re-run it only if you want to pick up more strings.

Usage: python find_exe_strings.py UNPACKED_RPG.EXE OUT.json
"""
import json
import struct
import sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_16

DS = 0x1527  # DGROUP paragraph (relative to load image)

# Menus stored as one string cut into equal-width slices: offset -> (items, bytes per item)
LAYOUT = {
    0x0153: (2, 16), 0x6DAF: (6, 10), 0x6ECB: (2, 6), 0x716F: (2, 6), 0x718B: (2, 12),
    0x71D7: (4, 16), 0x76E5: (5, 8), 0x7CB3: (2, 10),
}
# Strings that must not be touched (code indexes into them / pure layout filler)
SKIP = {0x0174, 0x7218, 0x6D98, 0x6B51, 0x7FFE}

W = 'Status screen, printf format: keep the %-4d. This screen draws formatted text DOUBLE WIDTH, and the number must start where it did originally, so use at most '
N = 'NAME = a character/enemy name printed just before this. '
NOTES = {
    0x7037: N + 'Field menu. Full message: NAME + this + MAGIC + [703B].',
    0x703B: 'Printed right after a magic name (see 7037).',
    0x704D: 'Printed right after an item name: NAME + [は#] + ITEM + this.',
    0x7059: N + 'NAME + this + NUMBER + [7062].',
    0x7062: 'Follows a number (HP amount).',
    0x7071: 'this + NUMBER + [7080] (whole party healed).',
    0x70FF: N + 'NAME + this + NUMBER + [7108].',
    0x7117: N + 'NAME + this + NUMBER + [7120] (MP).',
    0x7120: 'Follows a number (MP amount).',
    0x7308: 'Party lands a critical: this + [7312].',
    0x730D: 'Enemy lands a critical: this + [7312].',
    0x7312: 'See 7308/730D.',
    0x7399: N + 'NAME + this + ( [739C]  or  NUMBER + [73B0] ).',
    0x739C: 'NAME + [7399] + this.',
    0x73B0: 'NAME + [7399] + NUMBER + this.',
    0x73C1: N + 'NAME + this + one of [73C4] / [73D0] / [73E0] (target unavailable).',
    0x73F3: N + 'Battle. NAME + this + MAGIC + [73F7].',
    0x7425: N + 'NAME + this + NUMBER + [742E].',
    0x743D: 'this + NUMBER + [744C].',
    0x7524: N + 'NAME + this + [7541] + NUMBER + [7545] (stat up).',
    0x752D: 'see 7524', 0x7536: 'see 7524',
    0x7541: 'see 7524', 0x7545: 'see 7524',
    0x7554: N + 'NAME + this + [7571] + NUMBER + [7575] (stat down).',
    0x755D: 'see 7554', 0x7566: 'see 7554', 0x7571: 'see 7554', 0x7575: 'see 7554',
    0x7584: N + 'Battle. NAME + this + ITEM + [7588].',
    0x75A6: N + 'NAME + this + NUMBER + [75AF].',
    0x75BE: N + 'NAME + this + NUMBER + [75C7] (MP).',
    0x7687: N + 'NAME + this + NUMBER + [7690].',
    0x777D: 'this + NUMBER + [778F].',
    0x7799: 'this + NUMBER + [77A1].',
    0x77B0: N + 'NAME + this + NUMBER + [77B9].',
    0x7CF8: 'Shop, selling. this + PRICE + [7CFF].',
    0x7D2D: 'Inn. this + PRICE + [7D39]. Then a Yes/No menu appears.',
    0x6F4A: 'Status (Attack). ' + W + '4 characters before the %-4d.',
    0x6F57: 'Status (Defense). ' + W + '4 characters before the %-4d.',
    0x6F64: 'Status (Strength). ' + W + '2 characters before the %-4d.',
    0x6F6D: 'Status (Vitality). ' + W + '3 characters before the %-4d.',
    0x6F78: 'Status (Intelligence). ' + W + '3 characters before the %-4d.',
    0x6F83: 'Status (Speed). ' + W + '5 characters before the %-4d.',
    0x6F92: 'Status (Luck). ' + W + '2 characters before the %-4d.',
    0x6F02: 'Status ailment tag, 4 columns: poison', 0x6F07: 'ailment tag, 4 columns: magic sealed',
    0x6F0C: 'ailment tag, 4 columns: confused', 0x6F11: 'ailment tag, 4 columns: asleep',
    0x6F16: 'ailment tag, 4 columns: paralysed',
    0x6ED8: 'Equip screen slot label, 6 columns.', 0x6EDF: 'Equip slot label, 6 columns.',
    0x6EE6: 'Equip slot label, 6 columns.', 0x6EED: 'Equip slot label, 6 columns.',
    0x6EF4: 'Equip slot label, 6 columns.',
    0x71CE: 'Debug flag monitor, printf format. Do NOT use the # character (it means newline).',
    0x01E2: 'Printed by DOS after quitting (plain text mode; \r\n line ends).',
}


def main(exe_path, out_path):
    d = open(exe_path, 'rb').read()
    h = struct.unpack('<14H', d[:28])
    img = d[h[4] * 16:]
    dsb = DS * 16
    relocs = [s * 16 + o for o, s in (struct.unpack_from('<HH', d, h[12] + i * 4) for i in range(h[3]))]
    relset = set(relocs)

    dataptr = {}
    for r in relocs:
        if r >= dsb and struct.unpack_from('<H', img, r)[0] == DS:
            dataptr.setdefault(struct.unpack_from('<H', img, r - 2)[0], []).append(r - 2 - dsb)

    md = Cs(CS_ARCH_X86, CS_MODE_16)
    ins = []
    a = 0
    while a < dsb:
        for i in md.disasm(img[a:dsb], a):
            ins.append(i)
            a = i.address + i.size
        if a < dsb:
            a += 1
    coderef = {}
    for k, i in enumerate(ins):
        b = i.bytes
        if b[0] in (0xB8, 0xB9, 0xBA, 0xBB, 0xBE, 0xBF) and len(b) == 3:
            imm, pos = b[1] | b[2] << 8, i.address + 1
        elif b[0] == 0xC7 and len(b) >= 5:
            imm, pos = b[-2] | b[-1] << 8, i.address + len(b) - 2
        else:
            continue
        if pos in relset:
            continue
        ctx = ' | '.join(x.mnemonic + ' ' + x.op_str for x in ins[max(0, k - 3):k + 4])
        if ' ds' in ctx:  # a far pointer DS:imm is being built
            coderef.setdefault(imm, []).append(pos)

    out = []
    for off in sorted(set(coderef) | set(dataptr)):
        if not 0x100 <= off < len(img) - dsb or off in SKIP:
            continue
        raw = img[dsb + off:img.index(b'\0', dsb + off)]
        try:
            t = raw.decode('cp932')
        except UnicodeDecodeError:
            continue
        if len(raw) < 2 or not any(ord(c) > 0x7F for c in t) or '' in t:
            continue
        e = dict(off=off, len=len(raw), code=coderef.get(off, []), data=dataptr.get(off, []))
        if off in LAYOUT:
            e['layout'] = list(LAYOUT[off])
        if off in NOTES:
            e['note'] = NOTES[off]
        out.append(e)
    json.dump(dict(ds_paragraph=DS, strings=out), open(out_path, 'w'), indent=1)
    print(len(out), 'strings,', sum(e['len'] + 1 for e in out), 'bytes of pool')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
