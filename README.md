# Network Switch Automation Toolkit

A complete infrastructure automation suite for Cisco Catalyst switch provisioning, firmware management, and configuration lifecycle across multi-switch deployments.

**Status:** Production-ready | **Impact:** 85-90% time reduction per device

---

## Overview

This toolkit automates the full switch lifecycle — from initial provisioning through operational maintenance:

**Provisioning Pipeline:**
1. **Config Backup** — Serial console and SSH-based configuration snapshots with timestamping
2. **Firmware Updates** — Hands-off IOS/IOS-XE installation via USB with live monitoring
3. **Config Modernization** — Legacy syntax translation and obsolete command purging
4. **Deployment** — Interface range batching and organized config templates

**Operational Tasks:**
5. **IP Migration** — Coordinated IP address migrations with deadlock detection and safe rollback

### Real-World Performance

- **Per-device setup**: Reduced from ~1 week to 3-4 hours
- **Firmware updates**: ~12-15 minutes per device (vs. 45-60 min manual)
- **Config translation**: ~2 minutes automated (vs. 30-45 min manual review)
- **Multi-device stacks**: 3-switch deployment in 8 hours (vs. 3 calendar days)

---

## Architecture

```
PROVISIONING PIPELINE
├─ Backup Layer (Serial/SSH) → running-config.txt
├─ Modernize Layer (Legacy→Modern syntax) → clean configs
├─ Firmware Layer (IOS install + verify) → production-ready
└─ Ready for Deployment

OPERATIONAL TASKS
└─ IP Migration (Deadlock detection + staging strategy) → coordinated redeployment
```

---

## Scripts

### 1. BackupConfigConsole.py

**Backup running configuration from factory-fresh or disconnected switches via serial console.**

- Netmiko over serial (9600 baud)
- Automatic session cleanup (logs out stale sessions)
- Handles auth prompts and enable secret negotiation
- Timestamped output files
- Debug logging for troubleshooting

**Usage:**
```bash
python BackupConfigConsole.py
# Enter username, password, and enable secret when prompted
# Output: backup_config_20260928_143022.txt
```

**Inputs:**
- COM port (USB adapter)
- SSH/console username/password
- Enable secret (optional)

---

### 2. SendCommandsOverSSH.py

**Bulk command execution across multiple switch IPs with parallel config pulls.**

- Multi-switch iteration with per-device error handling
- Automatic hostname detection from CLI prompt
- Configurable command list
- Rate-limiting between connections (prevents AAA flooding)
- File naming: `{hostname}_{ip}_config.txt`
- Failed connections logged separately

**Before Running:**
```python
SWITCH_IPS = [
    "192.168.1.10",
    "192.168.1.11",
    "192.168.1.12",
]

COMMANDS = [
    "show running-config",
    "show version",
]
```

**Usage:**
```bash
python SendCommandsOverSSH.py
# Enter SSH username and password when prompted
# Output: switch-hostname_192.168.1.10_config.txt, etc.
```

---

### 3. UpdateSWSerial.py

**Fully automated IOS/IOS-XE firmware installation via USB with post-reboot cleanup.**

**7-Stage Process:**
1. Serial prep — Clears stale sessions, detects device state
2. Pre-install setup — Silence console logging, save config
3. Firmware install — Execute `install add file usbflash0:IMAGE.bin activate commit`
4. Reload confirmation — Watches for prompt, confirms Y/N
5. Reboot monitoring — 5-minute POST phase wait, then prompt detection
6. Post-reboot cleanup — Remove temporary enable secret, save config
7. Verification — Confirm new IOS version active

**Before Running:**
```python
IMAGE_NAME = 'cat9k_iosxe.17.09.04a.SPA.bin'  # Filename on USB
TEMP_PASS = 'YourTempPassword123!'             # Temporary enable secret
COM_PORT = 'COM3'                               # Serial port
```

**Usage:**
```bash
# Ensure IOS binary is on USB root directory
# Attach USB to switch USB port
python UpdateSWSerial.py
# Script monitors entire process; no interaction needed
```

