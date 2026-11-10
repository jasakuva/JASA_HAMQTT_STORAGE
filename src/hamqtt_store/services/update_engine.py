"""Engine-neutral command construction for updater operations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    name: str
    compose_command: str
    project_name: str = "hamqtt-store"
    compose_file: str = "compose.github.yml"


class ContainerEngine:
    def __init__(self, config: EngineConfig):
        if config.name not in {"docker", "podman"}:
            raise ValueError(f"Unsupported container engine: {config.name}")
        self.config = config

    def compose(self, *arguments: str) -> list[str]:
        return [
            *self.config.compose_command.split(),
            "-p",
            self.config.project_name,
            "-f",
            self.config.compose_file,
            *arguments,
        ]

    def validate_command(self) -> list[str]:
        return self.compose("config", "--quiet")

    def pull_command(self) -> list[str]:
        return self.compose("pull")

    def migration_command(self) -> list[str]:
        return self.compose("run", "--rm", "--no-deps", "migrate")

    def start_application_command(self) -> list[str]:
        return self.compose("up", "-d", "--no-deps", "web", "mqtt-ingestor", "ha-ingestor", "cleanup", "mcp", "backup", "recovery")

    def rollback_command(self) -> list[str]:
        return self.compose("up", "-d", "--no-deps", "web", "mqtt-ingestor", "ha-ingestor", "cleanup", "mcp", "backup", "recovery")


def engine_from_name(name: str, *, compose_file: str = "compose.github.yml") -> ContainerEngine:
    normalized = name.strip().lower()
    command = "podman-compose" if normalized == "podman" else "docker compose"
    return ContainerEngine(EngineConfig(normalized, command, compose_file=compose_file))