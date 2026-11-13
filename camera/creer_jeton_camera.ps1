# SCOT — Crée (ou renouvelle) le jeton d'accès du PC caméra et l'écrit dans camera\config.json.
#
# Le jeton ne permet QUE de créer de nouvelles images dans blob-scot : pas de lecture,
# pas de modification, pas de suppression. Il dépend de la stratégie d'accès « camera »
# du conteneur : supprimer cette stratégie révoque immédiatement le jeton.
#
#   powershell -ExecutionPolicy Bypass -File camera\creer_jeton_camera.ps1            # 1 an
#   powershell -ExecutionPolicy Bypass -File camera\creer_jeton_camera.ps1 -Revoquer  # coupe l'accès
#
# Prérequis : Azure CLI + `az login` avec un compte Owner/Contributor du stockage.
# Le jeton n'est jamais affiché : il est écrit directement dans config.json (exclu de git).
param([int]$Mois = 12, [switch]$Revoquer)

$ErrorActionPreference = "Stop"
$account = "projetscot"; $container = "blob-scot"; $policy = "camera"
$azcli = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin"
if (Test-Path $azcli) { $env:PATH = "$azcli;$env:PATH" }

$existe = az storage container policy list --account-name $account -c $container --auth-mode key --only-show-errors --query "contains(keys(@), '$policy')" -o tsv
if ($Revoquer) {
    if ($existe -eq "true") {
        az storage container policy delete --account-name $account -c $container -n $policy --auth-mode key --only-show-errors -o none
        Write-Host "Strategie '$policy' supprimee : le jeton de la camera ne fonctionne plus."
    } else { Write-Host "Aucune strategie '$policy' : rien a revoquer." }
    exit 0
}

$expiry = (Get-Date).ToUniversalTime().AddMonths($Mois).ToString("yyyy-MM-ddTHH:mmZ")
if ($existe -eq "true") {
    az storage container policy update --account-name $account -c $container -n $policy --permissions c --expiry $expiry --auth-mode key --only-show-errors -o none
} else {
    az storage container policy create --account-name $account -c $container -n $policy --permissions c --expiry $expiry --auth-mode key --only-show-errors -o none
}
$sas = az storage container generate-sas --account-name $account -n $container --policy-name $policy --https-only --auth-mode key --only-show-errors -o tsv
if (-not $sas) { throw "Generation du jeton impossible." }

$cfgPath = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path $cfgPath)) { Copy-Item (Join-Path $PSScriptRoot "config.example.json") $cfgPath }
$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$cfg.url_sas_conteneur = "https://$account.blob.core.windows.net/$container`?$sas"
$json = $cfg | ConvertTo-Json -Depth 3
[IO.File]::WriteAllText($cfgPath, $json, (New-Object Text.UTF8Encoding $false))
Write-Host "Jeton ecrit dans $cfgPath (creation seule dans $container, valable jusqu'au $expiry)."
