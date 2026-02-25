param()

$ErrorActionPreference = "Stop"

Write-Host "Repo status"
git status --short
Write-Host "Python version"
python --version
Write-Host "Ruff version"
ruff --version
