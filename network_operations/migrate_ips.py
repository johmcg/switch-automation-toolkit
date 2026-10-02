import sys
import time
import socket
import argparse
import logging
import getpass
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import yaml
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# ==========================================
# Data Models
# ==========================================

@dataclass
class SwitchNode:
    hostname: str
    current_ip: str
    target_ip: str
    subnet_mask: str = "255.255.255.0"
    gateway: Optional[str] = None
    interface: str = "Vlan1"
    device_type: str = "cisco_ios"

@dataclass
class MigrationStep:
    step_number: int
    hostname: str
    action_type: str  # 'MOVE_TO_STAGING' or 'MOVE_TO_TARGET'
    from_ip: str
    to_ip: str
    switch: SwitchNode

# ==========================================
# Migration Planner Engine
# ==========================================

class IPMigrationPlanner:
    def __init__(self, switches: List[SwitchNode], staging_ip: str):
        self.switches = {s.hostname: s for s in switches}
        self.staging_ip = staging_ip

    def build_execution_plan(self) -> List[MigrationStep]:
        current_ips = {host: s.current_ip for host, s in self.switches.items()}
        target_ips = {host: s.target_ip for host, s in self.switches.items()}
        
        pending = set(self.switches.keys())
        plan = []
        step_counter = 1

        while pending:
            active_ips_in_network = set(current_ips.values())
            move_made = False

            # Phase 1: Move switches whose target IPs are currently unoccupied
            for host in list(pending):
                curr = current_ips[host]
                target = target_ips[host]

                if curr == target:
                    pending.remove(host)
                    move_made = True
                    break

                if target not in active_ips_in_network:
                    plan.append(MigrationStep(
                        step_number=step_counter,
                        hostname=host,
                        action_type="MOVE_TO_TARGET",
                        from_ip=curr,
                        to_ip=target,
                        switch=self.switches[host]
                    ))
                    current_ips[host] = target
                    pending.remove(host)
                    step_counter += 1
                    move_made = True
                    break

            # Phase 2: If locked in a swap cycle, move one switch to Staging IP
            if not move_made and pending:
                cycle_host = next(iter(pending))
                curr = current_ips[cycle_host]

                plan.append(MigrationStep(
                    step_number=step_counter,
                    hostname=cycle_host,
                    action_type="MOVE_TO_STAGING",
                    from_ip=curr,
                    to_ip=self.staging_ip,
                    switch=self.switches[cycle_host]
                ))
                current_ips[cycle_host] = self.staging_ip
                step_counter += 1

        return plan

# ==========================================
# Network Execution Driver
# ==========================================

