After School Ghosts / 放課後の幽霊達  -  English version
=========================================================

A PC-98 RPG made with DANTE98 by Yuji Watanabe (from the Login Sofcom No.4 CD-ROM),
with an unofficial English translation.

HOW TO PLAY
-----------
1. Unzip the whole folder somewhere (keep the files together).
2. Open the "np21w-0.86-rev100" folder and run np21w.exe  (NOT the x64 one).
3. The game starts by itself after a few seconds.

If you get a blank screen or an error instead:
   Harddisk -> IDE #0 -> Open...  and choose win31_EN.hdi (one folder up),
   make sure IDE #1 is empty, then Emulate -> Reset.

CONTROLS
--------
   Arrow keys   move / move the cursor
   Enter        confirm, talk, advance text
   Esc          open the menu, cancel

Saving is in the menu under System -> Save Game.

ABOUT THE TRANSLATION
---------------------
The English text is a machine-assisted first draft that has not been reviewed by a
Japanese speaker. All dialogue, menus, battle messages and names are translated; the
title-screen logo and the save-slot labels are still in Japanese. Shops, inns, some
menus and the ending have not been play-tested in English yet, so expect rough edges.

WANT TO IMPROVE IT?
-------------------
The "ghost-en" folder contains everything needed to edit the translation and rebuild
the game: the text as .po files (script/), the tools (Python 3, nothing to install)
and documentation. Start with ghost-en/README.md. In short:

   edit ghost-en/script/*.po, close the emulator, then run
   python tools/ghost.py all        (from inside the ghost-en folder)

WHAT'S IN THIS FOLDER
---------------------
   win31_EN.hdi          hard disk image: MS-DOS 6.20 + the English game (boots into it)
   np21w-0.86-rev100/    Neko Project 21/W, the PC-98 emulator
   ghost-en/             the localization kit and the original Japanese game files
