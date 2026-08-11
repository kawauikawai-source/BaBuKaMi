$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Backend = Join-Path $Root "backend"
$CodexNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"

function Step($Name) {
  Write-Host ""
  Write-Host "==> $Name" -ForegroundColor Cyan
}

function Find-Python {
  $VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
  if (Test-Path $VenvPython) {
    return $VenvPython
  }
  $Python = Get-Command python -ErrorAction SilentlyContinue
  if ($Python) {
    return $Python.Source
  }
  $Py = Get-Command py -ErrorAction SilentlyContinue
  if ($Py) {
    return $Py.Source
  }
  throw "Python not found. Create backend\.venv or install Python 3.13."
}

function Find-Node {
  $Node = Get-Command node -ErrorAction SilentlyContinue
  if ($Node) {
    return $Node.Source
  }
  if (Test-Path $CodexNode) {
    return $CodexNode
  }
  throw "Node.js not found. Install Node 20+ or run inside Codex with bundled runtime."
}

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
  )

  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
  }
}

function Assert-RequiredFile {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path $Path)) {
    throw "Required file is missing: $Path"
  }
}

function Test-PowerShellParse {
  param([Parameter(Mandatory = $true)][string]$Path)
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count -gt 0) {
    throw "PowerShell parse failed for $Path`: $($errors[0].Message)"
  }
}

$Python = Find-Python
$Node = Find-Node

Step "Python compile"
Push-Location $Backend
Invoke-Checked $Python -m compileall app tests
Pop-Location

Step "Backend tests"
Push-Location $Backend
Invoke-Checked $Python -m unittest discover -s tests
Pop-Location

Step "Alembic upgrade"
Push-Location $Backend
Invoke-Checked $Python -m alembic upgrade head
Pop-Location

Step "Alembic current"
Push-Location $Backend
Invoke-Checked $Python -m alembic current
Pop-Location

Step "JavaScript syntax"
$JavaScriptRoots = @(
  (Join-Path $Root "js"),
  (Join-Path $Root "bukamiku_service\static")
)
$JavaScriptRoots | ForEach-Object {
  Assert-RequiredFile $_
}
$JavaScriptRoots | ForEach-Object {
  Get-ChildItem -Path $_ -Filter "*.js" -Recurse
} | Sort-Object FullName | ForEach-Object {
  Invoke-Checked $Node --check $_.FullName
}

Step "CSS compatibility bundle"
Invoke-Checked $Node (Join-Path $Root "scripts\build-css.js")
Assert-RequiredFile (Join-Path $Root "css\style.css")

Step "Render frontend build"
Invoke-Checked $Python (Join-Path $Root "scripts\build_render_site.py")
$RenderDist = Join-Path $Root "dist"
Assert-RequiredFile (Join-Path $RenderDist "index.html")
Assert-RequiredFile (Join-Path $RenderDist "pages\profile.html")
Assert-RequiredFile (Join-Path $RenderDist "js\config\runtime.js")
if (Test-Path (Join-Path $RenderDist "backend")) {
  throw "Render frontend build must not contain backend sources"
}
$SourceHtmlCount = 1 + @(Get-ChildItem -Path (Join-Path $Root "pages") -Filter "*.html" -File).Count
$BuiltHtmlCount = @(Get-ChildItem -Path $RenderDist -Filter "*.html" -File -Recurse).Count
if ($SourceHtmlCount -ne $BuiltHtmlCount) {
  throw "Render frontend build has $BuiltHtmlCount HTML files; expected $SourceHtmlCount"
}

Step "Static release checks"
Invoke-Checked $Node (Join-Path $Root "scripts\static-checks.js")

Step "Infrastructure checks"
$RequiredInfraFiles = @(
  "docker-compose.yml",
  ".env.compose.example",
  "backend\.env.example",
  "backend\.env.production.example",
  "backend\Dockerfile",
  "deploy\nginx\default.conf",
  "deploy\nginx\runtime.js",
  "scripts\backup-postgres.ps1",
  "scripts\restore-postgres.ps1",
  "backups\.gitkeep",
  "render.yaml",
  "scripts\build_render_site.py",
  "scripts\render-start.sh",
  "RENDER_NEON_DEPLOY.md",
  "bukamiku_service\app.py",
  "bukamiku_service\static\index.html"
)
$RequiredInfraFiles | ForEach-Object {
  Assert-RequiredFile (Join-Path $Root $_)
}
Test-PowerShellParse (Join-Path $Root "scripts\backup-postgres.ps1")
Test-PowerShellParse (Join-Path $Root "scripts\restore-postgres.ps1")

$RenderBlueprint = Get-Content (Join-Path $Root "render.yaml") -Raw
@("name: bambiku", "name: bukamiku", "runtime: python", "plan: free", "region: frankfurt", "healthCheckPath: /api/health", "healthCheckPath: /health") | ForEach-Object {
  if (-not $RenderBlueprint.Contains($_)) {
    throw "render.yaml is missing required setting: $_"
  }
}

Write-Host ""
Write-Host "Quality gate passed" -ForegroundColor Green
