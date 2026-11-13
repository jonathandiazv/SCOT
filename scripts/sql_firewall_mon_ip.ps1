# SCOT — Autorise l'IP publique actuelle de ce PC sur le serveur Azure SQL.
#
# À lancer quand on change de réseau (maison, école, 4G…) :
#   powershell -ExecutionPolicy Bypass -File scripts\sql_firewall_mon_ip.ps1
#
# Crée ou met à jour UNE règle par personne, nommée d'après le compte Azure
# (ex. PC-arthur.col). Prérequis : Azure CLI installé et `az login` fait.

$ErrorActionPreference = "Stop"
$rg     = "VisualStudioOnline-E84EAA5FD02E457DBDF1D43E9E02F69B"
$server = "projectscot"

$azcli = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin"
if (Test-Path $azcli) { $env:PATH = "$azcli;$env:PATH" }

$user = (az account show --query user.name -o tsv)
if (-not $user) { throw "Pas connecté : lancez d'abord `az login`." }
$rule = "PC-" + ($user.Split("@")[0])

$ip = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 15).Trim()
Write-Host "Compte : $user"
Write-Host "IP publique : $ip"

$exists = az sql server firewall-rule list -g $rg -s $server --query "[?name=='$rule'] | length(@)" -o tsv
if ($exists -eq "1") {
    az sql server firewall-rule update -g $rg -s $server -n $rule --start-ip-address $ip --end-ip-address $ip -o none
    Write-Host "Règle $rule mise à jour."
} else {
    az sql server firewall-rule create -g $rg -s $server -n $rule --start-ip-address $ip --end-ip-address $ip -o none
    Write-Host "Règle $rule créée."
}
Write-Host "La prise en compte peut prendre jusqu'à 5 minutes."
