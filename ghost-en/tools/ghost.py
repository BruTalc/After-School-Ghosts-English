#!/usr/bin/env python3
"""
ghost.py - localization toolchain for "Houkago no Yuureitachi" (After School Ghosts, PC-98).

    python tools/ghost.py extract   pull the Japanese game files out of the disk image -> original/
    python tools/ghost.py dump      original/ -> script/*.po   (keeps translations already in the .po files)
    python tools/ghost.py build     original/ + script/*.po -> build/GHOST/
    python tools/ghost.py install   copy build/GHOST/* into a COPY of the disk image (win31_EN.hdi)
    python tools/ghost.py all       build + install
    python tools/ghost.py stats     translation progress per file
    python tools/ghost.py list IVENT00    readable listing of an event file (script commands + text)

Only the Python 3 standard library is needed.  See README.md for the text markup.
"""
import argparse
import glob
import json
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import pc98hdd  # noqa: E402
import unlzexe  # noqa: E402

ORIG = os.path.join(ROOT, 'original')
SCRIPT = os.path.join(ROOT, 'script')
BUILD = os.path.join(ROOT, 'build', 'GHOST')
DEFAULT_SRC_IMAGE = os.path.join(os.path.dirname(ROOT), 'win31.hdi')
DEFAULT_DST_IMAGE = os.path.join(os.path.dirname(ROOT), 'win31_EN.hdi')
GAME_DIR = 'GHOST'  # directory of the game inside the image

# ----------------------------------------------------------------------------
# game constants (found by disassembling RPG.EXE - see docs/FORMATS.md)
# ----------------------------------------------------------------------------
DIALOG_COLS = 40          # dialogue window width in half-width columns
DIALOG_ROWS = 4           # lines per page
TEXT_CMD_MAX = 250        # a '*' command holds at most 255 bytes of text
EVENT_BUF_DEFAULT = 0x7E00  # malloc size for an IVENT file in the original EXE
EVENT_BUF_PATCH = (0x3EDD, 0x3EF4)  # image offsets of the two "mov ax,7E00h" operands

NAME_PAD = bytes(1)     # padding for translated names (the Japanese originals are space padded)
# name tables: file -> (record size, record count, name field size)
TABLES = {
    'ITEM.DAT': (26, 128, 16),
    'MAGIC.DAT': (20, 32, 16),
    'ENEMY.DAT': (40, 160, 16),
    'PLAYER.DAT': (56, 8, 16),
}

# event script commands: opcode -> (total length in bytes, description)
CMD_LEN = {':': 1, '?': 1, 'd': 1, 'p': 1, 'q': 1,
           'b': 2, 'e': 2, 'v': 2, 'w': 2, 'y': 2,
           'j': 4, 't': 4, 's': 5}
CMD_DOC = {
    '*': 'text', '?': 'yes/no choice (commands up to ":" run on Yes)', ':': 'else / end of choice',
    'b': 'music/sound', 'c': 'party member join(+)/leave(-)', 'd': 'poison party?', 'e': 'screen effect',
    'f': 'set(+)/clear(-) story flag', 'g': 'give/take money', 'h': 'change HP', 'm': 'change MP',
    'i': 'give(+)/take(-) item', 'j': 'warp to map,cell', 'n': 'inn (price)', 'p': 'status effect',
    'q': 'quit / game over', 's': 'shop', 't': 'set return point', 'v': 'move/turn this event',
    'w': 'move/turn player', 'x': 'give exp', 'y': 'battle',
}

CTRL_TO_TAG = {'#': '\n', '_': '{wait}', ';': '{pause}', '@': '{clear}'}
TAG_TO_CTRL = {'{wait}': '_', '{pause}': ';', '{clear}': '@'}
FULLWIDTH = {'#': '＃', ';': '；', '@': '＠', '_': '＿'}
TYPO = {'\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2026': '...',
        '\u2014': '--', '\u2013': '-', '\u00a0': ' '}


class BuildError(Exception):
    pass


