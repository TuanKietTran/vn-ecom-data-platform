[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Output,
    [string]$Serial
)
$ErrorActionPreference = 'Stop'
$adb = Get-Command adb -ErrorAction SilentlyContinue
if (-not $adb) { throw 'adb is unavailable; capture is UNVERIFIED until Android platform tools are provided.' }
$devices = @(& $adb.Source devices | Select-Object -Skip 1 | Where-Object { $_ -match '^\S+\s+device$' })
if ($LASTEXITCODE -ne 0) { throw 'adb devices failed.' }
if ($Serial) {
    if ($devices -notmatch "^$([regex]::Escape($Serial))\s+device$") { throw "Requested adb device is not connected and authorized: $Serial" }
} elseif ($devices.Count -ne 1) {
    throw "Expected exactly one authorized adb device; found $($devices.Count). Pass -Serial when multiple devices are connected."
} else {
    $Serial = ($devices[0] -split '\s+')[0]
}
$fullOutput = [IO.Path]::GetFullPath($Output)
$directory = [IO.Path]::GetDirectoryName($fullOutput)
[IO.Directory]::CreateDirectory($directory) | Out-Null
$remote = "/sdcard/hunt-capture-$([Guid]::NewGuid().ToString('N')).png"
try {
    & $adb.Source -s $Serial shell screencap -p $remote
    if ($LASTEXITCODE -ne 0) { throw 'Device screenshot command failed.' }
    & $adb.Source -s $Serial pull $remote $fullOutput
    if ($LASTEXITCODE -ne 0) { throw 'Could not pull the device screenshot.' }
} finally {
    & $adb.Source -s $Serial shell rm -f $remote | Out-Null
}
$bytes = [IO.File]::ReadAllBytes($fullOutput)
if ($bytes.Length -lt 8 -or [BitConverter]::ToString($bytes[0..7]) -ne '89-50-4E-47-0D-0A-1A-0A') {
    Remove-Item -LiteralPath $fullOutput -Force
    throw 'Captured output is not a valid PNG signature; removed it.'
}
$hash = (Get-FileHash -LiteralPath $fullOutput -Algorithm SHA256).Hash.ToLowerInvariant()
"CAPTURED serial=$Serial path=$fullOutput bytes=$($bytes.Length) sha256=$hash"
