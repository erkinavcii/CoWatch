<#
Builds the Windows installer: dist\CoWatch-Setup-<version>.exe

    .\tools\build_windows.ps1

1. PyInstaller turns tray.py into dist\CoWatch\CoWatch.exe (folder mode: antivirus programs
   flag single-file builds more often), with web\ and torrent-helper\ inside.
2. tools\ next to it gets ffmpeg and ffprobe (BtbN's GPL build with shared libraries: the two
   share their DLLs, a third of the size of two static builds) and Node for the torrent helper.
   Both are downloaded once into build\cache.
3. Inno Setup (ISCC.exe) packs the folder into an installer that needs no administrator.

Needs: the project's .venv, Inno Setup 6, and torrent-helper's npm packages.
#>
param(
    [string]$Version = "0.1.0",
    [string]$FfmpegZip = "ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip",
    [string]$NodeVersion = ""  # default: the version of the node on PATH
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is many times faster without the bar

$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root ".venv\Scripts\python.exe"
$build = Join-Path $root "build"
$cache = Join-Path $build "cache"
$dist = Join-Path $root "dist"
$app = Join-Path $dist "CoWatch"
New-Item -ItemType Directory -Force $cache | Out-Null

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Fetch($url, $file) {
    if (-not (Test-Path $file)) {
        Write-Host "   downloading $url"
        Invoke-WebRequest $url -OutFile "$file.part"
        Move-Item "$file.part" $file
    }
}

Step "Python packages"
& $py -m pip install -q -r (Join-Path $root "requirements-build.txt")
if ($LASTEXITCODE) { throw "pip failed" }

Step "Torrent helper packages"
if (-not (Test-Path (Join-Path $root "torrent-helper\node_modules\webtorrent"))) {
    Push-Location (Join-Path $root "torrent-helper"); npm.cmd install --omit=dev; Pop-Location
    if ($LASTEXITCODE) { throw "npm install failed" }
}

Step "Icon"
$icon = Join-Path $build "cowatch.ico"
& $py -c "import sys; sys.path.insert(0, r'$root'); import tray; tray.draw_icon(256).save(r'$icon', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE) { throw "icon failed" }

Step "CoWatch.exe (PyInstaller)"
& $py -m PyInstaller --noconfirm --clean --windowed --name CoWatch --icon $icon `
    --distpath $dist --workpath (Join-Path $build "pyinstaller") --specpath $build `
    --add-data "$root\web;web" --add-data "$root\torrent-helper;torrent-helper" `
    --collect-submodules server --collect-submodules uvicorn --hidden-import run `
    --exclude-module jedi --exclude-module parso --exclude-module IPython `
    (Join-Path $root "tray.py")
if ($LASTEXITCODE) { throw "PyInstaller failed" }

Step "ffmpeg"
$tools = Join-Path $app "tools"
$licenses = Join-Path $app "licenses"
New-Item -ItemType Directory -Force $tools, $licenses | Out-Null
$ffZip = Join-Path $cache $FfmpegZip
Fetch "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/$FfmpegZip" $ffZip
$ffDir = Join-Path $cache ([IO.Path]::GetFileNameWithoutExtension($FfmpegZip))
if (-not (Test-Path $ffDir)) { Expand-Archive $ffZip -DestinationPath $cache }
Copy-Item (Join-Path $ffDir "bin\*") $tools -Exclude "ffplay.exe"
Copy-Item (Join-Path $ffDir "LICENSE.txt") (Join-Path $licenses "ffmpeg-LICENSE.txt")
Set-Content (Join-Path $licenses "ffmpeg-SOURCE.txt") -Encoding ascii -Value @(
    "ffmpeg and ffprobe in tools\ are BtbN's builds ($FfmpegZip), under the GPL.",
    "Their source: https://github.com/BtbN/FFmpeg-Builds and https://ffmpeg.org/download.html"
)

Step "Node"
if (-not $NodeVersion) { $NodeVersion = (node --version).TrimStart("v") }
$nodeName = "node-v$NodeVersion-win-x64"
$nodeZip = Join-Path $cache "$nodeName.zip"
Fetch "https://nodejs.org/dist/v$NodeVersion/$nodeName.zip" $nodeZip
$nodeDir = Join-Path $cache $nodeName
if (-not (Test-Path $nodeDir)) { Expand-Archive $nodeZip -DestinationPath $cache }
Copy-Item (Join-Path $nodeDir "node.exe") $tools
Copy-Item (Join-Path $nodeDir "LICENSE") (Join-Path $licenses "node-LICENSE.txt")
Copy-Item (Join-Path $root "LICENSE") (Join-Path $licenses "CoWatch-LICENSE.txt")

Step "Installer (Inno Setup)"
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup)" }
& $iscc /Q "/DAppVersion=$Version" "/DSourceDir=$app" "/DOutputDir=$dist" "/DIconFile=$icon" (Join-Path $PSScriptRoot "cowatch.iss")
if ($LASTEXITCODE) { throw "Inno Setup failed" }

$setup = Get-Item (Join-Path $dist "CoWatch-Setup-$Version.exe")
$size = (Get-ChildItem $app -Recurse | Measure-Object Length -Sum).Sum
Write-Host ("`nDone: {0} ({1:N0} MB; {2:N0} MB once installed)" -f $setup.FullName, ($setup.Length / 1MB), ($size / 1MB)) -ForegroundColor Green
