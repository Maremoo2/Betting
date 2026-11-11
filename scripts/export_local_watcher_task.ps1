param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$WorkingDirectory,
    [Parameter(Mandatory=$true)][string]$State,
    [Parameter(Mandatory=$true)][string]$Journal,
    [Parameter(Mandatory=$true)][string]$ClockServer,
    [Parameter(Mandatory=$true)][string]$OutputXml
)
$ErrorActionPreference = 'Stop'
if ($ClockServer -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*$') { throw 'Invalid clock server' }
foreach ($p in @($Python,$WorkingDirectory,$State,$Journal)) {
    if (![IO.Path]::IsPathFullyQualified($p) -or ![IO.File]::Exists($p) -and ![IO.Directory]::Exists($p)) {
        throw "Path must exist and be absolute: $p"
    }
}
$command = [Security.SecurityElement]::Escape($Python)
$cwd = [Security.SecurityElement]::Escape($WorkingDirectory)
$argsText = [Security.SecurityElement]::Escape("-m hbi.local_watcher --state `"$State`" --journal `"$Journal`" --clock-server $ClockServer")
$now = [datetime]::Now
$start = $now.Date.AddMinutes(([math]::Floor($now.TimeOfDay.TotalMinutes / 5) + 1) * 5).ToString('yyyy-MM-ddTHH:mm:ss')
@"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><TimeTrigger>
    <Repetition><Interval>PT5M</Interval></Repetition>
    <StartBoundary>$start</StartBoundary><Enabled>true</Enabled>
  </TimeTrigger></Triggers>
  <Principals><Principal id="Watcher">
    <UserId>S-1-5-19</UserId><RunLevel>LeastPrivilege</RunLevel>
  </Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Watcher"><Exec><Command>$command</Command><Arguments>$argsText</Arguments><WorkingDirectory>$cwd</WorkingDirectory></Exec></Actions>
</Task>
"@ | Set-Content -LiteralPath $OutputXml -Encoding Unicode
