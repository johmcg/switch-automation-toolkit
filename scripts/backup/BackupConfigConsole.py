import time
import serial
from datetime import datetime
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
import getpass


input_username = input("Enter your username: ")
input_password = getpass.getpass("Enter your password: ")
input_secret = getpass.getpass("Enter enable password (press Enter if none): ")

COM_PORT = 'COM3'  # Update with your COM port

# --- STEP 1: Smart Serial Clean-Up ---
print("Checking serial line state...")
try:
    ser = serial.Serial(COM_PORT, 9600, timeout=2)
    ser.write(b'\r\n\r\n')
    time.sleep(1)
    
    # Read whatever text is sitting on the screen
    buffer = ser.read_all().decode('utf-8', errors='ignore')
    
    # If the switch was left logged in (> or #), log out completely
    if '#' in buffer or '>' in buffer:
        print("Line was left logged in from a previous crash. Logging out...")
        ser.write(b'exit\r\n')
        time.sleep(1)
        ser.write(b'exit\r\n')
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
    'username': input_username,   # Your local username
    'password': input_password,   # Your local password
    'secret': input_secret,    # Your enable password
    'auth_timeout': 60,
    'global_delay_factor': 3,
    'fast_cli': False,
    'session_log': 'serial_debug.log',
}

try:
    print("Connecting to switch via Netmiko...")
    with ConnectHandler(**device) as net_connect:
        if device['secret']:
            print("Entering enable mode...")
            net_connect.enable()
        
        print("Fetching running configuration (please wait ~30-60s over serial)...")
        output = net_connect.send_command('show running-config', read_timeout=120)

    filename = f"backup_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w') as f:
        f.write(output)

    print(f"\nSUCCESS! Config saved to: {filename}")

except NetmikoAuthenticationException:
    print("\nAuthentication failed!")
    print("Check 'serial_debug.log' to see if the switch is asking for Username/Password or sitting at a MOTD/prompt.")
except NetmikoTimeoutException:
    print("\nConnection timed out. Ensure PuTTY / TeraTerm / etc... are completely closed.")
except Exception as e:
    print(f"\nAn error occurred: {e}")
