# After School Ghosts (放課後の幽霊達) — English localization kit

A complete, rebuildable English translation of the PC-98 RPG *Hōkago no Yūreitachi*
(a DANTE98 game by Yuji Watanabe, from the *Login Sofcom No.4* CD-ROM), plus the tools
that produced it. Everything translatable lives in plain `.po` text files; one command
turns them back into a playable disk image.

**The translation in `script/` is a machine-assisted first draft made without a native
speaker's review.** Every entry is flagged `fuzzy` so you can see what has not been
checked by a human yet. Improving it is the whole point of this kit.

## Quick start

You need Python 3.8+ (standard library only). From this folder:

```
python tools/ghost.py all
```

That rebuilds the game files into `build/GHOST/` and installs them into
`../win31_EN.hdi` (created as a copy of `../win31.hdi` the first time; the original
image is never modified). Close the emulator first — it keeps the image locked.

To play: start `np21w.exe`, choose Harddisk → IDE #0 → Open… → **`win31_EN.hdi`**,
leave IDE #1 empty (Harddisk → IDE #1 → Remove), then Emulate → Reset. The game starts
by itself; no DOS commands are needed and `YAHDI.nhd` is not used.

The install step makes this possible by replacing `AUTOEXEC.BAT` and `CONFIG.SYS` on the
copy (the Windows 3.1 originals are kept on the image as `AUTOEXEC.W31` and
`CONFIG.W31`). Pass `--no-autoboot` to `install`/`all` to skip that. The old way —
`YAHDI.nhd` in IDE #0, `win31_EN.hdi` in IDE #1, then `B:`, `cd Ghost`, `GHOST` — still
works either way.

## Editing the translation

