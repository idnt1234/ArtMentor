$ErrorActionPreference = "Stop"
$workerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "D:\ArtMentorPose\envs\mmpose-py310\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "MMPose Python was not found at $python"
}

$env:ARTMENTOR_POSE_HOME = "D:\ArtMentorPose"
$env:POSE_DEVICE = "auto"
$env:POSE_ALLOW_UNAUTHENTICATED = "true"
$env:POSE_REQUIRE_CUDA = "true"
$env:PYTHONNOUSERSITE = "1"
$env:PIP_USER = "false"
$env:PYTHONPATH = $null
$env:PIP_CACHE_DIR = "D:\ArtMentorPose\cache\pip"
$env:TORCH_HOME = "D:\ArtMentorPose\cache\torch"
$env:MMENGINE_HOME = "D:\ArtMentorPose\cache\mmengine"
$env:TEMP = "D:\ArtMentorPose\cache\tmp"
$env:TMP = $env:TEMP
& $python -m uvicorn app:app --app-dir $workerRoot --host 127.0.0.1 --port 8011
