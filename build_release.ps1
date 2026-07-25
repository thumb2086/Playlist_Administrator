$ErrorActionPreference = 'Stop'

Write-Host "Building release..."
flutter build windows --release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$releaseDir = "$PSScriptRoot\build\windows\x64\runner\Release"
Write-Host "Copying tools to $releaseDir..."
Copy-Item -Path "$PSScriptRoot\tools" -Destination "$releaseDir\tools" -Recurse -Force

Write-Host "Done: $releaseDir\playlist_administrator.exe"
