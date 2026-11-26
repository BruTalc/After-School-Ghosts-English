# Launcher for After School Ghosts (English).
#
# Neko Project 21/W has no command-line option for hard disk images, so this script
# points the emulator's np21w.ini at win31_EN.hdi using a full path, then starts it.
# That way the game boots no matter where the folder was unzipped or how it was started.
#
#   launch.ps1            set up the ini and start the game
#   launch.ps1 -DryRun    set up the ini only, print what was done
param([switch]$DryRun)

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

try {
    [System.IO.File]::WriteAllText($Ini, $text, [System.Text.Encoding]::Unicode)
} catch {
    Show-Error ("Could not save the emulator settings:`n$Ini`n`n" +
                "Move the game folder somewhere you can write to, such as Documents or the Desktop.")
}

if ($DryRun) {
    Write-Host "np21w.ini updated: HDD1FILE=$Image"
    exit 0
}

Start-Process -FilePath $Exe -WorkingDirectory $EmuDir
