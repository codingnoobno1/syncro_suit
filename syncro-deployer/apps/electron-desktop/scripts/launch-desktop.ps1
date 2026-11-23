$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$CpDir = Resolve-Path (Join-Path $AppDir "..\..\services\control-plane")

Write-Host "==> Ensuring Python Syncro Control Plane (.venv) is ready..."
$SyncroExe = Join-Path $CpDir ".venv\Scripts\syncro.exe"
if (-not (Test-Path $SyncroExe)) {
    Push-Location $CpDir
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv .venv
        uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
    } else {
        python -m venv .venv
        .venv\Scripts\pip.exe install -e ".[dev]"
    }
    Pop-Location
}

Write-Host "==> Building Syncro Electron Desktop renderer..."
Push-Location $AppDir
if (-not (Test-Path "node_modules")) {
    npm install
}
if ((Get-Command gcc -ErrorAction SilentlyContinue) -or (Get-Command cl -ErrorAction SilentlyContinue)) {
    & pwsh -File native\build-native.ps1
}
npm run build

Write-Host "==> Launching Syncro Deployer as a standalone native Windows desktop application..."
npx electron .
Pop-Location
