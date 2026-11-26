After School Ghosts / 放課後の幽霊達  -  English version
=========================================================

A PC-98 RPG made with DANTE98 by Yuji Watanabe (from the Login Sofcom No.4 CD-ROM),
with an unofficial English translation.

HOW TO PLAY (WINDOWS)
--------------------
1. Make sure you EXTRACTED the zip: right-click it, choose "Extract All...", then
   click Extract. The game won't run from inside the zip.

2. Double-click:   Play After School Ghosts
   (It may show as "Play After School Ghosts.cmd", type "Windows Command Script".)

3. If Windows shows a warning the first time:
     "Open File - Security Warning"   -> click Run
     "Windows protected your PC"      -> click More info, then Run anyway

4. The game starts by itself after a few seconds. You don't need to type anything.

Next time, just double-click "Play After School Ghosts" again.

WINDOW SIZE: the first time, the window is sized to fit your screen. To change it,
right-click the emulator's title bar and pick a size, such as "1280x800(x2)". Your
choice is remembered. For fullscreen, use Screen -> Fullscreen.

IF SOMETHING GOES WRONG
   "...run from inside the zip"       extract the zip first (step 1)
   "...disk image/emulator is missing" extract the zip again; keep the files together
   "Could not save the emulator settings"
                                      move the folder to Documents or the Desktop
   "The game is already running"      look for the Neko Project 21/W window

To start the emulator by hand instead: run np21w-0.86-rev100\np21w.exe, then
   Harddisk -> IDE #0 -> Open...  and choose win31_EN.hdi (one folder up),
   make sure IDE #1 is empty, then Emulate -> Reset.

CONTROLS
--------
   Arrow keys   move / move the cursor
   Enter        confirm, talk, advance text
   Esc          open the menu, cancel

Saving is in the menu under System -> Save Game.

CREDITS
-------
   MarshSMT and VmigoStation   for leading the effort to preserve this game
   Yuji Watanabe               creator of After School Ghosts
   Neko Project 21/W           the PC-98 emulator (licences in np21w-0.86-rev100\LICENSES)

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
   Play After School Ghosts.cmd   double-click to play
   launcher/             the launcher script and a clean default emulator config
   win31_EN.hdi          hard disk image: MS-DOS 6.20 + the English game (boots into it)
   np21w-0.86-rev100/    Neko Project 21/W, the PC-98 emulator
   ghost-en/             the localization kit and the original Japanese game files
