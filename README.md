# Network Switch Automation Toolkit

A complete infrastructure automation suite for Cisco Catalyst switch provisioning, firmware management, and configuration lifecycle across multi-switch deployments.

**Status:** Production-ready | **Impact:** 85-90% time reduction per device

---

## Overview

This toolkit automates the full switch lifecycle:

1. **Config Backup** — Serial console and SSH-based configuration snapshots with timestamping
2. **Firmware Updates** — Hands-off IOS/IOS-XE installation via USB with live monitoring
3. **Config Modernization** — Legacy syntax translation and obsolete command purging
4. **Deployment** — Interface range batching and organized config templates

### Real-World Performance

- **Per-device setup**: Reduced from ~1 week to 3-4 hours
- **Firmware updates**: ~12-15 minutes per device (vs. 45-60 min manual)
- **Config translation**: ~2 minutes automated (vs. 30-45 min manual review)
- **Multi-device stacks**: 3-switch deployment in 8 hours (vs. 3 calendar days)

---

## Architecture

```
Backup Layer (Serial/SSH)
    ↓ (running-config.txt)
Modernize Layer (Legacy→Modern syntax)
    ↓ (clean_configs/ + interface ranges)
Firmware Layer (IOS installation + verification)
    ↓
Ready for Deployment
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
IMAGE_NAME = 'IOSIMAGE.bin'  # Filename on USB
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
[STEP 3] Running install: install add file usbflash0:IOSIMAGE.bin activate commit
[STEP 5] Monitoring reboot sequence... (Holding checks for 5 mins during POST)
[STEP 7] Verifying running software version...
Active Image: Cisco IOS XE Software, Catalyst L3 Switch Software Version 17.x.x
```

---

### 4. UpdateandRemoveOldCommands.ps1

**Translate legacy Catalyst configurations to updated Catalyst syntax. Remove deprecated commands.**

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
 switchport access vlan 12
 spanning-tree portfast

interface range Gi1/0/25 - 48
 switchport mode access
 switchport access vlan 13
```

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
IMAGE_NAME = 'IOSIMAGE.bin'
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
- Ensure PuTTY/TeraTerm/Etc... are closed (exclusive device access required)
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
- **Real-world scale** — tested on factory-fresh and legacy hardware across multiple generations
- **Production-ready** code with edge case handling

The infrastructure engineering value isn't in the individual scripts — it's in understanding provisioning workflows, identifying failure modes, and building systems that handle them reliably.

---

## License

MIT License — feel free to fork, modify, and use for your environment.

---

## Contributing

Improvements, bug reports, and site-specific enhancements are welcome.