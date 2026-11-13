# SCOT — Lance le veilleur caméra automatiquement à l'ouverture de session Windows,
# en arrière-plan (sans fenêtre), et le relance s'il s'arrête.
#
#   powershell -ExecutionPolicy Bypass -File camera\installer_tache.ps1               # installer
#   powershell -ExecutionPolicy Bypass -File camera\installer_tache.ps1 -Desinstaller # retirer
#
# À exécuter sur le PC du montage, après avoir rempli camera\config.json.
# Suivi : camera\logs\scot_camera.log
param([switch]$Desinstaller)

$ErrorActionPreference = "Stop"
$nom = "SCOT - Veilleur camera"

if ($Desinstaller) {
    Unregister-ScheduledTask -TaskName $nom -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tache '$nom' supprimee."
    exit 0
}

$camera = $PSScriptRoot
$repo = Split-Path $camera -Parent
$pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "Environnement Python introuvable : $pythonw" }
if (-not (Test-Path (Join-Path $camera "config.json"))) { throw "camera\config.json manquant (voir config.example.json)." }

$action   = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$camera\scot_camera.py`"" -WorkingDirectory $repo
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $nom -Action $action -Trigger $trigger -Settings $settings `
    -Description "Envoie les images du SDK camera vers Azure (SCOT)" -Force | Out-Null
Start-ScheduledTask -TaskName $nom
Write-Host "Tache '$nom' installee et demarree. Logs : $camera\logs\scot_camera.log"
