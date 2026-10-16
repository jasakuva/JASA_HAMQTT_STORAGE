import logging
from pathlib import Path
from .config import settings
from .integrations.ha_worker import run as run_ha
from .integrations.mqtt_worker import run as run_mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

def main():
    import sys
    if len(sys.argv) < 2 or sys.argv[1] not in {"ha", "mqtt", "mcp", "cleanup", "backup", "reset-auth"}:
        raise SystemExit("Usage: python -m hamqtt_store.cli [ha|mqtt|mcp|cleanup|backup [full|diff|dump]|reset-auth]")
    if sys.argv[1] == "reset-auth":
        marker = Path(settings.app_data_dir) / ".reset-auth"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        print(f"Authentication reset marker created: {marker}")
        return
    if sys.argv[1] == "mcp":
        from .mcp_server import main as run_mcp
        run_mcp()
    elif sys.argv[1] == "cleanup":
        from .services.cleanup import run_scheduler
        run_scheduler()
    elif sys.argv[1] == "backup":
        from .services.backup import run_backup, run_scheduler
        if len(sys.argv) == 3:
            if sys.argv[2] not in {"full", "diff", "dump"}:
                raise SystemExit("Backup type must be full, diff, or dump")
            run_backup(sys.argv[2])
        else:
            run_scheduler()
    else:
        (run_ha if sys.argv[1] == "ha" else run_mqtt)()

if __name__ == "__main__": main()
