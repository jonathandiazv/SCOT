# Lance l'app SCOT en local, connectée aux vraies ressources Azure.
# Prérequis : `az login` fait une fois, et le venv créé (voir README).
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$azcli = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin"
if (Test-Path $azcli) { $env:PATH = "$azcli;$env:PATH" }   # DefaultAzureCredential utilise `az`
Set-Location $PSScriptRoot
& "$root\.venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.headless true @args
