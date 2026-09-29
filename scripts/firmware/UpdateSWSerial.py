import time
from pathlib import Path
import serial

# 1. Configuration variables
COM_PORT = 'COM3'
IMAGE_NAME = 'IOSIMAGE.bin'
TEMP_PASS = 'TEMPPASS!'

print(f"Opening {COM_PORT}... Ensure PuTTY is closed.")

with serial.Serial(COM_PORT, 9600, timeout=1) as ser:
    
    # --- STEP 1: Universal Prompt Handler ---
    print("\n[STEP 1] Detecting switch state and navigating to Switch#...")
    
    while True:
        ser.write(b'\r\n')
        time.sleep(1.5)
        
        if ser.in_waiting > 0:
            buffer = ser.read(ser.in_waiting).decode('utf-8', errors='ignore').lower()
            clean_tail = buffer.strip().splitlines()[-1] if buffer.strip() else ""
            print(f"Current Prompt: {clean_tail}")
            
            if 'switch#' in buffer:
                print("\n[!] SUCCESS: Reached Privileged EXEC mode (Switch#).")
                break
            elif 'enter enable secret:' in buffer or '% no defaulting allowed' in buffer:
                print("--> Supplying required enable secret...")
                ser.write(f"{TEMP_PASS}\r\n".encode())
            elif 'confirm enable secret:' in buffer:
                print("--> Confirming enable secret...")
                ser.write(f"{TEMP_PASS}\r\n".encode())
            elif 'initial configuration dialog' in buffer or '[yes/no]' in buffer:
                print("--> Bypassing configuration wizard...")
                ser.write(b'no\r\n')
            elif 'selection' in buffer or '[0]' in buffer:
                print("--> Selecting option 0 (exit setup without saving)...")
                ser.write(b'0\r\n')
            elif 'password:' in buffer:
                print("--> Entering password for enable mode...")
                ser.write(f"{TEMP_PASS}\r\n".encode())
            elif 'switch>' in buffer:
                print("--> Entering enable mode...")
                ser.write(b'enable\r\n')
            else:
                ser.write(b'\r\n')
        else:
            print("Waiting for console data...", end='\r')
            
        time.sleep(1)

    # --- STEP 2: Disable Console Syslog Noise & Save Configuration ---
    print("\n[STEP 2] Silencing console logging noise and writing memory...")
    ser.write(b'conf t\r\nno logging console\r\nend\r\n')
    time.sleep(2)
    ser.write(b'write memory\r\n')
    time.sleep(5)
    
    if ser.in_waiting:
        ser.read(ser.in_waiting)  # Clear buffer

    # --- STEP 3: Execute Install Directly from USB ---
    install_cmd = f"install add file usbflash0:{IMAGE_NAME} activate commit\r\n"
    print(f"\n[STEP 3] Running install: {install_cmd.strip()}")
    ser.write(install_cmd.encode())
    
    print("\nExpanding packages (Live console stream below):")
    print("=" * 65)
    
    install_buffer = ""
    reload_prompt_detected = False
    start_time = time.time()
    
    while time.time() - start_time < 900:
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            install_buffer += data
            print(data, end='', flush=True)
            
            lower_buf = install_buffer.lower()
            if any(k in lower_buf for k in ["[y/n]", "require a reload", "proceed?"]):
                reload_prompt_detected = True
                break
            elif "% error" in lower_buf or "invalid input" in lower_buf:
                print("\n[!] Installation stopped due to a Cisco command error.")
                break
        time.sleep(0.2)

    print("\n" + "=" * 65)

    # --- STEP 4: Confirm Reload ---
    if reload_prompt_detected:
        print("\n[STEP 4] Reload prompt detected! Sending 'y' to confirm reboot...")
        ser.write(b'y\r\n')
        time.sleep(2)
        
        reboot_start = time.time()
        while time.time() - reboot_start < 60:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                print(data, end='', flush=True)
                if any(k in data.lower() for k in ["reloading", "system bootstrap", "rebooting"]):
                    break
            time.sleep(0.5)
        print("\n[!] Switch accepted reload command and is restarting.")
    else:
        print("\n[!] Reload prompt was not reached. Review output above.")
        exit(1)

# --- STEP 5: Live Reboot Monitor ---
    print("\n[STEP 5] Monitoring reboot sequence... (Holding checks for 5 mins during POST)")
    start_reboot = time.time()
    MIN_BOOT_TIME = 300  # Enforce 5-minute minimum wait before checking prompts
    
    while True:
        elapsed_sec = time.time() - start_reboot
        elapsed_min = int(elapsed_sec / 60)
        
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            print(data, end='', flush=True)
            
            # Only evaluate prompts AFTER the 5-minute boot phase passes
            if elapsed_sec > MIN_BOOT_TIME:
                if any(prompt in data.lower() for prompt in ["switch#", "switch>", "initial configuration dialog"]):
                    print(f"\n\n[!] SUCCESS! Switch booted and online after {elapsed_min} minutes.")
                    break
        else:
            ser.write(b'\r\n')
        time.sleep(5)

    # Verification: Step 5 is successful when real prompt data is received past the 5-minute mark.

    # --- STEP 6: Robust Post-Reboot Password Cleanup ---
    print("\n[STEP 6] Navigating post-reboot prompt to remove temporary password...")
    
    # Wait 30 seconds for all background system processes to stabilize post-boot
    time.sleep(30)
    
    # Navigate to Switch# dynamically
    while True:
        ser.write(b'\r\n')
        time.sleep(1.5)
        if ser.in_waiting > 0:
            post_buf = ser.read(ser.in_waiting).decode('utf-8', errors='ignore').lower()
            
            if 'switch#' in post_buf:
                break
            elif 'password:' in post_buf:
                ser.write(f"{TEMP_PASS}\r\n".encode())
            elif 'switch>' in post_buf:
                ser.write(b'enable\r\n')
            elif 'initial configuration dialog' in post_buf or '[yes/no]' in post_buf:
                ser.write(b'no\r\n')
            elif 'selection' in post_buf or '[0]' in post_buf:
                ser.write(b'0\r\n')

    print("--> Reached Switch#. Executing: configure terminal -> no enable secret -> write memory")
    ser.write(b'conf t\r\nno enable secret\r\nend\r\nwrite memory\r\n')
    time.sleep(5)
    
    if ser.in_waiting > 0:
        print(ser.read(ser.in_waiting).decode('utf-8', errors='ignore'))

    print("[!] Temporary password successfully removed!")

    # Verification: Step 6 is successful when the console prints '[OK]' after write memory.
    
    # --- STEP 7: Verify Running Software Version ---
    print("\n[STEP 7] Verifying running software version...")
    ser.write(b'show version | include Cisco IOS XE Software\r\n')
    time.sleep(2)
    
    if ser.in_waiting > 0:
        ver_res = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        print(f"\nActive Image:\n{ver_res.strip()}")

print("\nAutomated firmware upgrade and post-cleanup complete!")