[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ArchivePath,
    [Parameter(Mandatory)][string]$CatalogPath,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$CertificateThumbprint,
    [Parameter(Mandatory)][string]$Publisher,
    [switch]$CheckTamperDetection
)

$ErrorActionPreference = 'Stop'
function Assert-PublisherSignature([string]$File) {
    $signature = Get-AuthenticodeSignature -LiteralPath $File
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.TimeStamperCertificate) {
        throw "A trusted timestamped signature is required on $File ($($signature.Status))."
    }
    $cert = $signature.SignerCertificate
    if ($cert.Thumbprint -ne $CertificateThumbprint -or $cert.Subject -cne $Publisher) {
        throw "Unexpected signing certificate or publisher on $File."
    }
}
$archive = Get-Item -LiteralPath $ArchivePath
$catalog = Get-Item -LiteralPath $CatalogPath
Assert-PublisherSignature $catalog.FullName
$stage = Join-Path ([IO.Path]::GetTempPath()) ('pivoki-verify-' + [guid]::NewGuid())
try {
    $archiveFolder = New-Item -ItemType Directory -Path (Join-Path $stage 'archive')
    Copy-Item -LiteralPath $archive.FullName -Destination $archiveFolder.FullName
    $result = Test-FileCatalog -Path $archiveFolder.FullName -CatalogFilePath $catalog.FullName -Detailed
    if ($result.Status -ne 'Valid' -or $result.HashAlgorithm -ne 'SHA256') {
        throw 'The archive differs from its signed SHA-256 catalog.'
    }
    $expanded = Join-Path $stage 'app'
    Expand-Archive -LiteralPath (Join-Path $archiveFolder.FullName $archive.Name) -DestinationPath $expanded
    foreach ($required in 'Pivoki.exe','Pivoki.dll','Pivoki.Core.dll','engine/pivoki-engine.exe') {
        Assert-PublisherSignature (Join-Path $expanded $required)
    }
    Get-ChildItem -LiteralPath $expanded -Recurse -File | Where-Object { $_.Extension -in '.exe','.msi' } |
        ForEach-Object { Assert-PublisherSignature $_.FullName }
    $verifiedArchive = Join-Path $archiveFolder.FullName $archive.Name
    $digest = (Get-FileHash -LiteralPath $verifiedArchive -Algorithm SHA256).Hash
    if ($CheckTamperDetection) {
        # Only alter our temporary copies. Check both the embedded PE signature and detached archive catalog.
        $testExe = Join-Path $expanded 'Pivoki.exe'
        $pe = [IO.File]::Open($testExe, 'Open', 'ReadWrite', 'None')
        try {
            $pe.Position = 0x40
            $original = $pe.ReadByte()
            $pe.Position = 0x40
            $pe.WriteByte([byte]($original -bxor 1))
        } finally { $pe.Dispose() }
        if ((Get-AuthenticodeSignature -LiteralPath $testExe).Status -eq 'Valid') {
            throw 'The modified executable still verified.'
        }
        $zip = [IO.File]::Open($verifiedArchive, 'Append')
        try { $zip.WriteByte(0x42) } finally { $zip.Dispose() }
        if ((Test-FileCatalog -Path $archiveFolder.FullName -CatalogFilePath $catalog.FullName) -eq 'Valid') {
            throw 'The modified release archive still verified.'
        }
    }
    [pscustomobject]@{ Archive=$archive.Name; Publisher=$Publisher; Thumbprint=$CertificateThumbprint;
        SHA256=$digest; Status='Verified' }
}
finally { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }
