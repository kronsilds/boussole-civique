# Draws the social sharing preview (Open Graph, 1200x630) into web/partage_2027.png with Windows GDI+.
#   .\deploiement\image_partage.ps1
# Decorative star field in the candidates' palette: no real positions, no names, so the preview stays neutral.
# Deterministic (fixed seed): running it again gives the same image.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$racine = Split-Path $PSScriptRoot -Parent
$sortie = Join-Path $racine 'web\partage_2027.png'
$e = [char]0xE9

$L = 1200; $H = 630
$img = New-Object System.Drawing.Bitmap $L, $H
$g = [System.Drawing.Graphics]::FromImage($img)
$g.SmoothingMode = 'AntiAlias'
$g.TextRenderingHint = 'AntiAliasGridFit'
function Couleur([string]$hex, [int]$a = 255) {
    $c = [System.Drawing.ColorTranslator]::FromHtml($hex); [System.Drawing.Color]::FromArgb($a, $c)
}
$g.Clear((Couleur '#121211'))

$palette = '#7F1D1D', '#D97706', '#CA8A04', '#A21CAF', '#7C3AED', '#0891B2', '#DB2777', '#881337', '#1E3A8A', '#4F46E5',
    '#C0265A', '#0284C7', '#78350F', '#1D4ED8', '#DC2626', '#EA580C', '#16A34A', '#64748B', '#334155'
$rnd = New-Object System.Random 2027
$etoiles = @()
for ($i = 0; $i -lt 340; $i++) {
    $x = 380 + [math]::Pow($rnd.NextDouble(), 0.8) * 800
    $y = 25 + $rnd.NextDouble() * ($H - 50)
    $r = 1.4 + [math]::Pow($rnd.NextDouble(), 3) * 5.5
    $etoiles += [pscustomobject]@{ x = $x; y = $y; r = $r; c = $palette[$rnd.Next($palette.Count)] }
}

# Constellation lines between neighbouring bright stars.
$brillantes = $etoiles | Where-Object { $_.r -gt 3.6 }
$trait = New-Object System.Drawing.Pen (Couleur '#8a8984' 70), 1.2
foreach ($a in $brillantes) {
    $voisine = $brillantes | Where-Object { $_ -ne $a } |
        Sort-Object { [math]::Pow($_.x - $a.x, 2) + [math]::Pow($_.y - $a.y, 2) } | Select-Object -First 1
    if ($voisine -and ([math]::Pow($voisine.x - $a.x, 2) + [math]::Pow($voisine.y - $a.y, 2)) -lt 150 * 150) {
        $g.DrawLine($trait, [float]$a.x, [float]$a.y, [float]$voisine.x, [float]$voisine.y)
    }
}
foreach ($s in $etoiles) {
    if ($s.r -gt 3.6) {
        $halo = New-Object System.Drawing.SolidBrush (Couleur $s.c 60)
        $g.FillEllipse($halo, [float]($s.x - $s.r * 2.2), [float]($s.y - $s.r * 2.2), [float]($s.r * 4.4), [float]($s.r * 4.4))
    }
    $pinceau = New-Object System.Drawing.SolidBrush (Couleur $s.c 235)
    $g.FillEllipse($pinceau, [float]($s.x - $s.r), [float]($s.y - $s.r), [float]($s.r * 2), [float]($s.r * 2))
}

# Fade the field under the text.
$g.FillRectangle((New-Object System.Drawing.SolidBrush (Couleur '#121211' 235)), 0, 0, 560, $H)
$fondu = New-Object System.Drawing.Drawing2D.LinearGradientBrush (New-Object System.Drawing.Point 559, 0),
    (New-Object System.Drawing.Point 840, 0), (Couleur '#121211' 235), (Couleur '#121211' 0)
$g.FillRectangle($fondu, 560, 0, 280, $H)

# Logo: the three stars of the page icon.
function Etoile([float]$cx, [float]$cy, [float]$R, [string]$hex, [string]$contour) {
    $pts = for ($k = 0; $k -lt 10; $k++) {
        $rr = if ($k % 2) { $R * 0.45 } else { $R }
        $ang = -[math]::PI / 2 + $k * [math]::PI / 5
        New-Object System.Drawing.PointF ([float]($cx + $rr * [math]::Cos($ang))), ([float]($cy + $rr * [math]::Sin($ang)))
    }
    $g.FillPolygon((New-Object System.Drawing.SolidBrush (Couleur $hex)), [System.Drawing.PointF[]]$pts)
    if ($contour) { $g.DrawPolygon((New-Object System.Drawing.Pen (Couleur $contour), 2.5), [System.Drawing.PointF[]]$pts) }
}
$lien = New-Object System.Drawing.Pen (Couleur '#8a8984'), 3
$g.DrawLines($lien, [System.Drawing.PointF[]]@((New-Object System.Drawing.PointF 86, 112), (New-Object System.Drawing.PointF 130, 78),
    (New-Object System.Drawing.PointF 174, 104)))
Etoile 86 112 20 '#2a4fc4' $null
Etoile 130 78 22 '#ffffff' '#55544f'
Etoile 174 104 20 '#dc3540' $null

$blanc = New-Object System.Drawing.SolidBrush (Couleur '#f4f3f0')
$gris = New-Object System.Drawing.SolidBrush (Couleur '#b5b3ab')
$bleu = New-Object System.Drawing.SolidBrush (Couleur '#8fb0ff')
$titre = New-Object System.Drawing.Font 'Segoe UI Semibold', 60, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Pixel)
$texte = New-Object System.Drawing.Font 'Segoe UI', 29, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Pixel)
$domaine = New-Object System.Drawing.Font 'Segoe UI Semibold', 30, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Pixel)
$g.DrawString('Constellation des', $titre, $blanc, 66, 168)
$g.DrawString('programmes 2027', $titre, $blanc, 66, 242)
$y = 352
foreach ($ligne in "Les propositions des candidats $([char]0xE0) la", "pr${e}sidentielle, sourc${e}es et plac${e}es",
    'par des formules publiques.') {
    $g.DrawString($ligne, $texte, $gris, 70, $y); $y += 42
}
$g.DrawString('atlasdesprogrammes.fr', $domaine, $bleu, 70, 538)

$g.Dispose()
$img.Save($sortie, [System.Drawing.Imaging.ImageFormat]::Png)
$img.Dispose()
Write-Output "Image ecrite : $sortie ($([math]::Round((Get-Item $sortie).Length / 1KB)) Ko)"
