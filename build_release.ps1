$ErrorActionPreference = 'Stop'

# Keep the asset copy of the bridge in sync before building — the release
# EXE bundles assets\tools\flutter_download_bridge.py. Building with a stale
# copy silently reintroduces bugs (e.g. missing large-audio chunking).
Copy-Item -Path "$PSScriptRoot\tools\flutter_download_bridge.py" -Destination "$PSScriptRoot\assets\tools\flutter_download_bridge.py" -Force
# RAG scripts accompany the bridge so GUI RAG works in release too.
New-Item -ItemType Directory -Path "$PSScriptRoot\assets\tools\rag" -Force | Out-Null
Copy-Item -Path "$PSScriptRoot\rag\*.py" -Destination "$PSScriptRoot\assets\tools\rag\" -Force

Write-Host "Building release..."
flutter build windows --release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$releaseDir = "$PSScriptRoot\build\windows\x64\runner\Release"
Write-Host "Copying tools to $releaseDir..."
Copy-Item -Path "$PSScriptRoot\tools" -Destination "$releaseDir\tools" -Recurse -Force

Write-Host "Done: $releaseDir\playlist_administrator.exe"