**Output Example:**
```
[STEP 1] Detecting switch state and navigating to Switch#...
[STEP 3] Running install: install add file usbflash0:cat9k_iosxe.17.09.04a.SPA.bin activate commit
[STEP 5] Monitoring reboot sequence... (Holding checks for 5 mins during POST)
[STEP 7] Verifying running software version...
Active Image: Cisco IOS XE Software, Catalyst L3 Switch Software Version 17.9.4a
```

---

### 4. UpdateandRemoveOldCommands.ps1

**Translate legacy Catalyst 3850 configurations to Catalyst 9300 syntax. Remove deprecated commands.**

**Deprecation Purging:**
- `srr-queue` (old rate-limiting)
- `priority-queue` (legacy QoS)
- `mls qos` rules
- `trust device cisco-phone` (redundant)
- Auto-QoS service-policy rules

**Command Translation (3850 → 9300):**
- `mls qos trust device cisco-phone` → `auto qos voip cisco-phone`
- `spanning-tree portfast edge` → `spanning-tree portfast`

**Before Running:**
```powershell
$inputFile  = "C:\configs\running_config.txt"
$descFile   = "C:\configs\descriptions.txt"
$rangeFile  = "C:\configs\ranges_and_configs.txt"
```

**Usage:**
```powershell
.\UpdateandRemoveOldCommands.ps1
# Outputs two files:
# - descriptions.txt (every port with its description)
# - ranges_and_configs.txt (grouped configs with interface range syntax)
```

**Output Example — Descriptions:**
```
interface Gi1/0/1
 description Zone-A-Access
interface Gi1/0/2
 description Zone-B-Uplink
```

**Output Example — Ranges:**
```
interface range Gi1/0/1 - 24
 switchport mode access
 switchport access vlan 10
 spanning-tree portfast

interface range Gi1/0/25 - 48
 switchport mode access
 switchport access vlan 20
```

---

### 5. migrate_ips.py

**Intelligent IP address migration for deployed switches with deadlock detection and safe rollback.**

Orchestrates coordinated IP migrations across multiple switches. Automatically detects IP swap cycles and uses staging IP strategy to break deadlocks. Each migration step includes a 5-minute safety reload timer with automatic rollback if SSH reconnection fails.

**Features:**
- Deadlock detection: Identifies when switches need to swap IPs (circular dependencies)
- Staging IP strategy: Uses temporary IP to break swap cycles without manual intervention
- Safety rollback: 5-minute reload timer auto-triggers if target IP unreachable
- Live polling: Waits for SSH response on new IP before finalizing config
- Comprehensive logging: Tracks every step and migration success/failure
- Safe-mode default: Generates plan and displays before any live execution

**Before Running:**

Create `inventory.yaml` with switch definitions:
```yaml
staging_ip: "10.0.0.222"

switches:
  - hostname: Switch-A
    current_ip: "10.0.0.1"
    target_ip: "10.0.0.8"
    subnet_mask: "255.255.255.0"
    gateway: "10.0.0.254"
    interface: "Vlan1"
    device_type: "cisco_ios"

  - hostname: Switch-B
    current_ip: "10.0.0.8"
    target_ip: "10.0.0.1"
    subnet_mask: "255.255.255.0"
    gateway: "10.0.0.254"
    interface: "Vlan1"
    device_type: "cisco_ios"
```

**Usage:**
```bash
python migrate_ips.py -i inventory.yaml -l migration.log
# Generates and displays migration plan
# Plan shows staging steps needed to avoid IP conflicts
# Live execution section is commented out; uncomment and run with credentials
```

**Output Example:**
```
======================================================================
STEP   | HOSTNAME     | FROM IP         -> TO IP         | ACTION
======================================================================
1      | Switch-A     | 10.0.0.1        -> 10.0.0.222    | MOVE_TO_STAGING
2      | Switch-B     | 10.0.0.8        -> 10.0.0.1      | MOVE_TO_TARGET
3      | Switch-A     | 10.0.0.222      -> 10.0.0.8      | MOVE_TO_TARGET
======================================================================

SAFE MODE: Plan generated and logged. Network changes are disabled by default.
```

