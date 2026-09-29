import getpass
import time
from netmiko import ConnectHandler

SWITCH_IPS = [
""
]

DEVICE_TYPE = "cisco_ios"
DELAY_SECONDS = 5  # Increased delay between switches to prevent AAA rate-limiting

COMMANDS = [
    "show run",
]

USERNAME = input("Enter SSH Username: ")
PASSWORD = getpass.getpass("Enter SSH Password: ")

for ip in SWITCH_IPS:
    device = {
        "device_type": DEVICE_TYPE,
        "host": ip,
        "username": USERNAME,
        "password": PASSWORD,
        "conn_timeout": 30,        # Waits up to 30s to establish initial TCP connection
        "auth_timeout": 30,        # Waits up to 30s for TACACS+/RADIUS authentication
        "banner_timeout": 30,      # Allows extra time for heavy switch login banners
        "global_delay_factor": 2,  # Multiplies all internal Netmiko timing intervals by 2x
    }
    
    try:
        print(f"Connecting to {ip}...")
        connection = ConnectHandler(**device)
        
        # Extract hostname dynamically from the CLI prompt
        prompt = connection.find_prompt()
        hostname = prompt.rstrip("#>").strip()
        
        # Save file named with Hostname and IP for clear identification
        filename = f"{hostname}_{ip}_config.txt"
        
        with open(filename, "w") as f:
            f.write("============================================================\n")
            f.write(f"Hostname : {hostname}\n")
            f.write(f"IP       : {ip}\n")
            f.write("============================================================\n\n")
            
            for cmd in COMMANDS:
                print(f"  --> [{hostname}] Running: {cmd}")
                output = connection.send_command(cmd)
                f.write(f"--- [COMMAND]: {cmd} ---\n")
                f.write(f"{output}\n\n")
                
        connection.disconnect()
        print(f"[{ip}] Successfully saved report to {filename}\n")
        
    except Exception as e:
        print(f"[{ip}] Failed: {e}\n")
        error_filename = f"{ip}_FAILED.txt"
        with open(error_filename, "w") as f:
            f.write(f"IP     : {ip}\n")
            f.write(f"Status : CONNECTION FAILED\n")
            f.write(f"Error  : {e}\n")
            
    time.sleep(DELAY_SECONDS)