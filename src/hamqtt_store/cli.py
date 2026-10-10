import logging
from .integrations.ha_worker import run as run_ha
from .integrations.mqtt_worker import run as run_mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

def main():
    import sys
    if len(sys.argv) != 2 or sys.argv[1] not in {"ha", "mqtt", "mcp"}:
        raise SystemExit("Usage: python -m hamqtt_store.cli [ha|mqtt|mcp]")
    if sys.argv[1] == "mcp":
        from .mcp_server import main as run_mcp
        run_mcp()
    else:
        (run_ha if sys.argv[1] == "ha" else run_mqtt)()

if __name__ == "__main__": main()
