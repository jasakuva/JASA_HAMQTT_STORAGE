from types import SimpleNamespace

from hamqtt_store.services.update_engine import engine_from_name
from hamqtt_store.services.update_provider import normalize_tag
from hamqtt_store import updater_server


def test_normalize_tag_accepts_release_tags_and_rejects_paths():
    assert normalize_tag("v0.3.5") == "0.3.5"
    assert normalize_tag("0.3.5-rc1") == "0.3.5-rc1"
    assert normalize_tag("bad/version") is None


def test_engine_command_builders_are_engine_specific_but_workflow_neutral():
    podman = engine_from_name("podman")
    docker = engine_from_name("docker")
    assert podman.pull_command()[:2] == ["podman-compose", "-p"]
    assert docker.pull_command()[:3] == ["docker", "compose", "-p"]
    assert "down" not in podman.start_application_command()
    assert "-v" not in docker.start_application_command()


def test_updater_health_is_public_but_api_requires_token(monkeypatch):
    monkeypatch.setattr(
        updater_server,
        "settings",
        SimpleNamespace(
            updater_token="secret",
            hamqtt_engine="podman",
            update_repository="jasakuva/JASA_HAMQTT_STORAGE",
            update_include_prereleases=False,
        ),
    )
    app = updater_server.create_updater_app()
    client = app.test_client()
    assert client.get("/health").status_code == 200
    assert client.get("/v1/status").status_code == 401
    assert client.get("/v1/status", headers={"X-HAMQTT-Updater-Token": "secret"}).status_code == 200