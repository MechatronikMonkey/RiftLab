<#
.SYNOPSIS
    Build the RiftLab Windows installer locally.

.DESCRIPTION
    The same steps CI runs, for when you want a setup file on your own machine
    without pushing a tag:

      1. build a virtualenv with the viewer's dependencies + PyInstaller
      2. generate the icon from the viewer's own palette
      3. freeze the app into dist\RiftLab\
      4. run `RiftLab.exe selfcheck` against the frozen build - the smoke test
         that catches a dependency PyInstaller failed to see. RiftLab's stack
         (Qt, pyqtgraph, matplotlib, numpy) is the heavier of the two tools, so
         it has more ways to go wrong, and in a windowed build every one of them
         looks identical: a window that never appears.
      5. optionally sign RiftLab.exe
      6. wrap it into dist\RiftLab-Setup-<version>.exe with Inno Setup

    Anyone who wants to change RiftLab works from a source checkout instead;
    this is for people who just want to open a recording and look at it.

.PARAMETER SignCommand
    Command used to sign binaries, with {f} where the file goes, e.g.
      -SignCommand 'signtool.exe sign /fd sha256 /f cert.pfx /p pw /tr http://timestamp.digicert.com /td sha256 {f}'
    Omit it for an unsigned build.

.PARAMETER SkipInstaller
    Stop after the frozen folder (useful when Inno Setup is not installed).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#>
[CmdletBinding()]
param(
    [string]$SignCommand,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }

# -- version ---------------------------------------------------------------
$initPath = Join-Path $root "riftlab\__init__.py"
$match = Select-String -Path $initPath -Pattern '^__version__\s*=\s*"([^"]+)"'
if (-not $match) { throw "Could not read __version__ from $initPath" }
$version = $match.Matches[0].Groups[1].Value
Step "RiftLab $version"

# -- 1. build environment --------------------------------------------------
$venv = Join-Path $root ".venv-build"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    Step "Creating build environment ($venv)"
    python -m venv $venv
    if (-not $?) { throw "Could not create the build virtualenv" }
}
# A release is built by the interpreter named in .python-version. A local
# build on a different one is fine for trying something out, but it is not the
# same artefact - so say so rather than let the difference go unnoticed.
$pinFile = Join-Path $root ".python-version"
if (Test-Path $pinFile) {
    $pinned = (Get-Content $pinFile -Raw).Trim()
    $local = (& $py -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
    if ($local -ne $pinned) {
        Write-Warning "Building with Python $local; releases are built with $pinned (.python-version). The result will differ from the released installer."
    }
}

Step "Installing build dependencies"
& $py -m pip install --disable-pip-version-check --quiet --upgrade pip

# --use-feature=truststore makes pip verify against the WINDOWS certificate
# store instead of its own bundled one. On a machine where something inspects
# TLS - a corporate proxy, or an antivirus with HTTPS scanning, which is common
# enough that it hit this project - pip otherwise fails with
# CERTIFICATE_VERIFY_FAILED against PyPI. This keeps verification on, unlike
# --trusted-host, which switches it off. Harmless where it is not needed, and
# droppable once pip does it by default.
$reqs = @("-r", (Join-Path $root "requirements.txt"), "pyinstaller")
& $py -m pip install --disable-pip-version-check --quiet --use-feature=truststore @reqs
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Install with truststore failed - retrying with pip's own certificates"
    & $py -m pip install --disable-pip-version-check --quiet @reqs
}
if ($LASTEXITCODE -ne 0) { throw "Dependency install failed" }

# -- 2. icon ---------------------------------------------------------------
Step "Generating the icon"
& $py (Join-Path $root "packaging\make_icon.py")
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

# -- 3. freeze -------------------------------------------------------------
Step "Freezing the application"
& $py -m PyInstaller --noconfirm --clean --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "build") (Join-Path $root "packaging\riftlab.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $root "dist\RiftLab\RiftLab.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe to exist after the build" }

# -- 4. smoke test the frozen build ---------------------------------------
Step "Self-check against the frozen build"
$log = Join-Path $env:APPDATA "RiftLab\riftlab.log"
if (Test-Path $log) { Remove-Item $log -Force }
$proc = Start-Process -FilePath $exe -ArgumentList "selfcheck" -Wait -PassThru
if (Test-Path $log) { Get-Content $log | ForEach-Object { Write-Host "    $_" } }
if ($proc.ExitCode -ne 0) {
    throw "selfcheck failed (exit $($proc.ExitCode)) - the frozen build is missing something"
}

# -- 5. sign the application (optional) -----------------------------------
function Invoke-Sign([string]$file) {
    if (-not $SignCommand) { return }
    $cmd = $SignCommand.Replace("{f}", '"' + $file + '"')
    Write-Host "    signing $file"
    cmd.exe /c $cmd
    if ($LASTEXITCODE -ne 0) { throw "Signing failed for $file" }
}
if ($SignCommand) {
    Step "Signing RiftLab.exe"
    Invoke-Sign $exe
}

if ($SkipInstaller) {
    Step "Done (installer skipped): $exe"
    return
}

# -- 6. installer ----------------------------------------------------------
Step "Building the installer"
$iscc = $null
foreach ($candidate in @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe")) {
    if (Test-Path $candidate) { $iscc = $candidate; break }
}
if (-not $iscc) {
    $found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($found) { $iscc = $found.Source }
}
if (-not $iscc) {
    Write-Warning "Inno Setup 6 not found - install it (winget install JRSoftware.InnoSetup) and re-run, or use -SkipInstaller."
    Write-Host "Frozen build is ready at: $exe"
    return
}

$isccArgs = @("/DAppVersion=$version")
if ($SignCommand) {
    # Inno signs the setup and the uninstaller itself; $f is its own placeholder
    # for the file being signed, so hand the command over with {f} swapped for it.
    $isccArgs += "/DSIGN"
    $isccArgs += ("/Ssigntool=" + $SignCommand.Replace("{f}", '$f'))
}
$isccArgs += (Join-Path $root "packaging\riftlab.iss")
& $iscc $isccArgs
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

$setup = Join-Path $root "dist\RiftLab-Setup-$version.exe"
Step "Done"
Write-Host "Installer: $setup"
if (-not $SignCommand) {
    Write-Host "NOTE: unsigned - Windows SmartScreen will warn on first run." -ForegroundColor Yellow
}
Write-Host "(build environment kept at $venv for faster rebuilds; delete it to reset)"
