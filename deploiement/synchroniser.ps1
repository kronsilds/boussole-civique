# Exchanges public contributions and error reports between the VPS and the local dashboard:
#   .\deploiement\synchroniser.ps1 -Hote utilisateur@serveur
# New deposits come down from the VPS, decisions taken in the dashboard go back up. Safe to run again at any time.
param([Parameter(Mandatory = $true)][string]$Hote)
$ErrorActionPreference = 'Stop'
$racine = Split-Path $PSScriptRoot -Parent
$outil = Join-Path $racine 'contributions_2027.py'
$enLigne = '/srv/boussole/donnees'
# Connected as root: no sudo needed (and it may be missing); otherwise sudo switches to the service account.
$commeService = if ($Hote -match '^root@') { 'runuser -u boussole --' } else { 'sudo -u boussole' }

function Verifier([string]$etape) {
    if ($LASTEXITCODE -ne 0) { throw "Echec : $etape (code $LASTEXITCODE)." }
}

$tmp = Join-Path $env:TEMP ('boussole_synchro_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$distant = (ssh $Hote 'd=$(mktemp -d /tmp/boussole_synchro.XXXXXX) && chmod 755 $d && echo $d').Trim()
Verifier 'connexion au serveur'
try {
    foreach ($cle in 'contributions', 'signalements') {
        $nom = "${cle}_2027.json"
        $local = Join-Path $racine "donnees\$nom"
        $copie = Join-Path $tmp $nom

        ssh $Hote "test -f $enLigne/$nom"
        if ($LASTEXITCODE -eq 0) {
            scp "${Hote}:$enLigne/$nom" $copie
            Verifier "lecture de $nom"
            python $outil fusionner --depuis $copie --dans $local --cle $cle
            Verifier "fusion locale de $nom"
        }
        if (Test-Path $local) {
            scp $local "${Hote}:$distant/$nom"
            Verifier "envoi de $nom"
            ssh -t $Hote "$commeService /usr/local/bin/boussole-python /srv/boussole/contributions_2027.py fusionner --depuis $distant/$nom --dans $enLigne/$nom --cle $cle"
            Verifier "fusion en ligne de $nom"
        }
    }
}
finally {
    ssh $Hote "rm -rf $distant"
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Output 'Synchronisation terminee.'
