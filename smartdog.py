import subprocess
import time
import signal
import sys
import os
import json
import threading
import queue

# --- Shared State ---
stop_monitoring = False
CLEANING_UP = False 
trigger_queue = queue.Queue() 

# --- Process Management Helper ---
def get_process_status(program_name):
    """Checks if a process is currently running by name."""
    try:
        cmd = f'tasklist /NH /FO CSV /FI "IMAGENAME eq {program_name}"'
        output = subprocess.check_output(cmd, shell=True, universal_newlines=True, stderr=subprocess.DEVNULL)
        return program_name.lower() in output.lower()
    except Exception:
        return False

# --- Global Cleanup Function ---
def cleanup_programs(config, reason):
    """
    Executes the 'action' sequence defined in the config immediately.
    """
    global stop_monitoring, CLEANING_UP
    if CLEANING_UP:
        return
    CLEANING_UP = True
    
    stop_monitoring = True 

    print("\n*** CLEANUP SEQUENCE ACTIVATED ***")
    print(f"Reason: {reason}")

    for action_item in config.get("action", []):
        action = action_item.get("action")
        action_type = action_item.get("type")
        name = action_item.get("name")
        
        if action == "close" and action_type == "program" and name:
            try:
                if get_process_status(name):
                    print(f"   -> Executing **close** action on program **{name}**...")
                    subprocess.run(['taskkill', '/IM', name, '/F'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    print(f"   -> Program **{name}** is already closed or was never found.")
            except Exception as e:
                print(f"   -> ERROR during termination of {name}: {e}")
        
    print("*** CLEANUP COMPLETE. Script exiting. ***")
    sys.exit(0)

# --- Signal Handler (for Ctrl+C) ---
def signal_handler(config):
    """Returns a handler function that closes over the config."""
    def handler(sig, frame):
        cleanup_programs(config, "Termination Signal (Ctrl+C) received")
    return handler

# ----------------------------------------------------------------------
# --- THREAD WORKER FUNCTIONS WITH INDIVIDUAL TIMEOUTS ---
# ----------------------------------------------------------------------

def program_watch_worker(name, timeout):
    """Thread function to watch for a single program to start with a timeout."""
    start_time = time.time()
    print(f"[Thread-{name}] Monitoring program {name} (Timeout: {timeout}s)...")
    
    while not stop_monitoring:
        if time.time() - start_time > timeout:
            trigger_queue.put(("timeout_failure", name, f"Program '{name}' timed out after {timeout}s."))
            break

        if get_process_status(name):
            trigger_queue.put(("program_ready", name))
            break
        
        time.sleep(1)

def log_watch_worker(log_path, pattern, timeout, encoding):
    """Thread function to watch a log file for a specific pattern with a timeout and specified encoding."""
    start_time = time.time()
    log_name = os.path.basename(log_path)
    print(f"[Thread-{log_name}] Monitoring log file {log_name} (Encoding: {encoding}, Timeout: {timeout}s)...")

    try:
        # Pass the encoding argument to open()
        f = open(log_path, 'r', encoding=encoding)
        f.seek(0, os.SEEK_END)
    except Exception as e:
        trigger_queue.put(("timeout_failure", log_path, f"Log file error ({e.__class__.__name__}): Could not open/read log file with encoding '{encoding}'."))
        return 

    while not stop_monitoring:
        if time.time() - start_time > timeout:
            trigger_queue.put(("timeout_failure", log_path, f"Log pattern in '{log_name}' timed out after {timeout}s."))
            f.close()
            break
            
        try:
            new_line = f.readline()
        except UnicodeDecodeError as e:
            trigger_queue.put(("timeout_failure", log_path, f"Log file error (UnicodeDecodeError): Line read failed. Check if the specified encoding '{encoding}' is correct."))
            f.close()
            return
            
        if new_line:
            if pattern in new_line:
                print(f"[Thread-{log_name}] LOG TRIGGER FOUND!")
                trigger_queue.put(("log_pattern_found", log_path))
                f.close()
                break
        else:
            time.sleep(0.5)

# --- MAIN SCRIPT LOGIC ---
def main():
    if len(sys.argv) < 2:
        print("Usage: python generalized_monitor.py <config_file.json>")
        sys.exit(1)

    config_file = sys.argv[1]
    
    try:
        # --- MODIFIED CODE BLOCK ---
        # Explicitly specify 'utf-8' encoding when opening the configuration file.
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # --- END MODIFIED CODE BLOCK ---
        
    except FileNotFoundError:
        print(f"FATAL ERROR: Config file '{config_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"FATAL ERROR: Config file '{config_file}' is not valid JSON. Details: {e}")
        sys.exit(1)
    except Exception as e:
        # Catch any remaining file/encoding errors
        print(f"FATAL ERROR: Could not load or parse config file '{config_file}': {e}")
        sys.exit(1)

    # Register the signal handler...
    signal.signal(signal.SIGINT, signal_handler(config))
    print("Ctrl+C handler is active.")

    # --- 1. Initial Run ---
    initial_run_path = config.get("initial_run")
    if initial_run_path:
        print(f"1. Launching initial program: {initial_run_path}...")
        try:
            subprocess.Popen([initial_run_path]) 
            time.sleep(1) 
        except FileNotFoundError:
            print(f"ERROR: Executable not found at {initial_run_path}")
            sys.exit(1)

    # --- 2. Start Watcher Threads ---
    watch_items = config.get("watch", [])
    threads = []
    required_conditions = {} 
    
    # Launch threads for each watch item
    for i, item in enumerate(watch_items):
        name = item.get("name")
        item_id = name
        
        timeout = item.get("timeout_seconds")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            print(f"FATAL ERROR: Watch item {i+1} ('{name}') must contain a valid positive 'timeout_seconds' field.")
            cleanup_programs(config, "Configuration Validation Failed")
            
        required_conditions[item_id] = False 
        
        if item.get("type") == "program":
            t = threading.Thread(target=program_watch_worker, args=(name, timeout))
        elif item.get("type") == "log":
            pattern = item.get("pattern")
            encoding = item.get("encoding", "utf-8") # <<< DEFAULT TO UTF-8 IF NOT SPECIFIED
            if not pattern:
                 print(f"FATAL ERROR: Log watch item '{name}' is missing a 'pattern' field.")
                 cleanup_programs(config, "Configuration Validation Failed")
            
            # Pass encoding to the worker thread
            t = threading.Thread(target=log_watch_worker, args=(name, pattern, timeout, encoding))
        else:
            print(f"WARNING: Skipping unrecognized watch type in config: {item}")
            continue
            
        t.daemon = True 
        t.start()
        threads.append(t)
        
    print(f"\n2. Started {len(threads)} monitoring threads. Waiting for conditions...")
    
    # --- 3. Main Loop: Wait for Trigger or Failure ---
    while not stop_monitoring:
        try:
            trigger_type, item_id, *extra_args = trigger_queue.get(timeout=None) 
            
            if trigger_type == "program_ready" or trigger_type == "log_pattern_found":
                required_conditions[item_id] = True
                print(f"   [Main] Condition met: {item_id}")
            
            elif trigger_type == "timeout_failure":
                reason = extra_args[0] if extra_args else "Unknown timeout"
                print(f"\nFATAL: Watch job failed: {reason}")
                cleanup_programs(config, f"Watch job timeout/failure: {reason}")
                break
            
            if all(required_conditions.values()):
                print("\n3. All monitoring conditions met. Triggering action sequence...")
                cleanup_programs(config, "All monitoring conditions met")
                break
                
        except Exception:
             pass 

if __name__ == "__main__":
    main()