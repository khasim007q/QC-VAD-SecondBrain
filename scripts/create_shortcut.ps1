# Creates a "Class Notes" shortcut on the Desktop (and in the Start menu) that starts the app
# without a console window. Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1

$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$icon = Join-Path $root "src\classnotes\ui\icon.ico"

if (-not (Test-Path $pythonw)) {
    Write-Error "No environment yet. Run 'uv sync' in $root first."
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs")
)
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Class Notes.lnk"))
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = "-m classnotes.ui.app"
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = "Urdu/English class recordings to English notes"
    $lnk.Save()
    Write-Output "Created $(Join-Path $dir 'Class Notes.lnk')"
}
