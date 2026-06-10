$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $root 'tools\python312\python.exe'
$script = Join-Path $root 'tools\download_worldcup_opening_odds.py'

if (-not $env:ODDS_API_KEY) {
  $env:ODDS_API_KEY = '3aa61b8382dcb462b4b0bb97c16a169e05db1334b26c7f5f6c11a84ab0ad7fca'
}
if (-not $env:ODDS_BOOKMAKER) {
  $env:ODDS_BOOKMAKER = 'Bet365'
}

$env:ODDS_MODE = 'latest'
$env:ODDS_REQUEST_BUDGET = '90'
& $python $script

$env:ODDS_MODE = 'hybrid'
$env:ODDS_REQUEST_BUDGET = '10'
& $python $script
