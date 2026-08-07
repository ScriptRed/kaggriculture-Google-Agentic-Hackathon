<#
    PowerShell equivalent of the Makefile, for native Windows development.

    Usage:
        .\make.ps1 test
        .\make.ps1 quick
        .\make.ps1 arena
        .\make.ps1 freeze -Name v1-early-discipline
        .\make.ps1 submit -Msg "what changed"

    If PowerShell blocks the script, allow local scripts for this session:
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet('test', 'quick', 'arena', 'freeze', 'submit', 'clean')]
    [string]$Target = 'quick',

    [string]$Name,
    [string]$Msg
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

switch ($Target) {

    'test' {
        python -m pytest tests/ -q
    }

    'quick' {
        python arena/run.py --quick
    }

    'arena' {
        New-Item -ItemType Directory -Force -Path arena/results | Out-Null
        python arena/run.py --json arena/results/latest.json
    }

    'freeze' {
        if (-not $Name) { throw "usage: .\make.ps1 freeze -Name v1-somename" }
        $dest = "arena/opponents/$Name"
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item agent/*.py $dest
        Write-Host "frozen as $dest - now add '$Name' to DEFAULT_OPPONENTS in arena/run.py"
    }

    'submit' {
        if (-not $Msg) { throw 'usage: .\make.ps1 submit -Msg "what changed"' }

        # Windows 10+ ships bsdtar as tar.exe. Build from inside agent/ so that
        # main.py sits at the archive ROOT - Kaggle requires this.
        Push-Location agent
        try {
            tar -czf ../submission.tar.gz main.py constants.py
        } finally {
            Pop-Location
        }

        Write-Host "`nArchive contents (main.py MUST be at the root):"
        tar -tzf submission.tar.gz

        $ok = Read-Host "`nSubmit to Kaggle? (y/N)"
        if ($ok -eq 'y') {
            kaggle competitions submit kaggriculture -f submission.tar.gz -m $Msg
        } else {
            Write-Host "aborted - archive left at submission.tar.gz"
        }
    }

    'clean' {
        Get-ChildItem -Recurse -Directory -Filter __pycache__ |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item submission.tar.gz, arena/results/*.json -ErrorAction SilentlyContinue
    }
}
