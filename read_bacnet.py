#gets all objects and values from remote devices using bacnet
# vibe coded for a ctf


import asyncio
import nest_asyncio
import BAC0
import time

# --- CONFIGURATION ---
TARGET_DEVICE_IP = '192.168.1.50'
MY_LOCAL_IP = '192.168.1.10'
# ---------------------

nest_asyncio.apply()
BAC0.log_level('silence')

def safe_read(bacnet, request_string):
    """
    Attempts to read a property. 
    If it fails (Property Not Implemented/Unknown), returns None.
    """
    try:
        return bacnet.read(request_string)
    except Exception:
        # We silently catch the error because we EXPECT many properties to be missing.
        return None

def robust_audit():
    print(f"--- Connecting to {TARGET_DEVICE_IP} ---")
    
    # Event Loop Fix
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        bacnet = BAC0.lite(ip=MY_LOCAL_IP)
        if hasattr(bacnet, 'this_application'):
            bacnet.this_application.apduTimeout = 10000 
    except Exception as e:
        print(f"Error binding: {e}")
        return

    # Discovery
    bacnet.whois(TARGET_DEVICE_IP)
    time.sleep(2)
    
    target_id = None
    if bacnet.discoveredDevices:
        for ip, dev_id in bacnet.discoveredDevices:
            if ip == TARGET_DEVICE_IP:
                target_id = dev_id
                break

    if target_id is None:
        print("Target not responding.")
        bacnet.disconnect()
        return

    print(f"--- Auditing Device {target_id} ---")
    
    try:
        # Get count
        count = safe_read(bacnet, f"{TARGET_DEVICE_IP} device {target_id} objectList 0")
        if not isinstance(count, int):
            print("Could not read object list size. Aborting.")
            return

        print(f"Scanning {count} objects...\n")

        for i in range(1, count + 1):
            # 1. Get ID (Crucial - if this fails, skip the object)
            oid = safe_read(bacnet, f"{TARGET_DEVICE_IP} device {target_id} objectList {i}")
            if not oid: continue
            
            obj_type, obj_inst = oid
            base_cmd = f"{TARGET_DEVICE_IP} {obj_type} {obj_inst}"

            # 2. READ PROPERTIES (The "Safe" Way)
            name = safe_read(bacnet, f"{base_cmd} objectName") or "Unknown"
            
            # Value handling
            val = safe_read(bacnet, f"{base_cmd} presentValue")
            if isinstance(val, float): val = round(val, 2)
            if val is None: val = "N/A"

            # Optional properties that often fail
            desc = safe_read(bacnet, f"{base_cmd} description")
            
            # Reliability (Is the sensor broken?)
            # Returns: 'noFaultDetected', 'openLoop', 'unreliableOther', etc.
            reliability = safe_read(bacnet, f"{base_cmd} reliability") 

            # Priority Array (Who is controlling this?)
            # Only exists on Output/Value objects
            priority = None
            if "output" in obj_type or "value" in obj_type:
                # This returns a list of 16 values (or Nulls)
                priority = safe_read(bacnet, f"{base_cmd} priorityArray")

            # Units (for Analogs)
            units = ""
            if "analog" in obj_type:
                 units = safe_read(bacnet, f"{base_cmd} units")

            # --- PRETTY PRINT ---
            print(f"[{i}] {name}")
            print(f"    ID:      {obj_type} {obj_inst}")
            print(f"    Value:   {val} {units if units else ''}")
            
            if desc:
                print(f"    Desc:    {desc}")
            
            if reliability and reliability != "noFaultDetected":
                 print(f"    STATUS:  {reliability} (⚠️)")

            if priority:
                # Find which priority slot is active (lowest number with a value)
                active_slot = "None"
                for idx, p_val in enumerate(priority):
                    if p_val is not None and p_val != 'null':
                        active_slot = f"Priority {idx+1} ({p_val})"
                        break
                print(f"    Control: {active_slot}")

            print("-" * 40)

    finally:
        bacnet.disconnect()
        print("Audit Complete.")

if __name__ == "__main__":
    robust_audit()
