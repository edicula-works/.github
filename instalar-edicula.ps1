# Instala o edicula alpha (Linear + Slack + Orca + agents GLM) e roda o setup.
# Uso (PowerShell): irm https://raw.githubusercontent.com/edicula-works/.github/main/instalar-edicula.ps1 | iex
# Se você trabalha no WSL (o Orca cria as worktrees lá), rode o instalador .sh dentro do WSL.
$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Host 'Instale o GitHub CLI primeiro: winget install GitHub.cli (depois abra um novo PowerShell e rode de novo).'
  return
}
gh auth status -h github.com *> $null
if ($LASTEXITCODE -ne 0) { gh auth login -h github.com -w -p https }

$tags = gh release list -R edicula-works/harness --limit 50 --json tagName,isPrerelease | ConvertFrom-Json
$tag = $tags | Where-Object { $_.isPrerelease -and $_.tagName -match '^v[0-9.]+-alpha\.(\d+)$' } |
  Sort-Object { [int]($_.tagName -replace '^v[0-9.]+-alpha\.', '') } | Select-Object -Last 1 -ExpandProperty tagName
if (-not $tag) { Write-Host 'Não achei a versão alpha (sem acesso ao repo edicula-works/harness?)'; return }

$tmp = Join-Path $env:TEMP ("edicula-" + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
try {
  Write-Host "Baixando edicula $tag..."
  gh release download $tag -R edicula-works/harness -p edicula-windows-x64.exe -p SHA256SUMS -D $tmp
  $exe = Join-Path $tmp 'edicula-windows-x64.exe'
  $esperado = (Select-String -Path (Join-Path $tmp 'SHA256SUMS') -Pattern 'edicula-windows-x64.exe').Line.Split(' ')[0]
  if ((Get-FileHash $exe -Algorithm SHA256).Hash.ToLower() -ne $esperado.ToLower()) { throw 'Checksum não confere; abortando.' }
  # O setup instala o binário no lugar certo (guardando o estável) e prepara tudo.
  & $exe alpha setup
} finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
