param(
    [string]$BaseUrl = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"

$health = Invoke-RestMethod -Uri "$BaseUrl/api/v1/health"
if ($health.status -ne "alive") { throw "backend health check failed" }

$page = Invoke-WebRequest -UseBasicParsing -Uri $BaseUrl
if ($page.StatusCode -ne 200 -or $page.Content -notmatch "LawAgent") {
    throw "frontend smoke check failed"
}

$body = @{ message = "劳动合同法第四十七条规定了什么？" } | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/chat" -ContentType "application/json" -Body $body
if (-not $run.run_id -or -not $run.result.status) { throw "chat workflow smoke check failed" }

Write-Output "SMOKE_OK run_id=$($run.run_id) status=$($run.result.status) evidence=$($run.result.evidence.Count)"

