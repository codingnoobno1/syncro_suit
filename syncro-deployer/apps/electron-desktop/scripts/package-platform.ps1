$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $AppDir

$Version = (Get-Content package.json | ConvertFrom-Json).version

Write-Host "==> [1/4] Compiling Windows native DLL (syncro_native.dll)..."
& pwsh -File native\build-native.ps1

Write-Host "==> [2/4] Generating icons & building Vite renderer..."
npm run build

Write-Host "==> [3/4] Packaging Windows .exe (NSIS + Portable) & .zip with electron-builder..."
New-Item -ItemType Directory -Force -Path release | Out-Null
npx electron-builder --win nsis portable zip --publish never

Write-Host "==> [4/4] Copying standalone DLL & generating SHA256SUMS.txt..."
Copy-Item native\dist\syncro_native.dll release\ -Force

Push-Location release
Get-ChildItem -File | Where-Object { $_.Extension -in @('.exe', '.zip', '.dll') } | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    "$hash  $($_.Name)"
} | Set-Content SHA256SUMS.txt
Pop-Location

Write-Host "==> Windows artifacts ready in $AppDir\release:"
Get-ChildItem release | Format-Table Name, Length
