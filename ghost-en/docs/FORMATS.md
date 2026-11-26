# Technical notes

Everything here was worked out by disassembling `RPG.EXE` (Turbo C++ 1990, large
model, LZEXE 0.91 packed). Offsets written `0xNNNN` in the *image* are relative to the
start of the unpacked load image (file offset minus the 0x1400-byte MZ header).

## Disk images

* `win31.hdi` (Anex86 HDI) and `YAHDI.nhd` (T98-Next NHD) each hold one PC-98 FAT16
  partition. The game that actually runs is `\GHOST` on `win31.hdi`; `YAHDI.nhd` only
  boots DOS (and has an unused copy of the game in its root).
* `tools/pc98hdd.py` reads and writes files in such images (`ls`, `extract`, `put`).

## Text rendering

* The message printer is at image `0x43FB`. It draws into graphics VRAM with the
  kanji ROM font, 8 px per half-width column, 24 px per line, faux-bold.
* Bytes with the Shift-JIS lead-byte flag are 2-byte, 2-column glyphs; everything else
  is a 1-column ANK glyph. So plain ASCII works out of the box.
* Control bytes: `#` newline, `_` wait for key then clear, `;` 200 ms pause,
  `@` clear, `\0` end.
* A window is a struct: far pointer to text, x, y, width, height, cursor column, row.
  The dialogue window (data segment `0x7267`) is x=20, width=40, height=4.
* When the cursor passes the right edge the printer wraps by itself (no word wrap), and
  when it passes the last row it waits for a key and clears. The build tool inserts
  explicit `#` at word boundaries so the automatic wrap never triggers mid-word.
* Formatted (sprintf) text on the status screen goes through a different path that
  converts ASCII to full-width glyphs.

## IVENTxx.DAT — events

```
file   := event* FF FF FF FF
event  := page page page page
page   := header(10 bytes, starts with FF FF) command*
```

A page ends where the next `FF FF` word begins (the engine scans byte by byte), so a
script may never contain two `FF` bytes in a row. Header: bytes 2-3 screen number,
byte 4 cell (x = n % 20, y = n / 20), byte 7 sprite, bytes 8-9 flags.

Commands (first byte is the ASCII opcode; lengths include it). There are no jump
offsets anywhere, so scripts can grow and shrink freely.

| Op | Len | Meaning |
|---|---|---|
| `*` | 2+n | text: length byte `n`, then `n` bytes. Shown, then waits for a key |
| `?` | 1 | Yes/No choice; on "No" skip to the matching `:` |
| `:` | 1 | else / end of choice |
| `b` | 2 | music (0-99) or sound effect (100+) |
| `c` | 3 | party member joins (+) / leaves (−) |
| `e` | 2 | screen effect / fade / wait (digit) |
| `f` | 3 | set (+) / clear (−) story flag |
| `g` | 3 | give / take money |
| `h` `m` | 3 | change HP / MP of the party |
| `i` | 3 | give (+) / take (−) item; skips the rest of the page if it fails |
| `j` | 4 | warp: screen (word), cell (byte) |
| `n` | 3 | inn, price |
| `s` | 5 | shop |
| `t` | 4 | set return point |
| `v` `w` | 2 | move/turn this event / the player (digit) |
| `x` | 3 | give experience |
| `y` | 2 | battle with enemy group n |
| `d` `p` | 1 | status effects on the party |
| `q` | 1 | end of game |

Word arguments use bit 15 as the sign ("−").  The whole file is read into a
0x7E00-byte buffer (`mov ax,7E00h` at image `0x3EDC` and `0x3EF3`, one for the file and
one for a working copy); the build patches both if a file gets bigger.

`python tools/ghost.py list IVENTxx` prints all of this in readable form.

## Name tables

| File | Record | Count | Layout |
|---|---|---|---|
| `ITEM.DAT` | 26 | 128 | name[16], NUL, 9 bytes of stats |
| `MAGIC.DAT` | 20 | 32 | name[16], NUL, cost, power |
| `ENEMY.DAT` | 40 | 160 | name[16], stats |
| `PLAYER.DAT` | 56 | 8 (+22 bytes) | name[16], stats |

Names are space-padded Shift-JIS, 16 bytes.

## RPG.EXE strings

* UI strings are NUL-terminated in the data segment (DGROUP = paragraph `0x1527`).
* `tools/exe_strings.json` lists every Japanese string with the image offsets of each
  instruction operand (`mov ax, offset str` next to a `push ds`) and each data-segment
  far pointer that refers to it. `tools/dev/find_exe_strings.py` regenerates it.
* At build time, strings whose translation differs from the original give up their
  bytes to a pool; the new strings are packed into that pool (identical strings and
  suffixes are shared) and every reference is re-pointed. Nothing else moves.
* Menus are single strings cut into fixed-width slices (`layout` in the JSON), so each
  slice keeps its width.
* Left alone on purpose: `ＤＡＴＡ１…４` (the code indexes into it), `savedata. `
  (the last character is overwritten with the slot number), file names, formats.

## Not done / ideas

* `OPNTITLE.DAT` is a raw 640×400 4-plane image (4 × 32,000 bytes) with the palette in
  `OPNTITLE.RGB`; a converter to and from PNG would allow an English logo.
* Status-screen label positions are constants in the code around image `0x73A1`; moving
  them would allow longer labels.
* The Japanese word order in battle messages could be changed by patching the print
  call sequences (image `0x9F00`–`0xD500`).
* Sound was not checked under the autoboot startup files (`AUTOBOOT` in `ghost.py`:
  a two-line `CONFIG.SYS` and `CD \GHOST` / `GHOST`); `GHOST.BAT` itself loads the
  music driver.
