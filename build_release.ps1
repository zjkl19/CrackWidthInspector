$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$version = "v1.0.0"
$releaseRoot = Join-Path $projectRoot "release"
$packageName = "CrackWidthInspector-$version-win64"
$packageDir = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot "$packageName.zip"
$distAppDir = Join-Path $projectRoot "dist\CrackWidthInspector"
$docsDir = Join-Path $projectRoot "docs"
$samplesDir = Join-Path $packageDir "SampleImages"
$customerDocsDir = Join-Path $packageDir "Docs"
$outputsDir = Join-Path $packageDir "outputs"
$quickStartSource = Join-Path $docsDir "customer_quick_start_zh.txt"

& (Join-Path $projectRoot "build_exe.ps1")

if (-not (Test-Path $distAppDir)) {
    throw "Packaged application not found: $distAppDir"
}

if (-not (Test-Path $quickStartSource)) {
    throw "Customer quick-start guide not found: $quickStartSource"
}

if (Test-Path $packageDir) {
    Remove-Item -Recurse -Force $packageDir
}

if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
New-Item -ItemType Directory -Path $packageDir | Out-Null

Copy-Item -Path (Join-Path $distAppDir "*") -Destination $packageDir -Recurse -Force

if (Test-Path $outputsDir) {
    Remove-Item -Recurse -Force $outputsDir
}
New-Item -ItemType Directory -Path $outputsDir | Out-Null
Set-Content -Path (Join-Path $outputsDir "Output_Files_Will_Be_Saved_Here.txt") -Value "Generated result files will be saved here." -Encoding ASCII

New-Item -ItemType Directory -Path $samplesDir | Out-Null
Copy-Item -Path (Join-Path $projectRoot "crack.jpeg") -Destination $samplesDir -Force
Copy-Item -Path (Join-Path $projectRoot "crack2.jpeg") -Destination $samplesDir -Force

New-Item -ItemType Directory -Path $customerDocsDir | Out-Null
$quickStartText = Get-Content -Path $quickStartSource -Raw
Set-Content -Path (Join-Path $packageDir "QuickStart_CN.txt") -Value $quickStartText -Encoding UTF8
Copy-Item -Path (Join-Path $docsDir "*.md") -Destination $customerDocsDir -Force
Copy-Item -Path (Join-Path $projectRoot "README.md") -Destination $customerDocsDir -Force

$launcher = @'
@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0CrackWidthInspector.exe"
endlocal
'@
Set-Content -Path (Join-Path $packageDir "Launch Crack Width Inspector.bat") -Value $launcher -Encoding ASCII

$releaseInfo = @"
Crack Width Inspector
Version: $version
Build Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

Main Program:
  CrackWidthInspector.exe

Customer Launch:
  Launch Crack Width Inspector.bat

Included Folders:
  outputs      - default output folder
  SampleImages - sample input images
  Docs         - technical and project documents

Notes:
  1. Width values in mm depend on the scale parameter.
  2. If scale is not calibrated, mm values are estimates only.
  3. HED model files are bundled under _internal\models.
"@
Set-Content -Path (Join-Path $packageDir "Release_Info.txt") -Value $releaseInfo -Encoding UTF8

Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -Force

Write-Host "Release package created:"
Write-Host "  $packageDir"
Write-Host "Zip archive created:"
Write-Host "  $zipPath"
