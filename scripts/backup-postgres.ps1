param(
  [string]$OutputDir = "backups",
  [string]$ComposeFile = "docker-compose.yml",
  [string]$DbName = $env:POSTGRES_DB,
  [string]$DbUser = $env:POSTGRES_USER
)

$ErrorActionPreference = "Stop"

if (-not $DbName) { $DbName = "bambiku" }
if (-not $DbUser) { $DbUser = "bambiku" }

function Invoke-DockerCompose {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
  & docker compose -f $ComposeFile @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose command failed: $($Arguments -join ' ')"
  }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker was not found in PATH."
}

& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Docker Compose plugin is not available."
}

$dbContainer = (& docker compose -f $ComposeFile ps -q db).Trim()
if (-not $dbContainer) {
  throw "Compose service 'db' is not running. Start it with: docker compose up -d db"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $OutputDir "bambiku-$timestamp.sql"

Invoke-DockerCompose exec -T db pg_dump -U $DbUser $DbName | Out-File -FilePath $target -Encoding utf8

Write-Host "Backup written to $target" -ForegroundColor Green
