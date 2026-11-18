[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$EngineDirectory,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$CertificateThumbprint,
    [Parameter(Mandatory)][string]$Publisher,
    [Parameter(Mandatory)][uri]$TimestampUrl,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '0.1.0',
    [string]$SignTool = 'signtool.exe',
    [string]$UpdateSigningKey
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Signing requires a Windows release host.' }
if ($TimestampUrl.Scheme -notin 'http','https') { throw 'Supply an RFC 3161 timestamp server URL.' }
$cert = Get-Item -LiteralPath "Cert:\CurrentUser\My\$CertificateThumbprint"
if (!$cert.HasPrivateKey -or $cert.Subject -cne $Publisher) { throw 'The requested publisher identity is unavailable.' }
$engine = Get-Item -LiteralPath $EngineDirectory
if (!(Test-Path -LiteralPath (Join-Path $engine.FullName 'pivoki-engine.exe') -PathType Leaf)) {
    throw 'Supply the packaged Windows engine directory containing pivoki-engine.exe.'
}
$tool = (Get-Command $SignTool -CommandType Application).Source
$project = Join-Path $PSScriptRoot 'Pivoki.Windows/Pivoki.Windows.csproj'
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $destination) { throw 'Choose a new output directory for this release.' }
$parent = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
$stage = Join-Path $parent.FullName ('.pivoki-sign-' + [guid]::NewGuid())
function Sign-File([string]$File) {
    & $tool sign /sha1 $CertificateThumbprint /s My /fd SHA256 /tr $TimestampUrl.AbsoluteUri /td SHA256 $File
    if ($LASTEXITCODE -ne 0) { throw "Authenticode signing failed on $File." }
    & $tool verify /pa /tw $File
    if ($LASTEXITCODE -ne 0) { throw "Timestamp or trust verification failed on $File." }
}
try {
    $app = [IO.Directory]::CreateDirectory((Join-Path $stage 'app'))
    $release = [IO.Directory]::CreateDirectory((Join-Path $stage 'release'))
    $archiveFolder = [IO.Directory]::CreateDirectory((Join-Path $stage 'archive'))
    $buildArgs = @("-p:Version=$Version")
    if ($UpdateSigningKey) {
        $key = (Get-Item -LiteralPath $UpdateSigningKey).FullName
        $der = Join-Path $stage 'public.der'
        & openssl pkey -in $key -pubout -outform DER -out $der
        if ($LASTEXITCODE -ne 0) { throw 'Could not read the supplied Ed25519 update identity.' }
        $bytes = [IO.File]::ReadAllBytes($der)
        if ($bytes.Length -ne 44 -or [BitConverter]::ToString($bytes,0,12) -ne '30-2A-30-05-06-03-2B-65-70-03-21-00') {
            throw 'The update signing identity must use Ed25519.'
        }
        $buildArgs += '-p:PivokiUpdateKey=' + [Convert]::ToBase64String($bytes,12,32)
    }
    & dotnet restore $project --locked-mode
    if ($LASTEXITCODE -ne 0) { throw 'Locked dependency restore failed.' }
    & dotnet publish $project --no-restore -c Release -r win-x64 --self-contained -o $app.FullName @buildArgs
    if ($LASTEXITCODE -ne 0) { throw 'WPF publish failed.' }
    $engineTarget = [IO.Directory]::CreateDirectory((Join-Path $app.FullName 'engine'))
    Get-ChildItem -LiteralPath $engine.FullName -Force | Copy-Item -Destination $engineTarget.FullName -Recurse
    foreach ($file in Get-ChildItem -LiteralPath $app.FullName -Recurse -File) {
        if ($file.Extension -in '.exe','.msi' -or $file.Name -in 'Pivoki.dll','Pivoki.Core.dll') { Sign-File $file.FullName }
    }
    $archiveName = "Pivoki-$Version-win-x64.zip"
    $archive = Join-Path $archiveFolder.FullName $archiveName
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($app.FullName,$archive)
    $catalog = Join-Path $release.FullName "$archiveName.cat"
    New-FileCatalog -Path $archiveFolder.FullName -CatalogVersion 2 -CatalogFilePath $catalog | Out-Null
    Sign-File $catalog
    & (Join-Path $PSScriptRoot 'Test-SignedRelease.ps1') -ArchivePath $archive -CatalogPath $catalog -CertificateThumbprint $CertificateThumbprint -Publisher $Publisher -CheckTamperDetection
    if ($UpdateSigningKey) {
        $signaturePath = Join-Path $stage 'update.sig'
        & openssl pkeyutl -sign -rawin -inkey $key -in $archive -out $signaturePath
        if ($LASTEXITCODE -ne 0) { throw 'Update manifest signing failed.' }
        $signature = [IO.File]::ReadAllBytes($signaturePath)
        if ($signature.Length -ne 64) { throw 'Expected a 64-byte Ed25519 signature.' }
        $manifest = @{ version=$Version; url="https://github.com/keremoktener/pivoki/releases/download/v$Version/$archiveName";
            length=(Get-Item -LiteralPath $archive).Length; edSignature=[Convert]::ToBase64String($signature) } | ConvertTo-Json
        [IO.File]::WriteAllText((Join-Path $release.FullName 'windows-update.json'),$manifest)
    }
    Move-Item -LiteralPath $archive -Destination $release.FullName
    [IO.Directory]::Move($release.FullName,$destination)
    Write-Output "Verified release files in $destination"
}
finally { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }
