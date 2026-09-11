$ErrorActionPreference = "Stop"
$project = Join-Path $HOME "concept-language"
$python = Join-Path $project ".venv\Scripts\python.exe"
Set-Location $project
& $python "scripts\first_analysis.py"
