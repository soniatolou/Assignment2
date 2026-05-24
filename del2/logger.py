import os
import json
from datetime import datetime

LOG_DIR = "logs"

def setup_logger():
    # skapar log-mappen om den inte finns
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(LOG_DIR, f"session_{timestamp}.json")
    return log_file


def log_event(log_file, event_type, data):
    # läser in befintliga loggar om filen redan finns
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            logs = json.load(f)
    else:
        logs = []

    # lägger till ny händelse med tidsstämpel
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        "data": data
    })

    # sparar tillbaka till filen
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2, ensure_ascii=True)