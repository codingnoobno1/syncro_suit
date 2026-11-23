$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutDir = Join-Path $ScriptDir "dist"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Src = Join-Path $ScriptDir "src\syncro_native.c"
$OutDll = Join-Path $OutDir "syncro_native.dll"

if (Get-Command gcc -ErrorAction SilentlyContinue) {
    & gcc -O2 -Wall -Wextra -std=c99 -shared -o $OutDll $Src
} elseif (Get-Command cl -ErrorAction SilentlyContinue) {
    & cl /O2 /LD $Src /Fe:$OutDll
} else {
    throw "No C compiler (gcc or cl) found in PATH to compile syncro_native.dll"
}

Write-Host "Built Windows native library: $OutDll"
Get-Item $OutDll | Format-List Name, Length, FullName
