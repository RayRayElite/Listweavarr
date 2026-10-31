# SPDX-License-Identifier: AGPL-3.0-only
param([ValidateSet('menu','install','update','uninstall','status','recover')][string]$Action='menu')
$ErrorActionPreference='Stop'
$logPath=Join-Path ([IO.Path]::GetTempPath()) 'Listweavarr-Playlist-Companion-setup.log'
if ($Action -eq 'menu') {
  Write-Host 'Listweavarr Playlist Companion'
  Write-Host 'Close Plex before installing, updating, removing or recovering.'
  Write-Host '1 Install / update   2 Uninstall   3 Status   4 Recover after Plex update   0 Exit'
  $choice=Read-Host 'Choose'
  $Action=switch($choice) {'1' {'update'} '2' {'uninstall'} '3' {'status'} '4' {'recover'} default {exit}}
}
$python=Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python) { throw 'Install Python 3.11 or newer from python.org, then run setup again.' }
$administrator=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Action -ne 'status' -and -not $administrator) {
  Set-Content -LiteralPath $logPath -Value 'Starting playlist companion setup...'
  $elevated=Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Action',$Action)
  Get-Content -LiteralPath $logPath
  if ($elevated.ExitCode -ne 0) { throw 'The installer did not complete. Run setup Status for details.' }
  Write-Host 'Finished. Start Plex to use the companion.'
  exit
}
& $python.Source (Join-Path $PSScriptRoot 'desktop.py') $Action 2>&1 | Tee-Object -FilePath $logPath
if ($LASTEXITCODE -ne 0) { throw 'No successful installation was reported. Check the message above.' }
