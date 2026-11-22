# Убирает маркер "скачано из интернета" (Mark of the Web) у WinBoost.exe.
# Это убирает возможное предупреждение SmartScreen для уже загруженного файла.
# Запуск: powershell -ExecutionPolicy Bypass -File .\tools\unblock.ps1

param(
    [string]$Path = ".\WinBoost.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "File not found: $Path" -ForegroundColor Red
    exit 1
}

$item = Get-Item -LiteralPath $Path
$streams = $item | Get-Item -Stream * -ErrorAction SilentlyContinue

$hadZone = $false
foreach ($stream in $streams) {
    if ($stream.Stream -eq "Zone.Identifier") {
        $hadZone = $true
        break
    }
}

if ($hadZone) {
    Unblock-File -LiteralPath $Path
    Write-Host "Mark of the Web removed. You can run $Path now." -ForegroundColor Green
} else {
    Write-Host "No Mark of the Web found. SmartScreen warning (if any) is reputation-based." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "If Windows still blocks the file: click 'More info' -> 'Run anyway' once." -ForegroundColor Cyan
Write-Host "To avoid the warning permanently, sign the exe with an EV/OV code-signing certificate." -ForegroundColor Cyan
Write-Host "You can also submit the file for analysis: https://www.microsoft.com/en-us/wdsi/filesubmission" -ForegroundColor Cyan
