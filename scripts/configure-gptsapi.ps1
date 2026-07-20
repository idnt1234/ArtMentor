$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
$examplePath = Join-Path $projectRoot ".env.example"

if (Test-Path -LiteralPath $envPath) {
    $content = [IO.File]::ReadAllText($envPath)
} else {
    $content = [IO.File]::ReadAllText($examplePath)
}

$secureKey = Read-Host "Paste your WildAI / GPTsAPI key (input is hidden)" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plainKey) -or $plainKey.Contains("`n") -or $plainKey.Contains("`r")) {
        throw "A non-empty, single-line API key is required."
    }

    $model = Read-Host "Vision model id [gpt-5.6-terra]"
    if ([string]::IsNullOrWhiteSpace($model)) {
        $model = "gpt-5.6-terra"
    }

    function Set-DotEnvValue {
        param([string]$Text, [string]$Name, [string]$Value)
        $pattern = "(?m)^$([regex]::Escape($Name))=.*$"
        if ([regex]::IsMatch($Text, $pattern)) {
            return [regex]::Replace(
                $Text,
                $pattern,
                [Text.RegularExpressions.MatchEvaluator]{ param($match) "$Name=$Value" }
            )
        }
        return $Text.TrimEnd() + [Environment]::NewLine + "$Name=$Value" + [Environment]::NewLine
    }

    # 仅更新第三方提供者配置，保留现有的官方 OpenAI key 作为可选通道。
    $content = Set-DotEnvValue $content "AI_PROVIDER" "gptsapi"
    $content = Set-DotEnvValue $content "GPTSAPI_KEY" $plainKey
    $content = Set-DotEnvValue $content "GPTSAPI_BASE_URL" "https://api.gptsapi.net/v1"
    $content = Set-DotEnvValue $content "GPTSAPI_MODEL" $model.Trim()
    [IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
    Write-Host "WildAI / GPTsAPI configuration saved to the private .env file."
} finally {
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    $plainKey = $null
}
