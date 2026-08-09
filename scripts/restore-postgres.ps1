param(
  [Parameter(Mandatory = $true)][string]$InputFile,
  [string]$ComposeFile = "docker-compose.yml",
  [string]$DbName = $env:POSTGRES_DB,
  [string]$DbUser = $env:POSTGRES_USER,
  [switch]$Force
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

if (-not (Test-Path $InputFile)) {
  throw "Backup file not found: $InputFile"
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

if (-not $Force) {
  $answer = Read-Host "This will erase and restore database '$DbName'. Type RESTORE to continue"
  if ($answer -ne "RESTORE") {
    throw "Restore cancelled."
  }
}

$resetSql = "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
$resetSql | & docker compose -f $ComposeFile exec -T db psql -U $DbUser -d $DbName
if ($LASTEXITCODE -ne 0) {
  throw "Failed to reset public schema."
}

Get-Content -Raw $InputFile | & docker compose -f $ComposeFile exec -T db psql -U $DbUser -d $DbName
if ($LASTEXITCODE -ne 0) {
  throw "Restore failed."
}

Write-Host "Restore completed from $InputFile" -ForegroundColor Green