**Real-World Scenario:**
Reorganizing switch IPs across campus network after facility consolidation. Two switches need to swap IPs (A: 10.0.0.1 → 10.0.0.8, B: 10.0.0.8 → 10.0.0.1). Script detects the circular dependency, moves Switch-A to staging IP first, then executes the swap safely without downtime.

---

## Integration Workflow

**Scenario: Migrate legacy 2-switch stack to new 3-switch deployment**

### Step 1: Backup Legacy Configs
```bash
python SendCommandsOverSSH.py
# Output: legacy_sw1_10.1.1.5_config.txt, legacy_sw2_10.1.1.6_config.txt
```

### Step 2: Modernize Configs
```powershell
$inputFile = "legacy_sw1_10.1.1.5_config.txt"
$descFile = "sw1_descriptions.txt"
$rangeFile = "sw1_ranges.txt"
.\UpdateandRemoveOldCommands.ps1
# Output: Clean configs ready for new stack
```

### Step 3: Install New IOS on Factory Switches
```bash
# For each new switch:
python UpdateSWSerial.py
# All three now running same IOS version, ready to configure
```

### Step 4: Deploy Cleaned Configs
Paste cleaned range configs from Step 2 into new stack CLI, verify with descriptions as reference.

---

## Requirements

### Python Scripts (BackupConfigConsole.py, SendCommandsOverSSH.py, UpdateSWSerial.py)
- Python 3.8+
- `netmiko` for device automation
  ```bash
  pip install netmiko
  ```
- `pyserial` for serial communication
  ```bash
  pip install pyserial
  ```
- USB-to-serial adapter (for console methods)

### PowerShell Script (UpdateandRemoveOldCommands.ps1)
- PowerShell 5.0+ (Windows)
- Text editor or VS Code

### Hardware
- Cisco Catalyst switch with USB port (for firmware updates)
- USB flash drive with IOS/IOS-XE binary (for firmware method)

---

## Configuration

### BackupConfigConsole.py
Check Device Manager for correct COM port, update:
```python
COM_PORT = 'COM3'
```

### SendCommandsOverSSH.py
Populate switch IP list and desired commands:
```python
SWITCH_IPS = ["192.168.1.10", "192.168.1.11", ...]
COMMANDS = ["show running-config", "show version"]
```

### UpdateSWSerial.py
Set USB image name and temporary password:
```python
IMAGE_NAME = 'cat9k_iosxe.17.09.04a.SPA.bin'
TEMP_PASS = 'YourTempPassword123!'
COM_PORT = 'COM3'
```

### UpdateandRemoveOldCommands.ps1
Set file paths:
```powershell
$inputFile  = "C:\configs\running_config.txt"
$descFile   = "C:\configs\descriptions.txt"
$rangeFile  = "C:\configs\ranges.txt"
```

---

## Troubleshooting

### Serial Connection Issues
- Ensure PuTTY/TeraTerm are closed (exclusive device access required)
- Check Device Manager for correct COM port
- Verify USB-to-serial driver is installed
- Test with manual serial terminal (9600 baud) first

### SSH Authentication Failures
- Confirm AAA/TACACS+ server is reachable
- Check `serial_debug.log` for prompt-level details
- Verify account has privilege level 15

### Firmware Install Hangs
- USB image must be in root of USB flash (not subdirectory)
- Minimum 2 GB USB drive recommended
- POST phase waits 5 minutes before checking for prompts (expected behavior)
- If stuck beyond 15 minutes, use serial monitor to investigate

### Config Modernization Gaps
- Script handles common deprecated commands
- Add custom mappings in the translation section for site-specific syntax
- Always review generated configs before deployment
- Test on lab switch first

---

## Key Takeaways

This toolkit demonstrates:
- **Reliable automation** around inherently unreliable hardware (serial consoles, multi-stage boot sequences)
- **Error resilience** with graceful failure handling and logging
- **Real-world scale** tested on factory-fresh and legacy hardware across multiple generations
- **Production-ready** code with edge case handling

The infrastructure engineering value isn't in the individual scripts — it's in understanding provisioning workflows, identifying failure modes, and building systems that handle them reliably.

---

## License

MIT License — feel free to fork, modify, and use for your environment.

---

## Contributing

Improvements, bug reports, and site-specific enhancements are welcome.