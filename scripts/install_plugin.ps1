#requires -Version 5.1
<#
.SYNOPSIS
    Install the SAIE SketchUp plugin into the user's Plugins directory.

.DESCRIPTION
    Copies (or symlinks, in dev mode) the ruby_plugin/ contents into
    %APPDATA%\SketchUp\SketchUp <version>\SketchUp\Plugins\ so the plugin
    auto-loads when SketchUp launches.

.PARAMETER Version
    SketchUp version (e.g. "2025"). Defaults to value from saie.toml or 2025.

.PARAMETER Symlink
    Create a directory junction instead of copying. Useful for development —
    every edit in ruby_plugin/ is picked up on the next SketchUp launch.
    Requires Windows; no admin needed for directory junctions.

.PARAMETER Force
    Overwrite an existing install without prompting.

.EXAMPLE
    .\install_plugin.ps1
        Copy mode, version from saie.toml.

.EXAMPLE
    .\install_plugin.ps1 -Symlink
        Dev mode — junction to the repo.

.EXAMPLE
    .\install_plugin.ps1 -Version 2024 -Force
        Install into SketchUp 2024, overwrite any existing install.
#>

param(
    [string]$Version,
    [switch]$Symlink,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ─── Locate repo root ────────────────────────────────────────────────────────
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$srcRoot  = Join-Path $repoRoot 'ruby_plugin'
$srcDir   = Join-Path $srcRoot 'su_mcp_bridge'
$srcLdr   = Join-Path $srcRoot 'su_mcp_bridge.rb'

if (-not (Test-Path $srcDir) -or -not (Test-Path $srcLdr)) {
    throw "SAIE plugin source not found at $srcRoot."
}

# ─── Resolve SketchUp version from saie.toml or parameter ────────────────────
if (-not $Version) {
    $cfgPath = Join-Path $repoRoot 'saie.toml'
    if (Test-Path $cfgPath) {
        $cfg = Get-Content $cfgPath -Raw
        if ($cfg -match '(?m)^\s*version\s*=\s*"(\d{4})"') {
            $Version = $Matches[1]
        }
    }
    if (-not $Version) { $Version = '2025' }
}

Write-Host "SAIE plugin installer" -ForegroundColor Cyan
Write-Host "  SketchUp version: $Version"
Write-Host "  Source:           $srcRoot"
Write-Host ""

# ─── Locate destination Plugins directory ────────────────────────────────────
$pluginsDir = Join-Path $env:APPDATA "SketchUp\SketchUp $Version\SketchUp\Plugins"

if (-not (Test-Path $pluginsDir)) {
    Write-Host "Plugins directory not found: $pluginsDir" -ForegroundColor Yellow
    Write-Host "Make sure SketchUp $Version has been launched at least once."
    if (-not $Force) {
        $resp = Read-Host "Create it anyway? (y/N)"
        if ($resp -ne 'y') { exit 1 }
    }
    New-Item -ItemType Directory -Path $pluginsDir -Force | Out-Null
}

Write-Host "  Destination:      $pluginsDir"
Write-Host ""

# ─── Detect existing install ─────────────────────────────────────────────────
$dstDir = Join-Path $pluginsDir 'su_mcp_bridge'
$dstLdr = Join-Path $pluginsDir 'su_mcp_bridge.rb'

if (Test-Path $dstDir -or Test-Path $dstLdr) {
    if (-not $Force) {
        Write-Host "SAIE plugin already installed." -ForegroundColor Yellow
        $resp = Read-Host "Overwrite? (y/N)"
        if ($resp -ne 'y') { exit 0 }
    }
    Write-Host "Removing existing install..." -ForegroundColor Yellow
    if (Test-Path $dstDir) { Remove-Item $dstDir -Recurse -Force }
    if (Test-Path $dstLdr) { Remove-Item $dstLdr -Force }
}

# ─── Install ─────────────────────────────────────────────────────────────────
if ($Symlink) {
    Write-Host "Creating directory junction (dev mode)..." -ForegroundColor Green
    New-Item -ItemType Junction -Path $dstDir -Target $srcDir | Out-Null
    Copy-Item $srcLdr $dstLdr -Force
} else {
    Write-Host "Copying plugin files..." -ForegroundColor Green
    Copy-Item $srcDir $dstDir -Recurse -Force
    Copy-Item $srcLdr $dstLdr -Force
}

# ─── Seed user config ────────────────────────────────────────────────────────
$userCfgDir = Join-Path $env:USERPROFILE '.saie'
$userCfg    = Join-Path $userCfgDir 'saie.toml'
$repoCfg    = Join-Path $repoRoot 'saie.toml'

if ((Test-Path $repoCfg) -and (-not (Test-Path $userCfg))) {
    New-Item -ItemType Directory -Path $userCfgDir -Force | Out-Null
    Copy-Item $repoCfg $userCfg
    Write-Host "Seeded user config at $userCfg" -ForegroundColor Green
}

Write-Host ""
Write-Host "✓ SAIE plugin installed." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Launch SketchUp $Version."
Write-Host "  2. Look for 'Extensions → SAIE' in the menu bar."
Write-Host "  3. Verify with: saie ping"
