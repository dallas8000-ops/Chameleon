# Shows an exported video's length, its streams and how loud its sound is (to spot silent exports).
#   .\check-video.ps1 -File "local-fixtures\exports\Ep 1 They Called Me Muzungu.mp4"
param([Parameter(Mandatory)][string]$File)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$path = (Resolve-Path $File).Path

. "$root\local-env.ps1"
$probe = if ($env:FFPROBE_BINARY) { $env:FFPROBE_BINARY } else { 'ffprobe' }
$ffmpeg = if ($env:FFMPEG_BINARY) { $env:FFMPEG_BINARY } else { 'ffmpeg' }
& $probe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,sample_rate,channels -of default=noprint_wrappers=1 $path
# mean_volume near -91 dB means the sound track is silent. ffmpeg reports on stderr, which is not an error here.
$ErrorActionPreference = 'Continue'
$report = & $ffmpeg -hide_banner -nostats -i $path -map 0:a:0 -af volumedetect -f null NUL 2>&1 | ForEach-Object { "$_" }
$report | Select-String 'mean_volume|max_volume'
