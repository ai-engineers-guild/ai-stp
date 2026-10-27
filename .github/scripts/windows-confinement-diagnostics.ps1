# Read existing event channels only; never enable logs, tracing, audit or privileges.
# https://learn.microsoft.com/powershell/module/microsoft.powershell.diagnostics/get-winevent
param(
    [Parameter(Mandatory)][uint32[]]$OwnedProcessIds,
    [Parameter(Mandatory)][datetime]$StartTime,
    [Parameter(Mandatory)][datetime]$EndTime
)

$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows' -or
    $OwnedProcessIds.Count -lt 1 -or $OwnedProcessIds.Count -gt 4 -or
    @($OwnedProcessIds | Where-Object { $_ -eq 0 }).Count -ne 0 -or
    $EndTime -lt $StartTime -or ($EndTime - $StartTime).TotalMinutes -gt 5) {
    throw 'Bounded disposable CI process observations required'
}

$channels = @(
    'Microsoft-Windows-AppModel-Runtime/Admin',
    'Microsoft-Windows-CodeIntegrity/Operational'
)
foreach ($channel in $channels) {
    try {
        $configuration = Get-WinEvent -ListLog $channel -ErrorAction Stop
        if (-not $configuration.IsEnabled) {
            @{ diagnostic = 'owned_event_channel'; channel = $channel; enabled = $false } |
                ConvertTo-Json -Compress | Write-Output
            continue
        }
        try {
            $records = @(Get-WinEvent -FilterHashtable @{
                LogName = $channel; StartTime = $StartTime; EndTime = $EndTime
            } -MaxEvents 64 -ErrorAction Stop)
        } catch {
            if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw }
            $records = @()
        }
        $matched = 0
        foreach ($record in $records) {
            try {
                $encoded = $record.ToXml()
                if ($encoded.Length -gt 65536) { throw 'Event metadata exceeded its bound' }
                [xml]$document = $encoded
                $processes = @([uint32]$document.Event.System.Execution.ProcessID)
                foreach ($field in $document.Event.EventData.Data) {
                    if ($field.Name -in @('ProcessId', 'ProcessID', 'ClientProcessId', 'CallerProcessId')) {
                        $value = [string]$field.'#text'
                        if ($value -match '^[0-9]{1,10}$') { $processes += [uint32]$value }
                        elseif ($value -match '^0x[0-9a-fA-F]{1,8}$') {
                            $processes += [Convert]::ToUInt32($value.Substring(2), 16)
                        }
                    }
                }
                $owned = @($processes | Where-Object { $_ -in $OwnedProcessIds } | Select-Object -Unique)
                if ($owned.Count -eq 0) { continue }
                $matched++
                # Do not emit messages, paths, package names, user data or raw XML.
                @{ diagnostic = 'owned_process_event'; channel = $channel;
                    event_id = [uint32]$record.Id; version = [uint32]$record.Version;
                    level = [uint32]$record.Level; owned_process_ids = $owned } |
                    ConvertTo-Json -Compress | Write-Output
            } finally {
                $record.Dispose()
            }
        }
        @{ diagnostic = 'owned_event_channel'; channel = $channel; enabled = $true;
            observed = $records.Count; bound_reached = ($records.Count -eq 64); matched = $matched;
            absence_proves_no_denial = $false } | ConvertTo-Json -Compress | Write-Output
    } catch {
        @{ diagnostic = 'owned_event_read_unavailable'; channel = $channel;
            native_code = $_.Exception.HResult } | ConvertTo-Json -Compress | Write-Output
    }
}
