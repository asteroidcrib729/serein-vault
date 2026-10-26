[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ToolsDirectory)
$ErrorActionPreference = 'Stop'
$toolRoot = [IO.Path]::GetFullPath($ToolsDirectory)
New-Item -ItemType Directory -Path $toolRoot -Force | Out-Null
$compiler = Join-Path $toolRoot 'InnoSetup\ISCC.exe'
if (Test-Path -LiteralPath $compiler) { Write-Output $compiler; exit 0 }
$installer = Join-Path $toolRoot 'innosetup-7.1.0-x64.exe'
Invoke-WebRequest -Uri 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe' -OutFile $installer
$expected = '0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f'
if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Inno Setup checksum mismatch.' }
$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Pyrsys B.V.') { throw 'Unexpected Inno Setup signature.' }
$destination = Join-Path $toolRoot 'InnoSetup'
$process = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS', ('/DIR="' + $destination + '"')) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $compiler)) { throw 'Inno Setup bootstrap failed.' }
Write-Output $compiler
