param(
    [string]$Version = "final"
)

$ErrorActionPreference = "Stop"

$PortableDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $PortableDir
$SpecFile = Join-Path $PortableDir "DouyinDanmakuForwarder.spec"
$DistDir = Join-Path $ProjectDir "dist"
$WorkDir = Join-Path $ProjectDir "build"
$RuntimeRequirements = Join-Path $ProjectDir "requirements.txt"
$BuildRequirements = Join-Path $PortableDir "requirements-build.txt"
$AppName = "DouyinDanmakuForwarder"
$AppDir = Join-Path $DistDir $AppName
$PackageName = "$AppName-$Version"
$PackageDir = Join-Path $DistDir $PackageName
$ZipPath = Join-Path $DistDir "$PackageName.zip"

function Assert-CommandSucceeded {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

Write-Host "[build] checking PyInstaller..."
python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[build] PyInstaller is not installed."
    Write-Host "[build] installing build dependencies..."
    python -m pip install -r $RuntimeRequirements -r $BuildRequirements -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[build] mirror install failed, retrying official PyPI..."
        python -m pip install -r $RuntimeRequirements -r $BuildRequirements
    }
    Assert-CommandSucceeded "Failed to install build dependencies"
}
python -m PyInstaller --version | Out-Null
Assert-CommandSucceeded "PyInstaller is installed but cannot start"

Write-Host "[build] cleaning previous portable output..."
if (Test-Path -LiteralPath $AppDir) {
    Remove-Item -LiteralPath $AppDir -Recurse -Force
}
if (Test-Path -LiteralPath $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Write-Host "[build] running PyInstaller..."
python -m PyInstaller --clean --noconfirm --distpath $DistDir --workpath $WorkDir $SpecFile
Assert-CommandSucceeded "PyInstaller build failed"

Write-Host "[build] preparing package directory..."
Move-Item -LiteralPath $AppDir -Destination $PackageDir
$GeneratedEnv = Join-Path $PackageDir "platform_ingest.env"
if (Test-Path -LiteralPath $GeneratedEnv) {
    Remove-Item -LiteralPath $GeneratedEnv -Force
}
Copy-Item -LiteralPath (Join-Path $ProjectDir "platform_ingest.env.example") -Destination (Join-Path $PackageDir "platform_ingest.env.example") -Force
Copy-Item -LiteralPath (Join-Path $PortableDir "start-forwarder.bat") -Destination (Join-Path $PackageDir "start-forwarder.bat") -Force
Copy-Item -LiteralPath (Join-Path $PortableDir "README.md") -Destination (Join-Path $PackageDir "README.md") -Force

Write-Host "[build] validating packaged runtime resources..."
$RequiredFiles = @(
    "DouyinDanmakuForwarder.exe",
    "_internal\a_bogus.js",
    "_internal\sign.js",
    "_internal\mini_racer.dll",
    "_internal\icudtl.dat",
    "_internal\snapshot_blob.bin",
    "_internal\certifi\cacert.pem",
    "platform_ingest.env.example",
    "start-forwarder.bat",
    "README.md"
)
foreach ($RelativePath in $RequiredFiles) {
    $FullPath = Join-Path $PackageDir $RelativePath
    if (-not (Test-Path -LiteralPath $FullPath)) {
        throw "Packaged runtime resource is missing: $RelativePath"
    }
}
if (Test-Path -LiteralPath $GeneratedEnv) {
    throw "Do not package local platform_ingest.env because it may contain a real ingest token"
}

Write-Host "[build] creating zip..."
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force
if ((tar -tf $ZipPath) -contains "platform_ingest.env") {
    throw "Zip unexpectedly contains local platform_ingest.env"
}

Write-Host "[build] done: $ZipPath"