# ----------------------------------------------------------------------------
# PO files (minimal reader/writer, compatible with Poedit / Weblate / OmegaT)
# ----------------------------------------------------------------------------
def po_escape(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\t', '\\t')


def po_unescape(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            out.append({'n': '\n', 't': '\t', 'r': '\r'}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def po_string(key, s):
    parts = s.split('\n')
    if len(parts) == 1:
        return '%s "%s"\n' % (key, po_escape(s))
    lines = ['%s ""\n' % key]
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        if last and p == '':
            break
        lines.append('"%s%s"\n' % (po_escape(p), '' if last else '\\n'))
    return ''.join(lines)


def po_read(path):
    """returns {msgctxt: dict(msgid, msgstr, fuzzy, tcomments)}"""
    entries = {}
    if not os.path.exists(path):
        return entries
    cur, field = None, None

    def flush():
        if cur and cur.get('msgctxt') is not None:
            entries[cur['msgctxt']] = cur

    def new():
        return dict(msgctxt=None, msgid='', msgstr='', fuzzy=False, tcomments=[])

    cur = new()
    for line in open(path, encoding='utf-8-sig'):
        line = line.rstrip('\n')
        if not line.strip():
            flush()
            cur, field = new(), None
        elif line.startswith('#,'):
            cur['fuzzy'] = 'fuzzy' in line
        elif line.startswith('#.') or line.startswith('#:') or line.startswith('#|'):
            pass
        elif line.startswith('#'):
            cur['tcomments'].append(line[1:].lstrip(' '))
        elif line.startswith('"'):
            if field:
                cur[field] += po_unescape(line.strip()[1:-1])
        else:
            key, _, rest = line.partition(' ')
            if key in ('msgctxt', 'msgid', 'msgstr'):
                field = key
                cur[key] = po_unescape(rest.strip()[1:-1])
    flush()
    return entries


def po_write(path, title, items, old):
    """items: list of dict(id, msgid, comments=[...]); old: result of po_read (translations kept)"""
    out = ['# %s\n' % title,
           '# Edit the msgstr lines. Leave msgstr empty to keep the original Japanese.\n',
           '# "fuzzy" = unreviewed draft (still used by the build). See README.md for markup.\n',
           'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
           '"Content-Transfer-Encoding: 8bit\\n"\n"Language: en\\n"\n\n']
    for it in items:
        o = old.get(it['id'], {})
        for c in o.get('tcomments', []):
            out.append('# %s\n' % c if c else '#\n')
        for c in it.get('comments', []):
            out.append('#. %s\n' % c)
        if o.get('fuzzy') and o.get('msgstr'):
            out.append('#, fuzzy\n')
        out.append(po_string('msgctxt', it['id']))
        out.append(po_string('msgid', it['msgid']))
        out.append(po_string('msgstr', o.get('msgstr', '')))
        out.append('\n')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(out))


# ----------------------------------------------------------------------------
# text codec
# ----------------------------------------------------------------------------
def decode_text(raw):
    """game bytes -> editable text with markup"""
    s = raw.decode('cp932')
    if '\r\n' in s:  # plain DOS string, no control codes
        return s.replace('\r\n', '\n')
    return ''.join(CTRL_TO_TAG.get(c, c) for c in s)


def _cells(s):
    """display width in half-width columns (control tags are zero width)"""
    for t in TAG_TO_CTRL:
        s = s.replace(t, '')
    return sum(2 if len(c.encode('cp932')) == 2 else 1 for c in s)


def _normalize(text, ident):
    for a, b in TYPO.items():
        text = text.replace(a, b)
    # literal control characters -> full-width look-alikes (tags are protected first)
    hold = {}
    for i, t in enumerate(TAG_TO_CTRL):
        hold[chr(0xE000 + i)] = t
        text = text.replace(t, chr(0xE000 + i))
    text = ''.join(FULLWIDTH.get(c, c) for c in text)
    for k, t in hold.items():
        text = text.replace(k, t)
    try:
        text.replace('\n', '').encode('cp932')
    except UnicodeEncodeError as e:
        raise BuildError('%s: character %r cannot be shown by the game (not in Shift-JIS)' % (ident, e.object[e.start]))
    return text


def _to_bytes(s):
    for t, c in TAG_TO_CTRL.items():
        s = s.replace(t, c)
    return s.replace('\n', '#').encode('cp932')


def encode_plain(text, ident, crlf=False):
    """no wrapping: UI strings and names"""
    if crlf:
        return text.replace('\n', '\r\n').encode('cp932')
    return _to_bytes(_normalize(text, ident))


def wrap_line(line, width):
    """word-wrap one hard line into display lines (leading spaces are kept)"""
    indent = len(line) - len(line.lstrip(' '))
    lines, cur, empty = [], ' ' * indent, True
    for w in line.strip(' ').split(' '):
        cand = cur + w if empty else cur + ' ' + w
        if _cells(cand) > width and not empty:
            lines.append(cur)
            cand = w
        cur, empty = cand, False
        while _cells(cur) > width:  # a single word longer than the window
            cut = acc = 0
            for ch in cur:
                if acc + _cells(ch) > width:
                    break
                acc += _cells(ch)
                cut += 1
            lines.append(cur[:cut])
            cur = cur[cut:]
    lines.append(cur)
    return [ln.rstrip(' ') for ln in lines]


def encode_dialogue(text, ident):
    """wrap to the dialogue window and split into one or more '*' command payloads"""
    text = _normalize(text, ident)
    # segments separated by {wait}/{clear}; each segment starts on a fresh window
    segs, seps, buf, i = [], [], '', 0
    while i < len(text):
        for t in ('{wait}', '{clear}'):
            if text.startswith(t, i):
                segs.append(buf)
                seps.append(t)
                buf = ''
                i += len(t)
                break
        else:
            buf += text[i]
            i += 1
    segs.append(buf)
    if seps and segs[-1] == '':  # trailing {wait}: the engine waits anyway
        segs.pop()
        last_sep = seps.pop()
    else:
        last_sep = None
    # units: (bytes, separator that follows inside one command, can_cut_after)
    units = []
    for si, seg in enumerate(segs):
        lines = []
        for hard in seg.split('\n'):
            if hard.startswith('{center}'):
                for ln in wrap_line(hard[len('{center}'):].strip(' '), DIALOG_COLS):
                    lines.append(' ' * ((DIALOG_COLS - _cells(ln)) // 2) + ln)
            else:
                lines.extend(wrap_line(hard, DIALOG_COLS))
        pages = [lines[k:k + DIALOG_ROWS] for k in range(0, len(lines), DIALOG_ROWS)] or [[]]
        for pi, pg in enumerate(pages):
            raw = _to_bytes('\n'.join(pg))
            if pi < len(pages) - 1:
                units.append((raw, b'#', True))
            elif si < len(segs) - 1:
                sep = seps[si]
                units.append((raw, _to_bytes(sep), sep == '{wait}'))
            else:
                units.append((raw, _to_bytes(last_sep) if last_sep == '{clear}' else b'', True))
    chunks, cur = [], b''
    for n, (raw, sep, cut) in enumerate(units):
        if len(raw) > TEXT_CMD_MAX:
            raise BuildError('%s: one page is longer than %d bytes' % (ident, TEXT_CMD_MAX))
        piece = raw + (sep if n < len(units) - 1 or sep == b'@' else b'')
        if len(cur) + len(piece) > TEXT_CMD_MAX:
            prev_cut = units[n - 1][2] if n else True
            if not cur or not prev_cut:
                raise BuildError('%s: text too long around a {clear}; use {wait} instead' % ident)
            # drop the separator that ended the previous unit: the command boundary replaces it
            psep = units[n - 1][1]
            if psep and cur.endswith(psep):
                cur = cur[:-len(psep)]
            chunks.append(cur)
            cur = b''
        cur += piece
    chunks.append(cur)
    return chunks


# ----------------------------------------------------------------------------
# IVENTxx.DAT (event scripts)
# ----------------------------------------------------------------------------
def ivent_parse(data):
    """-> (events, tail). event = list of 4 pages; page = (header10, [(op, payload)])"""
    events, si = [], 0
    while struct.unpack_from('<H', data, si + 2)[0] != 0xFFFF:
        pages = []
        for _ in range(4):
            start = si
            si += 10
            while struct.unpack_from('<H', data, si)[0] != 0xFFFF:
                si += 1
            cmds, pc = [], start + 10
            while pc < si:
                op = chr(data[pc])
                if op == '*':
                    n = data[pc + 1]
                    cmds.append((op, data[pc + 2:pc + 2 + n]))
                    pc += 2 + n
                else:
                    ln = CMD_LEN.get(op, 3)
                    cmds.append((op, data[pc + 1:pc + ln]))
                    pc += ln
            if pc != si:
                raise BuildError('event script does not parse cleanly at offset %d' % start)
            pages.append((data[start:start + 10], cmds))
        events.append(pages)
    return events, data[si:]


def ivent_texts(stem, events):
    """yield (id, event index, page index, raw text, header) for every text command"""
    for ei, pages in enumerate(events):
        for pi, (hdr, cmds) in enumerate(pages):
            n = 0
            for op, payload in cmds:
                if op == '*':
                    yield '%s/e%03d/p%d/t%02d' % (stem, ei, pi, n), ei, pi, payload, hdr
                    n += 1


def ivent_build(stem, data, po):
    events, tail = ivent_parse(data)
    out = bytearray()
    for ei, pages in enumerate(events):
        for pi, (hdr, cmds) in enumerate(pages):
            out += hdr
            n = 0
            for op, payload in cmds:
                if op != '*':
                    out += op.encode() + payload
                    continue
                ident = '%s/e%03d/p%d/t%02d' % (stem, ei, pi, n)
                n += 1
                tr = po.get(ident, {}).get('msgstr', '')
                chunks = encode_dialogue(tr, ident) if tr else [payload]
                for c in chunks:
                    out += b'*' + bytes([len(c)]) + c
    out += tail
    # safety: the result must parse back to the same structure
    ev2, _ = ivent_parse(bytes(out))
    if len(ev2) != len(events):
        raise BuildError('%s: rebuilt file has a different event count (text produced an FFFF marker?)' % stem)
    return bytes(out)


def cmd_list(args):
    stem = args.file.upper().replace('.DAT', '')
    data = open(os.path.join(ORIG, stem + '.DAT'), 'rb').read()
    po = po_read(os.path.join(SCRIPT, stem + '.po'))
    events, _ = ivent_parse(data)
    for ei, pages in enumerate(events):
        for pi, (hdr, cmds) in enumerate(pages):
            if not cmds:
                continue
            scr, cell = struct.unpack_from('<H', hdr, 2)[0], hdr[4]
            print('--- event %d page %d | screen %d cell (%d,%d) | hdr %s' % (ei, pi, scr, cell % 20, cell // 20, hdr.hex()))
            n = 0
            for op, payload in cmds:
                if op == '*':
                    ident = '%s/e%03d/p%d/t%02d' % (stem, ei, pi, n)
                    n += 1
                    print('  * [%s]' % ident)
                    for ln in decode_text(payload).split('\n'):
                        print('      JP| ' + ln)
                    for ln in po.get(ident, {}).get('msgstr', '').split('\n'):
                        if ln:
                            print('      EN| ' + ln)
                elif len(payload) == 2 and op in 'cfghimnx':
                    v = struct.unpack('<H', payload)[0]
                    print('  %s %s%d   ; %s' % (op, '-' if v & 0x8000 else '+', v & 0x7FFF, CMD_DOC.get(op, '?')))
                else:
                    print('  %s %s   ; %s' % (op, payload.hex(), CMD_DOC.get(op, '?')))


# ----------------------------------------------------------------------------
# RPG.EXE
# ----------------------------------------------------------------------------
def exe_load():
    meta = json.load(open(os.path.join(HERE, 'exe_strings.json')))
    exe = bytearray(unlzexe.unlzexe(open(os.path.join(ORIG, 'RPG.EXE'), 'rb').read()))
    hsize = struct.unpack_from('<H', exe, 8)[0] * 16
    return meta, exe, hsize


def exe_items(meta, exe, hsize):
    """PO items for the EXE strings"""
    dsb = hsize + meta['ds_paragraph'] * 16
    items = []
    for e in meta['strings']:
        raw = bytes(exe[dsb + e['off']:dsb + e['off'] + e['len']])
        base = 'RPG.EXE/%04X' % e['off']
        note = [e['note']] if e.get('note') else []
        if 'layout' in e:
            cnt, w = e['layout']
            for i in range(cnt):
                items.append(dict(id='%s[%d]' % (base, i), msgid=raw[i * w:(i + 1) * w].decode('cp932').rstrip('\u3000 '),
                                  comments=note + ['menu item %d of %d - at most %d columns' % (i + 1, cnt, w)], raw=raw))
        else:
            items.append(dict(id=base, msgid=decode_text(raw), comments=note, raw=raw))
    return items


def exe_build(po, event_buf_needed):
    meta, exe, hsize = exe_load()
    dsb = hsize + meta['ds_paragraph'] * 16
    report = []
    new = {}  # off -> new bytes (without NUL)
    for e in meta['strings']:
        off = e['off']
        raw = bytes(exe[dsb + off:dsb + off + e['len']])
        base = 'RPG.EXE/%04X' % off
        if 'layout' in e:
            cnt, w = e['layout']
            parts = []
            for i in range(cnt):
                ident = '%s[%d]' % (base, i)
                tr = po.get(ident, {}).get('msgstr', '')
                if tr:
                    b = encode_plain(tr, ident)
                    if len(b) > w:
                        raise BuildError('%s: "%s" is %d columns, the menu slot holds %d' % (ident, tr, len(b), w))
                    parts.append(b.ljust(w))
                else:
                    parts.append(raw[i * w:(i + 1) * w])
            new[off] = b''.join(parts)
        else:
            tr = po.get(base, {}).get('msgstr', '')
            new[off] = encode_plain(tr, base, crlf=b'\r\n' in raw) if tr else raw
    # --- allocate: unchanged strings stay put, changed ones are packed into the freed space
    placed = {}   # off -> new offset
    content = {}  # bytes -> offset (for sharing identical strings / suffixes)
    free = []
    for e in meta['strings']:
        off = e['off']
        if new[off] == bytes(exe[dsb + off:dsb + off + e['len']]):
            placed[off] = off
            content.setdefault(new[off], off)
        else:
            free.append([off, off + e['len'] + 1])
    free.sort()
    merged = []
    for a, b in free:
        if merged and merged[-1][1] == a:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    for a, b in merged:
        exe[dsb + a:dsb + b] = bytes(b - a)
    avail = sum(b - a for a, b in merged)
    todo = sorted((o for o in new if o not in placed), key=lambda o: -len(new[o]))
    need = 0
    for off in todo:
        b = new[off]
        hit = next((c for c in content if c.endswith(b)), None)
        if hit is not None:
            placed[off] = content[hit] + len(hit) - len(b)
            continue
        need += len(b) + 1
        slot = next((m for m in merged if m[1] - m[0] >= len(b) + 1), None)
        if slot is None:
            raise BuildError('RPG.EXE: translated UI strings do not fit in the string pool '
                             '(%d bytes free in total, fragmented). Shorten some RPG.EXE.po entries.' % avail)
        exe[dsb + slot[0]:dsb + slot[0] + len(b)] = b
        placed[off] = slot[0]
        content[b] = slot[0]
        slot[0] += len(b) + 1
    for e in meta['strings']:
        tgt = struct.pack('<H', placed[e['off']])
        old = struct.pack('<H', e['off'])
        for pos in e['code']:
            assert exe[hsize + pos:hsize + pos + 2] == old
            exe[hsize + pos:hsize + pos + 2] = tgt
        for pos in e['data']:
            assert exe[dsb + pos:dsb + pos + 2] == old
            exe[dsb + pos:dsb + pos + 2] = tgt
    report.append('RPG.EXE: UI string pool %d / %d bytes used' % (need, avail))
    # --- event buffer
    if event_buf_needed > EVENT_BUF_DEFAULT:
        size = (event_buf_needed + 0x3FF) & ~0x3FF
        if size > 0xF000:
            raise BuildError('an IVENT file is larger than 60 KB - far too big')
        for pos in EVENT_BUF_PATCH:
            assert exe[hsize + pos:hsize + pos + 2] == struct.pack('<H', EVENT_BUF_DEFAULT)
            exe[hsize + pos:hsize + pos + 2] = struct.pack('<H', size)
        report.append('RPG.EXE: event buffers enlarged to %d bytes (largest IVENT file is %d)' % (size, event_buf_needed))
    return bytes(exe), report


# ----------------------------------------------------------------------------
# name tables
# ----------------------------------------------------------------------------
def table_items(fn, data):
    rec, cnt, w = TABLES[fn]
    stem = fn.split('.')[0]
    for i in range(cnt):
        raw = data[i * rec:i * rec + w]
        if len(raw) < w:
            break
        try:
            name = raw.decode('cp932').rstrip(' ')
        except UnicodeDecodeError:
            continue
        if name:
            yield dict(id='%s/%03d' % (stem, i), msgid=name, comments=['at most %d columns' % w], index=i)


def table_build(fn, data, po):
    rec, cnt, w = TABLES[fn]
    out = bytearray(data)
    for it in table_items(fn, data):
        tr = po.get(it['id'], {}).get('msgstr', '')
        if not tr:
            continue
        b = encode_plain(tr, it['id'])
        if len(b) > w:
            raise BuildError('%s: "%s" is %d columns, the limit is %d' % (it['id'], tr, len(b), w))
        # NUL padding (not spaces) so that messages read "Aoki attacks!" and not "Aoki            attacks!"
        out[it['index'] * rec:it['index'] * rec + w] = b.ljust(w, NAME_PAD)
    return bytes(out)


# ----------------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------------
def ivent_files():
    return sorted(glob.glob(os.path.join(ORIG, 'IVENT[0-9][0-9].DAT')))


def cmd_extract(args):
    fs = pc98hdd.open_fs(args.image)
    _, ent = fs.lookup(GAME_DIR)
    if ent is None:
        raise SystemExit('no \\%s directory in %s' % (GAME_DIR, args.image))
    os.makedirs(ORIG, exist_ok=True)
    n = 0
    for e in fs.listdir(ent['clus']):
        if not e['dir'] and not e['name'].upper().startswith('SAVEDATA'):
            open(os.path.join(ORIG, e['name']), 'wb').write(fs.readfile(e))
            n += 1
    print('extracted %d files to %s' % (n, ORIG))


def collect_items():
    """-> {po file name: (title, [items])} for everything translatable in original/"""
    out = {}
    for path in ivent_files():
        stem = os.path.basename(path)[:-4]
        events, _ = ivent_parse(open(path, 'rb').read())
        items = []
        for ident, ei, pi, raw, hdr in ivent_texts(stem, events):
            scr, cell = struct.unpack_from('<H', hdr, 2)[0], hdr[4]
            items.append(dict(id=ident, msgid=decode_text(raw),
                              comments=['event %d, page %d | screen %d, cell (%d,%d)' % (ei, pi, scr, cell % 20, cell // 20)]))
        if items:
            out[stem + '.po'] = ('%s.DAT - dialogue. Window: %d columns x %d lines, wrapped automatically.'
                                 % (stem, DIALOG_COLS, DIALOG_ROWS), items)
    for fn in TABLES:
        items = list(table_items(fn, open(os.path.join(ORIG, fn), 'rb').read()))
        out[fn.split('.')[0] + '.po'] = ('%s - names, at most %d half-width columns each.' % (fn, TABLES[fn][2]), items)
    meta, exe, hsize = exe_load()
    out['RPG.EXE.po'] = ('RPG.EXE - menus, battle and system messages. NOT wrapped automatically.',
                         exe_items(meta, exe, hsize))
    return out


def cmd_dump(args):
    for name, (title, items) in collect_items().items():
        dst = os.path.join(SCRIPT, name)
        po_write(dst, title, items, po_read(dst))
        print('%-12s %4d strings' % (name, len(items)))


def cmd_build(args):
    os.makedirs(BUILD, exist_ok=True)
    errors, report, biggest = [], [], 0
    for path in ivent_files():
        stem = os.path.basename(path)[:-4]
        po = po_read(os.path.join(SCRIPT, stem + '.po'))
        data = open(path, 'rb').read()
        try:
            out = ivent_build(stem, data, po)
        except BuildError as e:
            errors.append(str(e))
            continue
        biggest = max(biggest, len(out))
        open(os.path.join(BUILD, stem + '.DAT'), 'wb').write(out)
        if out != data:
            report.append('%s.DAT: %d -> %d bytes' % (stem, len(data), len(out)))
    for fn in TABLES:
        po = po_read(os.path.join(SCRIPT, fn.split('.')[0] + '.po'))
        try:
            open(os.path.join(BUILD, fn), 'wb').write(table_build(fn, open(os.path.join(ORIG, fn), 'rb').read(), po))
        except BuildError as e:
            errors.append(str(e))
    try:
        exe, rep = exe_build(po_read(os.path.join(SCRIPT, 'RPG.EXE.po')), biggest)
        open(os.path.join(BUILD, 'RPG.EXE'), 'wb').write(exe)
        report += rep
    except BuildError as e:
        errors.append(str(e))
    for r in report:
        print(r)
    if errors:
        print('\n%d ERROR(S):' % len(errors))
        for e in errors:
            print('  ' + e)
        raise SystemExit(1)
    print('build OK -> ' + BUILD)


def cmd_install(args):
    if not os.path.exists(args.image):
        print('creating %s from %s ...' % (args.image, args.source))
        shutil.copyfile(args.source, args.image)
    try:
        fs = pc98hdd.open_fs(args.image, writable=True)
    except PermissionError:
        raise SystemExit('cannot write to %s - close the emulator first (it keeps the disk image locked)' % args.image)
    n = 0
    for path in sorted(glob.glob(os.path.join(BUILD, '*'))):
        name = os.path.basename(path)
        data = open(path, 'rb').read()
        _, ent = fs.lookup(GAME_DIR + '/' + name)
        if ent is not None and fs.readfile(ent) == data:
            continue
        fs.writefile(GAME_DIR + '/' + name, data)
        n += 1
    print('installed %d changed file(s) into %s' % (n, args.image))
    if not args.no_autoboot:
        autoboot(fs, args.image)


# Startup files that make the image boot straight into the game when it is the first
# hard disk.  The image's own files are kept as AUTOEXEC.W31 / CONFIG.W31.
AUTOBOOT = {
    'AUTOEXEC.BAT': b'@ECHO OFF\r\nCD \\GHOST\r\nGHOST\r\n',
    'CONFIG.SYS': b'FILES=30\r\nBUFFERS=20\r\n',
}


def autoboot(fs, image):
    changed = False
    for name, data in AUTOBOOT.items():
        _, ent = fs.lookup(name)
        cur = fs.readfile(ent) if ent else None
        if cur == data:
            continue
        backup = name.split('.')[0] + '.W31'
        if cur is not None and fs.lookup(backup)[1] is None:
            fs.writefile(backup, cur)
        fs.writefile(name, data)
        changed = True
    if changed:
        print('autoboot: %s now starts the game by itself when it is hard disk #0' % image)


def cmd_stats(args):
    tot = done = fz = 0
    for path in sorted(glob.glob(os.path.join(SCRIPT, '*.po'))):
        po = po_read(path)
        d = sum(1 for e in po.values() if e['msgstr'])
        f = sum(1 for e in po.values() if e['msgstr'] and e['fuzzy'])
        print('%-14s %4d / %4d translated, %4d still marked fuzzy (unreviewed)' % (os.path.basename(path), d, len(po), f))
        tot += len(po)
        done += d
        fz += f
    print('%-14s %4d / %4d translated, %4d fuzzy' % ('TOTAL', done, tot, fz))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('extract')
    p.add_argument('--image', default=DEFAULT_SRC_IMAGE)
    sub.add_parser('dump')
    sub.add_parser('build')
    for name in ('install', 'all'):
        p = sub.add_parser(name)
        p.add_argument('--image', default=DEFAULT_DST_IMAGE, help='image to patch (created as a copy of --source if missing)')
        p.add_argument('--source', default=DEFAULT_SRC_IMAGE)
        p.add_argument('--no-autoboot', action='store_true',
                       help="leave the image's AUTOEXEC.BAT / CONFIG.SYS alone (it then boots into Windows 3.1 as before)")
    sub.add_parser('stats')
    p = sub.add_parser('list')
    p.add_argument('file')
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass
    if args.cmd == 'all':
        cmd_build(args)
        cmd_install(args)
    else:
        globals()['cmd_' + args.cmd](args)


if __name__ == '__main__':
    main()
