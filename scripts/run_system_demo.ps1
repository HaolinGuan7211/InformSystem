param(
    [ValidateSet("auto", "local", "mock", "kimi")]
    [string]$Mode = "auto"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

function Import-EnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        if ($line -match '^\s*([^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2]
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

Import-EnvFile (Join-Path $projectRoot ".env.kimi.local")
Import-EnvFile (Join-Path $projectRoot ".env.szu.local")

$resolvedMode = $Mode
if ($resolvedMode -eq "auto") {
    if (-not $env:SZU_BOARD_USERNAME -or -not $env:SZU_BOARD_PASSWORD) {
        $resolvedMode = "local"
    } elseif ($env:KIMI_API_KEY) {
        $resolvedMode = "kimi"
    } else {
        $resolvedMode = "mock"
    }
}

$scriptToRun = switch ($resolvedMode) {
    "local" {
        "scripts\demo_full_pipeline.py"
    }
    "kimi" {
        if (-not $env:SZU_BOARD_USERNAME -or -not $env:SZU_BOARD_PASSWORD) {
            throw "SZU credentials are required for kimi mode. Please fill .env.szu.local first."
        }
        if (-not $env:KIMI_API_KEY) {
            throw "KIMI_API_KEY is required for kimi mode. Please fill .env.kimi.local first."
        }
        "scripts\demo_kimi_szu_board_pipeline.py"
    }
    "mock" {
        if (-not $env:SZU_BOARD_USERNAME -or -not $env:SZU_BOARD_PASSWORD) {
            throw "SZU credentials are required for mock mode. Please fill .env.szu.local first."
        }
        "scripts\demo_szu_board_pipeline.py"
    }
}

Write-Host "Project root: $projectRoot"
Write-Host "Demo mode: $resolvedMode"
Write-Host "Running: $scriptToRun"

Push-Location $projectRoot
try {
    python $scriptToRun
} finally {
    Pop-Location
}
