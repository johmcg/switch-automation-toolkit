$inputFile  = "";
$descFile   = "";
$rangeFile  = "";

$raw = Get-Content $inputFile;
$currentIface = $null;
$currentDesc  = $null;
$currentConfigs = New-Object System.Collections.Generic.List[string];

$descriptions = New-Object System.Collections.Generic.List[string];
$configGroups = [ordered]@{};

function Process-Block {
    if ($script:currentIface) {
        $iface = $script:currentIface;

        # 1. Output Descriptions File (only if description exists)
        if ($script:currentDesc) {
            $script:descriptions.Add("interface $iface`n description $($script:currentDesc)");
        }

        # 2. Group Interfaces with Identical Configurations
        if ($script:currentConfigs.Count -gt 0) {
            $sig = ($script:currentConfigs -join "`n");
            if (-not $script:configGroups.Contains($sig)) {
                $script:configGroups[$sig] = New-Object System.Collections.Generic.List[string];
            }
            $script:configGroups[$sig].Add($iface);
        }
    }
}

foreach ($line in $raw) {
    $trimmed = $line.Trim();
    if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("!")) { continue; }

    if ($trimmed -match '^\s*interface\s+(.+)') {
        Process-Block;
        $currentIface = $Matches[1];
        $currentDesc  = $null;
        $currentConfigs.Clear();
    }
    elseif ($trimmed -match '^\s*description\s+(.+)') {
        $currentDesc = $Matches[1];
    }
    else {
        if ($currentIface) {
            # --- PURGE OBSOLETE, REDUNDANT & AUTO-GENERATED COMMANDS ---
            if ($trimmed -match '^\s*srr-queue') { continue; }
            if ($trimmed -match '^\s*priority-queue') { continue; }
            if ($trimmed -match '^\s*mls qos') { continue; }
            if ($trimmed -match '^\s*trust device cisco-phone') { continue; }
            if ($trimmed -match '^\s*service-policy\s+input\s+AUTOQOS-SRND4') { continue; }
            if ($trimmed -match '^\s*service-policy\s+(input|output)\s+AutoQos') { continue; }

            # --- UPDATE TO CATALYST 9300 SYNTAX ---
            if ($trimmed -match '^\s*mls qos trust device cisco-phone') {
                $trimmed = "auto qos voip cisco-phone";
            }
            elseif ($trimmed -match '^\s*spanning-tree portfast edge') {
                $trimmed = "spanning-tree portfast";
            }

            # Append cleaned configuration line if not already added
            if (-not $currentConfigs.Contains($trimmed)) {
                $currentConfigs.Add($trimmed);
            }
        }
    }
}
Process-Block;

# Save File 1: Descriptions
$descriptions | Out-File -FilePath $descFile;

# Helper function to collapse interfaces into Cisco range syntax
function Format-InterfaceRange($ifaceList) {
    $prefixGroups = [ordered]@{};
    foreach ($iface in $ifaceList) {
        if ($iface -match '^([a-zA-Z\-]+\d+/\d+/)(\d+)$') {
            $pfx = $Matches[1];
            $port = [int]$Matches[2];
            if (-not $prefixGroups.Contains($pfx)) { 
                $prefixGroups[$pfx] = New-Object System.Collections.Generic.List[int];
            }
            $prefixGroups[$pfx].Add($port);
        }
    }

    $rangeParts = @();
    foreach ($pfx in $prefixGroups.Keys) {
        $ports = $prefixGroups[$pfx] | Sort-Object -Unique;
        $start = $ports[0];
        $prev  = $ports[0];

        for ($i = 1; $i -le $ports.Count; $i++) {
            if ($i -lt $ports.Count -and $ports[$i] -eq $prev + 1) {
                $prev = $ports[$i];
            } else {
                if ($start -eq $prev) {
                    $rangeParts += "$pfx$start";
                } else {
                    $rangeParts += "$pfx$start - $prev";
                }
                if ($i -lt $ports.Count) {
                    $start = $ports[$i];
                    $prev  = $ports[$i];
                }
            }
        }
    }
    return "interface range " + ($rangeParts -join " , ");
}

# Save File 2: Ranges & Configs
$rangeOutput = New-Object System.Collections.Generic.List[string];
foreach ($sig in $configGroups.Keys) {
    $ifaces = $configGroups[$sig];
    $header = Format-InterfaceRange $ifaces;
    $rangeOutput.Add($header);
    foreach ($cfg in ($sig -split "`n")) {
        $rangeOutput.Add(" $cfg");
    }
    $rangeOutput.Add("!");
}

$rangeOutput | Out-File -FilePath $rangeFile

Write-Host "Done! Generated clean switch configs:`n - $descFile`n - $rangeFile" -ForegroundColor Green