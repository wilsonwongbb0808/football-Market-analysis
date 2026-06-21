$ErrorActionPreference = "Stop"

if (-not $env:CLOUDFLARE_API_TOKEN) {
  throw "Please set CLOUDFLARE_API_TOKEN first."
}

$root = Get-Location
$nodeDir = Join-Path $root "tools\node"
$wranglerHome = Join-Path $root ".wrangler-home"
$functionsDir = Join-Path $root "functions"
$hiddenFunctionsDir = Join-Path $root "functions.deploy-temp-disabled"

$env:Path = "$nodeDir;$env:Path"
$env:XDG_CONFIG_HOME = $wranglerHome

& (Join-Path $nodeDir "node.exe") "build-cloudflare.mjs"
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

if (Test-Path -LiteralPath $hiddenFunctionsDir) {
  throw "Temporary directory functions.deploy-temp-disabled already exists. Please inspect it first."
}

try {
  if (Test-Path -LiteralPath $functionsDir) {
    Rename-Item -LiteralPath $functionsDir -NewName "functions.deploy-temp-disabled"
  }
  & ".\node_modules\.bin\wrangler.cmd" pages deploy dist-cloudflare --project-name worldcup-predictor
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  if ((Test-Path -LiteralPath $hiddenFunctionsDir) -and -not (Test-Path -LiteralPath $functionsDir)) {
    Rename-Item -LiteralPath $hiddenFunctionsDir -NewName "functions"
  }
}