def check_ip_reachability(ip: str, port: int = 22, timeout: int = 3) -> bool:
    """Checks if target TCP port (SSH) is reachable."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def execute_ip_change(step: MigrationStep, credentials: Dict[str, str]) -> bool:
    """Executes IP migration step over SSH with reload safety timer."""
    sw = step.switch
    logging.info(f"--- Step {step.step_number}: Migrating {sw.hostname} from {step.from_ip} to {step.to_ip} [{step.action_type}] ---")

    device_params = {
        'device_type': sw.device_type,
        'host': step.from_ip,
        'username': credentials['username'],
        'password': credentials['password'],
        'secret': credentials.get('secret', ''),
        'timeout': 10,
    }

    try:
        logging.info(f"[{sw.hostname}] Connecting to current IP {step.from_ip}...")
        with ConnectHandler(**device_params) as net_connect:
            if credentials.get('secret'):
                net_connect.enable()

            # 1. Arm safety rollback (reload in 5 minutes)
            logging.info(f"[{sw.hostname}] Arming safety reload timer (reload in 5)...")
            net_connect.send_command("reload in 5\n", expect_string=r'confirm')
            net_connect.send_command("\n")

            # 2. Build configuration commands
            config_cmds = [
                f"interface {sw.interface}",
                f"ip address {step.to_ip} {sw.subnet_mask}",
                "no shutdown"
            ]
            if sw.gateway:
                config_cmds.append(f"ip default-gateway {sw.gateway}")

            # 3. Apply IP changes (Connection loss expected)
            logging.info(f"[{sw.hostname}] Applying target IP {step.to_ip}...")
            try:
                net_connect.send_config_set(config_cmds, timeout=5)
            except NetmikoTimeoutException:
                logging.info(f"[{sw.hostname}] SSH session dropped as expected following IP reassignment.")

    except NetmikoAuthenticationException:
        logging.error(f"[{sw.hostname}] Authentication failed on {step.from_ip}.")
        return False
    except Exception as e:
        logging.error(f"[{sw.hostname}] Unexpected error during command push to {step.from_ip}: {str(e)}")
        return False

    # 4. Poll for SSH reachability on new IP
    logging.info(f"[{sw.hostname}] Waiting for SSH response on target IP {step.to_ip}...")
    reconnected = False
    for attempt in range(1, 13):
        time.sleep(5)
        if check_ip_reachability(step.to_ip):
            reconnected = True
            logging.info(f"[{sw.hostname}] Port 22 active on {step.to_ip} after {attempt * 5} seconds.")
            break
        logging.info(f"  Polling {step.to_ip}... (attempt {attempt}/12)")

    if not reconnected:
        logging.critical(f"[{sw.hostname}] FAILED to reach switch on {step.to_ip}. Automatic reload will trigger in 5 minutes.")
        return False

    # 5. Reconnect to new IP, cancel reload, and save config
    try:
        device_params['host'] = step.to_ip
        logging.info(f"[{sw.hostname}] Re-connecting to {step.to_ip} to finalize configuration...")
        with ConnectHandler(**device_params) as net_connect:
            if credentials.get('secret'):
                net_connect.enable()

            net_connect.send_command("reload cancel")
            net_connect.send_command("write memory")
            logging.info(f"SUCCESS: [{sw.hostname}] Migrated to {step.to_ip} and saved to NVRAM.")
            return True
            
    except Exception as e:
        logging.error(f"[{sw.hostname}] Failed to finalize and cancel reload on {step.to_ip}: {str(e)}")
        return False

# ==========================================
# Helpers & Setup
# ==========================================

def load_inventory(yaml_path: str) -> Tuple[List[SwitchNode], str]:
    """Parses YAML inventory into dataclass objects."""
    try:
        with open(yaml_path, "r") as file:
            data = yaml.safe_load(file)
        
        staging_ip = data.get("staging_ip")
        if not staging_ip:
            raise ValueError("Missing 'staging_ip' field in YAML inventory.")

        switches = [SwitchNode(**node) for node in data.get("switches", [])]
        if not switches:
            raise ValueError("No switches found under 'switches' key in YAML inventory.")

        return switches, staging_ip
    except Exception as e:
        logging.error(f"Failed to load inventory file '{yaml_path}': {str(e)}")
        sys.exit(1)

def setup_logging(log_file: str):
    """Configures concurrent console and file logging."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File Handler
    fh = logging.FileHandler(log_file)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

# ==========================================
# CLI Interface
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="Live Switch IP Address Migration Tool")
    parser.add_argument("-i", "--inventory", default="inventory.yaml", help="Path to inventory YAML file (default: inventory.yaml)")
    parser.add_argument("-l", "--log", default="migration.log", help="Path to log file (default: migration.log)")

    args = parser.parse_args()
    setup_logging(args.log)

    logging.info("Starting Switch IP Migration Planner...")
    switches, staging_ip = load_inventory(args.inventory)

    # Generate Plan
    planner = IPMigrationPlanner(switches, staging_ip=staging_ip)
    execution_plan = planner.build_execution_plan()

    # Display Plan Overview
    print("\n" + "=" * 70)
    print(f"{'STEP':<6} | {'HOSTNAME':<12} | {'FROM IP':<15} -> {'TO IP':<15} | {'ACTION'}")
    print("=" * 70)
    for step in execution_plan:
        print(f"{step.step_number:<6} | {step.hostname:<12} | {step.from_ip:<15} -> {step.to_ip:<15} | {step.action_type}")
    print("=" * 70 + "\n")

    logging.info("SAFE MODE: Plan generated and logged. Network changes are disabled by default.")

    # =========================================================================
    # LIVE EXECUTION BLOCK (DISABLED / COMMENTED OUT FOR SAFETY)
    # Uncomment the section below when you are ready to execute live changes.
    # =========================================================================
    """
    username = input("Enter SSH Username: ")
    password = getpass.getpass("Enter SSH Password: ")
    secret = getpass.getpass("Enter Enable Password (press Enter if none): ")

    credentials = {
        "username": username,
        "password": password,
        "secret": secret
    }

    confirm = input("\nExecute live IP changes according to plan? (yes/no): ").strip().lower()
    if confirm != "yes":
        logging.info("Migration aborted by user.")
        return

    for step in execution_plan:
        success = execute_ip_change(step, credentials)
        if not success:
            logging.critical(f"MIGRATION HALTED at Step {step.step_number}. Resolve issues manually before proceeding.")
            break
    """

if __name__ == "__main__":
    main()