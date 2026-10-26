[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Installer,
      [Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$evidenceRoot = [IO.Path]::GetFullPath($EvidenceDirectory)
if (!$evidenceRoot.StartsWith(($repoRoot + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence must stay inside this repository.' }
$existing = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\FarazHussain.SereinVault_is1'
if (Test-Path -LiteralPath $existing) { throw 'An existing Serein Vault EXE installation must not be replaced by this test.' }
$testRoot = Join-Path $repoRoot ('.packaging-build\install-smoke-' + [Guid]::NewGuid().ToString('N'))
$installRoot = Join-Path $testRoot 'application'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null
$sentinel = Join-Path $testRoot 'user-data-must-survive.txt'
[IO.File]::WriteAllText($sentinel, 'Synthetic user data retained after uninstall')
$sentinelHash = (Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
$installed = $false
try {
    $installLog = Join-Path $testRoot 'install.log'
    $process = Start-Process -FilePath ([IO.Path]::GetFullPath($Installer)) -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS', ('/LOG="' + $installLog + '"'), ('/DIR="' + $installRoot + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
    $installed = $true
    $executable = Join-Path $installRoot 'SereinVault.exe'
    if (!(Test-Path -LiteralPath $executable)) { throw 'Installed executable missing.' }
    $report = Join-Path $evidenceRoot 'installed-smoke.json'
    if (Test-Path -LiteralPath $report) { throw 'Use a fresh evidence directory.' }
    $process = Start-Process -FilePath $executable -ArgumentList @('--smoke-test', ('"' + $report + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $report)) { throw 'Installed GUI/backend smoke failed.' }
    if (!(Get-Content -LiteralPath $report -Raw | ConvertFrom-Json).ok) { throw 'Installed smoke did not pass.' }
} finally {
    if ($installed) {
        $uninstaller = Join-Path $installRoot 'unins000.exe'
        $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw 'Uninstaller failed.' }
    }
}
if (Test-Path -LiteralPath (Join-Path $installRoot 'SereinVault.exe')) { throw 'Uninstall left the application executable.' }
if ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $sentinelHash) { throw 'User-data sentinel changed.' }
@{ ok=$true; exe_install=$true; installed_gui_backend=$true; uninstall=$true; separate_user_data_preserved=$true; test_root=$testRoot } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidenceRoot 'installer-validation.json') -Encoding UTF8
Write-Output 'EXE installation, installed GUI/backend, and uninstall checks passed.'
