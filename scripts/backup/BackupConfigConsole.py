import time
import serial
from datetime import datetime
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
import getpass

input_username = input("Enter your username: ")
input_password = getpass.getpass("Enter your password: ")
input_secret = getpass.getpass("Enter enable password (press Enter if same as login password): ")

# Fallback: Use login password as enable secret if left blank
if not input_secret:
    input_secret = input_password

COM_PORT = 'COM3'  # Update with your COM port

# --- STEP 1: Smart Serial Clean-Up ---
print("\nChecking serial line state...")
try:
    ser = serial.Serial(COM_PORT, 9600, timeout=2)
    ser.write(b'\r')
    time.sleep(1)
    
    # Read whatever text is sitting on the screen
    buffer = ser.read_all().decode('utf-8', errors='ignore')
    
    # If the switch was left logged in (> or #), log out cleanly to start fresh
    if '#' in buffer or '>' in buffer:
        print("Line was left logged in. Resetting prompt session...")
        ser.write(b'exit\r')
        time.sleep(1)
        
    ser.close()
    print("Serial line clean! Handing over to Netmiko...")
except Exception as e:
    print(f"Serial cleanup note: {e}")

# --- STEP 2: Netmiko Connection ---
device = {
    'device_type': 'cisco_ios_serial',
    'serial_settings': {
        'port': COM_PORT,
        'baudrate': 9600,
    },
    'username': input_username,
    'password': input_password,
    'secret': input_secret,
    'auth_timeout': 60,
    'global_delay_factor': 3,
    'fast_cli': False,
    'session_log': 'serial_debug.log',
}

try:
    print("\nConnecting to switch via Netmiko...")
    with ConnectHandler(**device) as net_connect:
        
        # Verify and elevate to enable mode (#)
        if not net_connect.check_enable_mode():
            print("Entering enable mode (#)...")
            net_connect.enable()
        
        print("Successfully in Enable Mode (#)!")
        print("Fetching running configuration (please wait ~30-60s over serial)...")
        output = net_connect.send_command('show running-config', read_timeout=120)

    filename = f"backup_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w') as f:
        f.write(output)

    print(f"\nSUCCESS! Config saved to: {filename}")

except NetmikoAuthenticationException:
    print("\nAuthentication failed!")
    print("Check 'serial_debug.log' to see if the switch rejected login or enable mode.")
except NetmikoTimeoutException:
    print("\nConnection timed out. Ensure PuTTY / TeraTerm are completely closed.")
except Exception as e:
    print(f"\nAn error occurred: {e}")