1. Open a file in `script/` with any text editor, or with a PO editor such as
   [Poedit](https://poedit.net/), OmegaT or Weblate.
2. Change the `msgstr`. `msgid` is the original Japanese (don't edit it; it is only
   there for reference and is regenerated from the game).
3. When you have checked an entry, remove its `#, fuzzy` line (Poedit: untick
   "Needs work"). The build uses fuzzy entries too; the flag is only a review marker.
4. Run `python tools/ghost.py all` and play.

An empty `msgstr` keeps the original Japanese for that string.

| File | Contents |
|---|---|
| `IVENTxx.po` | All dialogue and narration, one file per map group (1,422 strings) |
| `RPG.EXE.po` | Menus, battle and system messages (inside the program itself) |
| `ITEM.po`, `MAGIC.po`, `ENEMY.po`, `PLAYER.po` | Names, 16 columns max |

Other commands:

```
python tools/ghost.py stats           progress per file (translated / still fuzzy)
python tools/ghost.py list IVENT04    readable listing of an event file: script commands,
                                      Japanese and English side by side, in play order
python tools/ghost.py dump            regenerate the .po files from original/ (keeps your work)
python tools/ghost.py extract         re-extract original/ from ../win31.hdi
```

### Markup

| You write | Meaning |
|---|---|
| a line break in `msgstr` (`\n`) | forced line break |
| `{center}` at the start of a line | centre that line in the window (dialogue only) |
| `{wait}` | wait for a key, then clear the window |
| `{pause}` | short pause (used in battle messages) |
| `{clear}` | clear the window without waiting |

* **Dialogue (`IVENTxx.po`) is word-wrapped for you.** The window is 40 half-width
  columns × 4 lines. Text longer than 4 lines continues on a new page after a key
  press, exactly like the original. There is no length limit: long strings are split
  into several text commands automatically. Leading spaces are kept, so you can indent.
* A `msgstr` that starts with a blank line puts the text on the second row — the
  original uses this for the "other speaker" and for narration.
* **`RPG.EXE.po` is not wrapped**, and many entries are fragments that the game glues
  together with names and numbers at run time. Each one has a `#.` comment saying what
  comes before and after it. Keep leading/trailing spaces. Menu entries have a fixed
  maximum width (stated in the comment); the build stops with a clear message if you
  exceed one.
* The characters `# ; @ _` are control codes inside the game. If you type them, the
  build substitutes the full-width look-alikes (＃；＠＿) so they display normally.
  Curly quotes, `…` and `—` are converted to plain ASCII.
* Any character that exists in Shift-JIS can be used (so `「」★♪→` are fine); the
  build tells you if one can't. The PC-98 font shows `\` as `¥` and `~` as an overline.
* The status screen draws its numbers and labels double-width; see the comments on
  those entries.

### Limits the build checks for you

* Names: 16 columns.
* Menu slots: fixed width per item.
* UI string pool in `RPG.EXE`: about 2.7 KB in total (currently ~80% used). Identical
  strings are stored once, so reuse wording where you can.
* Event files: the original program allocates 32,256 bytes per file. If a translated
  file grows beyond that, the build enlarges the buffer inside `RPG.EXE` automatically
  and tells you so.

## What was changed in the game

* `IVENTxx.DAT`, `ITEM.DAT`, `MAGIC.DAT`, `ENEMY.DAT`, `PLAYER.DAT`: text only.
  Translated names are padded with NUL bytes instead of spaces, so that battle messages
  read `Aoki attacks!` rather than `Aoki            attacks!` (`NAME_PAD` in `ghost.py`).
* `RPG.EXE`: unpacked (it was LZEXE-compressed), UI strings replaced and re-pointed.
  No program logic is altered. The engine already supported half-width text.
* Not translated: the title-screen picture (`OPNTITLE.DAT`, the logo is a bitmap),
  the save-slot labels `ＤＡＴＡ１…４`, and `EDINIT.EXE`/DOS error messages.

## Translation notes and judgment calls

Things a reviewer may want to revisit:

* **Names.** 青木 Aoki, 美広 **Bihiro** (the game itself gives the reading ビヒロ),
  千歳 Chitose, 伊達 Date, 若月みおみ Miomi Wakatsuki, 学長 "the Principal"
  (若月きりゆ, Kiriyu Wakatsuki), 根岸 Negishi, 花子 Hanako. The author's name
  渡辺裕司 is rendered "Yuji Watanabe"; the reading of the given name is a guess.
* **Terms.** 法力 "dharma power", 真言 "mantra", 陀羅尼 "dharani", 九字 "Kuji",
  剣印 "sword mudra", 餓鬼 "hungry ghost", 浮遊霊 "wandering spirit", 背後霊団
  "guardian spirit band", 結界 "barrier", 祖霊 "ancestral spirit", 霊撮隊
  "ghost-filming crew" / "Ghost Crew" (a TV show), 審神 "saniwa", 幽邪鬼 "yujaki",
  冥邪鬼 "Dark Demon", 霊験 "Miracle" (spell family).
* Mantras are romanised from the kana (e.g. *Namaku samanda bazara dan kan*).
* Speaker labels follow the original (`Aoki: …`). In two places the original label
  does not match who is obviously speaking (IVENT09 e155, IVENT13 e026 t21); the
  English uses the speaker that makes sense.
* Miomi calls the Principal "Grandma" but introduces herself as her "only daughter";
  this contradiction is in the Japanese and was kept.
* Hanako says mantras reached Japan "in the Muromachi period" — the original's
  mistake (Kūkai lived in the Heian period), kept as written.
* Battle messages are built from fragments, so some are phrased to fit the original
  word order: `Name: 12 damage!`, `Name casts / Spell!`, `Item is used!`.
* Spell and item names are abbreviated to fit 16 columns (`Exorcism(Revive)`).
* The item list contains many generic DANTE98 template items (Excalibur etc.) that
  the game never hands out; they are translated anyway.

## Folder layout

```
script/      the translation (.po) — the only thing translators need to touch
tools/       ghost.py (main tool), pc98hdd.py (disk images), unlzexe.py, exe_strings.json
tools/dev/   find_exe_strings.py — regenerates exe_strings.json (needs `pip install capstone`)
docs/        FORMATS.md — file formats and how the engine draws text
original/    untouched Japanese game files extracted from the disk image
build/       output of the last build
```

See `docs/FORMATS.md` if you want to go further (script commands, patching more of the
program, replacing the title graphic).
