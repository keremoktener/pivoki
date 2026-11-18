# Pivoki for Windows

The x64 WPF application accepts files and folders from Explorer, the file picker and the clipboard. Home offers single-file tools and saved output packages. Studio opens the additional local file tools with the current selection. The package engine also services enabled folder rules while the desktop app is running.

## Run from source

Use the .NET 10 SDK and a Windows x64 build of the shared engine. Keep the entire engine folder together, including its runtime libraries. For a development checkout, set `PIVOKI_ENGINE` to the absolute path of `pivoki-engine.exe`. Portable distributions put it under `engine\` beside `Pivoki.exe`.

```powershell
dotnet restore windows/Pivoki.Windows/Pivoki.Windows.csproj --locked-mode
dotnet run --project windows/Pivoki.Windows/Pivoki.Windows.csproj -c Release
```

Choose **Output packages**, then select or create a package. Add images or a source folder, choose an output folder, select the folder scope and preview the final paths. **Create approved outputs** executes the displayed plan. Existing files that appeared after approval require a fresh review. **Open result folder** reveals the completed delivery. The Library lists the individual saved paths.

**Pin to wheel** adds the package to the Tools wheel for compatible selections. In **Settings → Wheel**, select visible commands, turn modifier hints on or off, and add applications where global drag shortcuts should pause. The home command list remains available. Local WPF preferences and native file history live under `%LOCALAPPDATA%\Pivoki`.

## Verification

```powershell
dotnet run --project windows/Pivoki.Verify/Pivoki.Verify.csproj -c Release
```

If `PIVOKI_ENGINE` is set, this also exercises the Windows RPC client and production engine with Unicode paths, package creation, two image outputs, cancellation and history removal. It creates an isolated temporary profile. After publishing the app, run the WPF check in a Windows desktop session.

```powershell
dotnet publish windows/Pivoki.Windows/Pivoki.Windows.csproj -c Release -r win-x64 --self-contained -o build/windows
$check = Start-Process -FilePath ./build/windows/Pivoki.exe -ArgumentList '--verify-package-window' -Wait -PassThru
if ($check.ExitCode -ne 0) { throw "WPF package check failed ($($check.ExitCode))" }
```

This check pins a package, previews two paths, introduces a competing file, reapproves the changed plan and checks the saved files and Library. For physical gesture acceptance, test an Explorer drag and modifier switch, a gesture inside an excluded application, and a full-screen application on an interactive Windows machine. Record OS build, display scale and focus behavior.

## Signed PDF inputs

Native PDF conversions, page edits, compression and metadata writes inspect the active PDF object graph. When a digital signature is present, the export dialog offers a byte-preserving archive of the original files. A single signed, unencrypted PDF can also open Studio's explicit unsigned-copy workflow. Permissions can restrict export. Viewing the document, reading a QR code, copying, and sharing original files remain available.

Detection covers reachable signature dictionaries, byte ranges, timestamp dictionaries and populated signature fields. Empty signature fields and discarded earlier revisions are distinguished. This check does not establish certificate trust, revocation status or cryptographic validity.

## Publisher-signed distribution

Run from a Windows release machine with SignTool, a trusted code-signing identity in the current user's Personal certificate store, and the complete packaged Windows engine. The publisher argument is the exact X.500 subject displayed by the signing certificate. Use a new output directory for every build.

```powershell
./windows/New-SignedRelease.ps1 -EngineDirectory $engineDir -CertificateThumbprint $thumbprint -Publisher $publisherSubject -TimestampUrl $timestampServer -OutputDirectory $newReleaseFolder -Version 0.1.0
```

The script signs and timestamps the executables and Pivoki assemblies, creates a ZIP, signs its SHA-256 catalog and verifies the extracted executables. It checks that modified temporary copies fail verification. A clean Windows host can verify the downloaded pair using the independently obtained publisher name and thumbprint.

```powershell
./windows/Test-SignedRelease.ps1 -ArchivePath $zip -CatalogPath $catalog -CertificateThumbprint $thumbprint -Publisher $publisherSubject -CheckTamperDetection
```

Record the actual SmartScreen and launch behavior on that machine. The signing script writes files locally. An optional, separately provisioned Ed25519 identity supplied through `-UpdateSigningKey` embeds its public key into the product and generates `windows-update.json` with OpenSSL. The updater reads the Pivoki release channel only in builds with that verification key. Signing and release publication are distinct steps.

Pivoki's license and the third-party notices ship beside the application. The original Nashi MIT license is included as `LICENSE-Nashi.txt`.
