# Publishes the constellation on the VPS. Run from any folder:
#   .\deploiement\publier.ps1 -Hote utilisateur@serveur -Domaine exemple.fr   # first time: prepares the VPS, then publishes
#   .\deploiement\publier.ps1 -Hote utilisateur@serveur                       # later updates
param(
    [Parameter(Mandatory = $true)][string]$Hote,
    [string]$Domaine
)
$ErrorActionPreference = 'Stop'
$racine = Split-Path $PSScriptRoot -Parent
# Connected as root: no sudo needed (and it may be missing on a minimal image).
$sudo = if ($Hote -match '^root@') { '' } else { 'sudo ' }

function Verifier([string]$etape) {
    if ($LASTEXITCODE -ne 0) { throw "Echec : $etape (code $LASTEXITCODE)." }
}

python (Join-Path $racine 'paquet_constellation_2027.py') --racine $racine
Verifier 'preparation du paquet'

if ($Domaine) {
    $prep = (ssh $Hote 'mktemp -d /tmp/boussole_prep.XXXXXX').Trim()
    Verifier 'connexion au serveur'
    $fichiers = 'preparer_vps.sh', 'installer_paquet.sh', 'Caddyfile.modele', 'boussole-constellation.service' |
        ForEach-Object { Join-Path $PSScriptRoot $_ }
    scp @fichiers "${Hote}:$prep/"
    Verifier 'envoi des fichiers de preparation'
    ssh -t $Hote "${sudo}sh $prep/preparer_vps.sh $Domaine; code=`$?; rm -rf $prep; exit `$code"
    Verifier 'preparation du serveur'
}

$archive = Join-Path $env:TEMP ('boussole_paquet_' + [guid]::NewGuid().ToString('N') + '.tgz')
try {
    tar -czf $archive -C (Join-Path $PSScriptRoot 'paquet') .
    Verifier 'creation de archive'
    $distant = (ssh $Hote 'mktemp -d /tmp/boussole_paquet.XXXXXX').Trim()
    Verifier 'connexion au serveur'
    # The installer travels with each package, so a change to it reaches the server without preparing it again.
    scp $archive (Join-Path $PSScriptRoot 'installer_paquet.sh') "${Hote}:$distant/"
    Verifier 'envoi du paquet'
    $nom = Split-Path $archive -Leaf
    ssh -t $Hote "${sudo}install -m 755 $distant/installer_paquet.sh /usr/local/sbin/boussole-installer && ${sudo}/usr/local/sbin/boussole-installer $distant/$nom; code=`$?; rm -rf $distant; exit `$code"
    Verifier 'installation du paquet'
}
finally {
    Remove-Item $archive -ErrorAction SilentlyContinue
}
Write-Output 'Publication terminee.'
