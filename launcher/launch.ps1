# Launcher for After School Ghosts (English).
#
# Neko Project 21/W has no command-line option for hard disk images, so this script
# points the emulator's np21w.ini at win31_EN.hdi using a full path, then starts it.
# That way the game boots no matter where the folder was unzipped or how it was started.
#
# On the first run it also picks a window size that suits the screen (see Set-WindowSize).
#
#   launch.ps1                set up the ini and start the game
#   launch.ps1 -DryRun        set up the ini only, print what was done
#   launch.ps1 -ResetWindow   pick the window size again, as on the first run
param([switch]$DryRun, [switch]$ResetWindow)

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$EmuDir   = Join-Path $Root 'np21w-0.86-rev100'
$Exe      = Join-Path $EmuDir 'np21w.exe'
$Ini      = Join-Path $EmuDir 'np21w.ini'
$Template = Join-Path $PSScriptRoot 'np21w.default.ini'
$Image    = Join-Path $Root 'win31_EN.hdi'

function Show-Error([string]$Message) {
    if ($DryRun) { Write-Host "ERROR: $Message"; exit 1 }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($Message, 'After School Ghosts',
        [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
    exit 1
}

# --- sanity checks -------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $Image)) {
    if ($Root -match '\\(Temp|Temporary Internet Files)\\') {
        Show-Error ("It looks like the game is being run from inside the zip file.`n`n" +
                    "Right-click the zip, choose 'Extract All...', then run " +
                    "'Play After School Ghosts' from the extracted folder.")
    }
    Show-Error "The game disk image is missing:`n$Image`n`nKeep all the files from the download together in one folder."
}
if (-not (Test-Path -LiteralPath $Exe)) {
    Show-Error "The emulator is missing:`n$Exe`n`nKeep all the files from the download together in one folder."
}
if (Get-Process -Name 'np21w' -ErrorAction SilentlyContinue) {
    Show-Error 'The game is already running.'
}

# --- point the emulator at the disk image ----------------------------------------------
# np21w.ini is UTF-16 LE with a BOM; it must be written back the same way.
if (Test-Path -LiteralPath $Ini) {
    $text = [System.IO.File]::ReadAllText($Ini)
} elseif (Test-Path -LiteralPath $Template) {
    $text = [System.IO.File]::ReadAllText($Template)
} else {
    $text = "[NekoProject21]`r`n"
}

function Set-IniKey([string]$Text, [string]$Key, [string]$Value) {
    $pattern = '(?m)^' + [regex]::Escape($Key) + '=[^\r\n]*'
    $line = "$Key=$Value"
    if ([regex]::IsMatch($Text, $pattern)) {
        # a MatchEvaluator keeps '$' in paths from being read as a substitution
        return [regex]::Replace($Text, $pattern, { param($m) $line }, 1)
    }
    # key missing: add it right under the [NekoProject21] header
    return [regex]::Replace($Text, '(?m)^\[NekoProject21\][^\r\n]*', { param($m) $m.Value + "`r`n" + $line }, 1)
}

$text = Set-IniKey $text 'HDD1FILE' $Image                       # IDE #0 = the game
$text = Set-IniKey $text 'HDD2FILE' ''                           # IDE #1 empty
$text = Set-IniKey $text 'HDfolder' $Image                       # folder the Open... dialog starts in
$text = Set-IniKey $text 'use_hdrv' 'false'                      # no host-folder sharing needed
$text = Set-IniKey $text 'HOSTDRV0' ''

# --- window size and position ----------------------------------------------------------
# SCRN_MUL is the window scale in eighths (8 = 1x = 640x400, 16 = 2x, 24 = 3x, 32 = 4x).
# The emulator is DPI-aware and draws in physical pixels, so on a high-DPI laptop 1x is
# tiny. On the first run (SVSCRMUL is not yet true) pick the largest scale that fits the
# screen, preferring whole-number scales so the pixels stay sharp. SVSCRMUL=true makes the
# emulator remember the size, so a size the player picks later in Screen -> Window size
# is kept. The window is re-centred whenever it would not be fully on screen.
function Get-IniKey([string]$Text, [string]$Key) {
    $m = [regex]::Match($Text, '(?m)^' + [regex]::Escape($Key) + '=([^\r\n]*)')
    if ($m.Success) { return $m.Groups[1].Value } else { return $null }
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -Namespace Ghost -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][Ghost.Dpi]::SetProcessDPIAware()   # so the screen size below is in physical pixels
$work = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$chromeW = 40; $chromeH = 110             # borders + title bar + menu bar, with some slack

$first = $ResetWindow -or ((Get-IniKey $text 'SVSCRMUL') -ne 'true')
if ($first) {
    $mul = 8
    foreach ($m in 32, 24, 16, 12) {
        if ((640 * $m / 8 + $chromeW) -le $work.Width -and (400 * $m / 8 + $chromeH) -le $work.Height) { $mul = $m; break }
    }
    $text = Set-IniKey $text 'SCRN_MUL' "$mul"
    $text = Set-IniKey $text 'SVSCRMUL' 'true'
}
$mul = 8
[void][int]::TryParse((Get-IniKey $text 'SCRN_MUL'), [ref]$mul)
$winW = [int](640 * $mul / 8 + $chromeW); $winH = [int](400 * $mul / 8 + $chromeH)
$x = 0; $y = 0
$okX = [int]::TryParse((Get-IniKey $text 'WindposX'), [ref]$x)
$okY = [int]::TryParse((Get-IniKey $text 'WindposY'), [ref]$y)
$onScreen = $okX -and $okY -and [System.Windows.Forms.Screen]::AllScreens.Where({
    $a = $_.WorkingArea
    $x -ge $a.Left - 20 -and $y -ge $a.Top - 20 -and $x + $winW -le $a.Right + 20 -and $y + $winH -le $a.Bottom + 20
}).Count -gt 0
if ($first -or -not $onScreen) {
    $text = Set-IniKey $text 'WindposX' ([string][Math]::Max($work.Left, $work.Left + [int](($work.Width - $winW) / 2)))
    $text = Set-IniKey $text 'WindposY' ([string][Math]::Max($work.Top, $work.Top + [int](($work.Height - $winH) / 2)))
}

try {
    [System.IO.File]::WriteAllText($Ini, $text, [System.Text.Encoding]::Unicode)
} catch {
    Show-Error ("Could not save the emulator settings:`n$Ini`n`n" +
                "Move the game folder somewhere you can write to, such as Documents or the Desktop.")
}

if ($DryRun) {
    Write-Host "np21w.ini updated: HDD1FILE=$Image"
    Write-Host ("window: scale {0}x (SCRN_MUL={1}), at {2},{3}, screen work area {4}x{5}" -f ($mul / 8), $mul,
        (Get-IniKey $text 'WindposX'), (Get-IniKey $text 'WindposY'), $work.Width, $work.Height)
    exit 0
}

Start-Process -FilePath $Exe -WorkingDirectory $EmuDir
