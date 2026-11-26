#!/usr/bin/env python3
"""
pc98hdd.py - minimal reader/writer for FAT12/16 partitions inside PC-98 hard
disk images (.nhd "T98HDDIMAGE.R0" and .hdi).

Usage:
    python pc98hdd.py IMAGE ls [PATH]
    python pc98hdd.py IMAGE extract SRC_PATH DEST_DIR      (recursive)
    python pc98hdd.py IMAGE put LOCAL_FILE DEST_PATH       (overwrite or create a file)

Only what the localization pipeline needs is implemented: listing, recursive
extraction, and writing a file (existing file is freed and rewritten; new files
get a new directory entry). 8.3 names only. Filenames are decoded as cp932.
"""
import os
import struct
import sys


class Image:
    def __init__(self, path, writable=False):
        self.f = open(path, 'r+b' if writable else 'rb')
        head = self.f.read(0x200)
        if head[:15] == b'T98HDDIMAGE.R0\x00':
            self.hdr, self.cyls, self.heads, self.spt, self.ss = struct.unpack('<IIHHH', head[0x110:0x11E])
        else:  # HDI
            _, _, self.hdr, _, self.ss, self.spt, self.heads, self.cyls = struct.unpack('<8I', head[:32])

    def read(self, lba, n=1):
        self.f.seek(self.hdr + lba * self.ss)
        return self.f.read(n * self.ss)

    def write(self, lba, data):
        self.f.seek(self.hdr + lba * self.ss)
        self.f.write(data)

    def partitions(self):
        pt = self.read(1)
        out = []
        for i in range(16):
            e = pt[i * 32:(i + 1) * 32]
            if e[0] == 0 and e[1] == 0:
                continue
            s, h, c = e[8], e[9], struct.unpack('<H', e[10:12])[0]
            out.append(((c * self.heads + h) * self.spt + s, e[16:32].decode('cp932', 'replace').strip()))
        return out


