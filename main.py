import os
from datetime import datetime, timedelta

LOG_FILE_PATH = "bot_activity.log"
MAX_LOG_LINES = 3000  # Automatically trims anything past 3000 lines to save Termux storage

def setup_file_logger():
    """Ensures a log file exists for capturing activity."""
    if not os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, "w") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bot log initialized.\n")

def log_event(message: str):
    """Appends an event with a timestamp and trims old entries to prevent storage bloat."""
    setup_file_logger()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_line = f"[{timestamp}] {message}\n"
    
    try:
        with open(LOG_FILE_PATH, "r") as f:
            lines = f.readlines()
            
        lines.append(new_line)
        
        # If lines exceed the safe limit, keep only the latest MAX_LOG_LINES
        if len(lines) > MAX_LOG_LINES:
            lines = lines[-MAX_LOG_LINES:]
            
        with open(LOG_FILE_PATH, "w") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"Logging error: {e}")

def get_logs_by_count(n: int = 10):
    """Retrieves the last N logs."""
    setup_file_logger()
    try:
        with open(LOG_FILE_PATH, "r") as f:
            lines = f.readlines()
        selected = lines[-n:] if len(lines) >= n else lines
        return "".join(selected)
    except Exception as e:
        return f"Error reading logs: {e}"

def get_logs_by_time(minutes: int = 10):
    """Retrieves logs from the last N minutes."""
    setup_file_logger()
    cutoff_time = datetime.now() - timedelta(minutes=minutes)
    filtered_lines = []
    
    try:
        with open(LOG_FILE_PATH, "r") as f:
            for line in f:
                if line.startswith("[") and "]" in line:
                    try:
                        timestamp_str = line[1:19]
                        log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        if log_time >= cutoff_time:
                            filtered_lines.append(line)
                    except ValueError:
                        filtered_lines.append(line)
        if not filtered_lines:
            return f"No logs found within the last {minutes} minutes."
        return "".join(filtered_lines)
    except Exception as e:
        return f"Error reading time-based logs: {e}"