class FAT:
    def __init__(self, img, part_lba):
        self.img = img
        self.base = part_lba
        b = img.read(part_lba)
        (self.bps, self.spc, self.rsv, self.nfat, self.nroot, tot16, _media, self.spf) = struct.unpack('<HBHBHHBH', b[11:24])
        tot32 = struct.unpack('<I', b[32:36])[0]
        self.total = tot16 or tot32
        self.k = self.bps // img.ss  # image sectors per FS sector
        self.root_lba = self.rsv + self.nfat * self.spf  # in FS sectors
        self.root_secs = (self.nroot * 32 + self.bps - 1) // self.bps
        self.data_lba = self.root_lba + self.root_secs
        self.nclus = (self.total - self.data_lba) // self.spc
        self.bits = 12 if self.nclus < 4085 else 16
        self.csize = self.bps * self.spc
        self.fat = bytearray(self._rd(self.rsv, self.spf))
        self.fat_dirty = False

    def _rd(self, sec, n):
        return self.img.read(self.base + sec * self.k, n * self.k)

    def _wr(self, sec, data):
        self.img.write(self.base + sec * self.k, data)

    # --- FAT table ---
    def get(self, c):
        if self.bits == 16:
            return struct.unpack_from('<H', self.fat, c * 2)[0]
        v = struct.unpack_from('<H', self.fat, c * 3 // 2)[0]
        return (v >> 4) if c & 1 else (v & 0xFFF)

    def set(self, c, v):
        self.fat_dirty = True
        if self.bits == 16:
            struct.pack_into('<H', self.fat, c * 2, v)
        else:
            o = c * 3 // 2
            cur = struct.unpack_from('<H', self.fat, o)[0]
            cur = (cur & 0x000F) | (v << 4) if c & 1 else (cur & 0xF000) | (v & 0xFFF)
            struct.pack_into('<H', self.fat, o, cur)

    def eoc(self, v):
        return v >= (0xFF8 if self.bits == 12 else 0xFFF8) or v < 2

    def chain(self, c):
        out = []
        while not self.eoc(c):
            out.append(c)
            c = self.get(c)
        return out

    def flush(self):
        if self.fat_dirty:
            for i in range(self.nfat):
                self._wr(self.rsv + i * self.spf, bytes(self.fat))
            self.fat_dirty = False

    def clus_sec(self, c):
        return self.data_lba + (c - 2) * self.spc

    def read_chain(self, c):
        return b''.join(self._rd(self.clus_sec(x), self.spc) for x in self.chain(c))

    # --- directories ---
    def _dir_raw(self, clus):
        """returns (bytes, list of (fs_sector) for each 32-byte slot's sector base)"""
        if clus == 0:
            return self._rd(self.root_lba, self.root_secs), [self.root_lba * self.bps]
        data = self.read_chain(clus)
        return data, [self.clus_sec(x) * self.bps for x in self.chain(clus)]

    def _slot_pos(self, clus, idx):
        """absolute byte offset (relative to partition) of dir slot idx"""
        off = idx * 32
        if clus == 0:
            return self.root_lba * self.bps + off
        ch = self.chain(clus)
        return self.clus_sec(ch[off // self.csize]) * self.bps + off % self.csize

    def listdir(self, clus=0):
        data, _ = self._dir_raw(clus)
        out = []
        for i in range(0, len(data), 32):
            e = data[i:i + 32]
            if e[0] == 0:
                break
            if e[0] == 0xE5 or e[11] & 0x08:
                continue
            raw = e[:11]
            if raw[0] == 0x05:
                raw = b'\xe5' + raw[1:]
            name = raw[:8].decode('cp932', 'replace').rstrip()
            ext = raw[8:11].decode('cp932', 'replace').rstrip()
            full = name + ('.' + ext if ext else '')
            if full in ('.', '..'):
                continue
            out.append(dict(name=full, attr=e[11], clus=struct.unpack('<H', e[26:28])[0],
                            size=struct.unpack('<I', e[28:32])[0], idx=i // 32, dir=bool(e[11] & 0x10),
                            time=struct.unpack('<HH', e[22:26])))
        return out

    def lookup(self, path):
        """returns (parent_cluster, entry or None for root)"""
        parts = [p for p in path.replace('\\', '/').split('/') if p]
        clus, ent, parent = 0, None, 0
        for p in parts:
            parent = clus
            ent = next((e for e in self.listdir(clus) if e['name'].upper() == p.upper()), None)
            if ent is None:
                return parent, None
            clus = ent['clus']
        return parent, ent

    def readfile(self, ent):
        return self.read_chain(ent['clus'])[:ent['size']]

    def walk(self, clus=0, prefix=''):
        for e in self.listdir(clus):
            p = prefix + '/' + e['name']
            yield p, e
            if e['dir']:
                yield from self.walk(e['clus'], p)

    # --- writing ---
    def _alloc(self, n):
        out = []
        c = 2
        while len(out) < n:
            if c >= self.nclus + 2:
                raise IOError('disk full')
            if self.get(c) == 0:
                out.append(c)
            c += 1
        end = 0xFFF if self.bits == 12 else 0xFFFF
        for a, b in zip(out, out[1:] + [end]):
            self.set(a, b)
        return out

    def _pwrite(self, byteoff, data):
        """write bytes at partition-relative byte offset (sector aligned regions)"""
        sec, rem = divmod(byteoff, self.bps)
        buf = bytearray(self._rd(sec, (rem + len(data) + self.bps - 1) // self.bps))
        buf[rem:rem + len(data)] = data
        self._wr(sec, bytes(buf))

    def writefile(self, path, data):
        parts = [p for p in path.replace('\\', '/').split('/') if p]
        parent, ent = self.lookup(path)
        if ent is None:
            # parent must exist
            if len(parts) > 1:
                _, pent = self.lookup('/'.join(parts[:-1]))
                if pent is None:
                    raise IOError('no such directory: ' + path)
                parent = pent['clus']
            raw, _ = self._dir_raw(parent)
            idx = next((i // 32 for i in range(0, len(raw), 32) if raw[i] in (0, 0xE5)), None)
            if idx is None:
                raise IOError('directory full (extending not implemented)')
            nm, _, ex = parts[-1].upper().partition('.')
            slot = bytearray(32)
            slot[:11] = nm.encode('cp932').ljust(8)[:8] + ex.encode('cp932').ljust(3)[:3]
            slot[11] = 0x20
            # keep the end-of-directory marker valid
            if raw[idx * 32] == 0 and (idx + 1) * 32 < len(raw):
                pass  # following slot is already 0
        else:
            if ent['dir']:
                raise IOError('is a directory')
            idx = ent['idx']
            for c in self.chain(ent['clus']):
                self.set(c, 0)
            raw, _ = self._dir_raw(parent)
            slot = bytearray(raw[idx * 32:idx * 32 + 32])
        n = (len(data) + self.csize - 1) // self.csize
        ch = self._alloc(n) if n else []
        for i, c in enumerate(ch):
            self._wr(self.clus_sec(c), data[i * self.csize:(i + 1) * self.csize].ljust(self.csize, b'\0'))
        struct.pack_into('<H', slot, 26, ch[0] if ch else 0)
        struct.pack_into('<I', slot, 28, len(data))
        self._pwrite(self._slot_pos(parent, idx), bytes(slot))
        self.flush()


def open_fs(path, writable=False, part=0):
    img = Image(path, writable)
    return FAT(img, img.partitions()[part][0])


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # Japanese file names
    except Exception:
        pass
    image, cmd, args = argv[1], argv[2], argv[3:]
    fs = open_fs(image, writable=(cmd == 'put'))
    if cmd == 'ls':
        _, ent = fs.lookup(args[0]) if args else (0, None)
        start = ent['clus'] if ent else 0
        for p, e in fs.walk(start, args[0].rstrip('/') if args else ''):
            print('%-9s %10d  %s' % ('<DIR>' if e['dir'] else '', e['size'], p))
    elif cmd == 'extract':
        src, dest = args
        _, ent = fs.lookup(src)
        if ent is None:
            raise SystemExit('not found: ' + src)
        if not ent['dir']:
            os.makedirs(dest, exist_ok=True)
            open(os.path.join(dest, ent['name']), 'wb').write(fs.readfile(ent))
            return 0
        for p, e in fs.walk(ent['clus'], ''):
            out = os.path.join(dest, *p.strip('/').split('/'))
            if e['dir']:
                os.makedirs(out, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(out), exist_ok=True)
                open(out, 'wb').write(fs.readfile(e))
    elif cmd == 'put':
        local, dest = args
        fs.writefile(dest, open(local, 'rb').read())
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
