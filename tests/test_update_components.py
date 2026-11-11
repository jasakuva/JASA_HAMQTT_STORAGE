import io
import json
from types import SimpleNamespace

from hamqtt_store.services.update_engine import engine_from_name
from hamqtt_store.services.update_provider import GitHubReleaseProvider, Release, normalize_tag
from hamqtt_store.services.versioning import compare_versions, is_upgrade, parse_version
from hamqtt_store import updater_server


def test_normalize_tag_accepts_release_tags_and_rejects_paths():
    assert normalize_tag("v0.3.5") == "0.3.5"
    assert normalize_tag("0.3.5-rc1") == "0.3.5-rc1"
    assert normalize_tag("bad/version") is None


def test_version_comparison_rejects_unknown_versions_and_orders_prereleases():
    assert parse_version("v0.3.4").value == "0.3.4"
    assert compare_versions("0.3.4-rc1", "0.3.4") == -1
    assert compare_versions("0.3.5-beta2", "0.3.5-beta10") == -1
    assert is_upgrade("0.3.4", "0.3.5")
    assert not is_upgrade("dev", "0.3.5")
    assert compare_versions("dev", "0.3.5") is None


def test_github_provider_excludes_prereleases_by_default(monkeypatch):
    releases = [
        {"tag_name": "v0.3.5-beta2", "prerelease": True, "draft": False, "html_url": "beta2"},
        {"tag_name": "v0.3.5-beta10", "prerelease": True, "draft": False, "html_url": "beta10"},
        {"tag_name": "v0.3.5-beta1", "prerelease": True, "draft": False, "html_url": "beta"},
        {"tag_name": "v0.3.4", "prerelease": False, "draft": False, "html_url": "stable"},
    ]

    class Response(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(
        "hamqtt_store.services.update_provider.urlopen",
        lambda request, timeout: Response(json.dumps(releases)),
    )
    release = GitHubReleaseProvider("owner/repo").latest()
    assert release.version == "0.3.4"
    assert release.is_prerelease is False


def test_github_provider_can_select_published_beta_release(monkeypatch):
    releases = [
        {"tag_name": "v0.3.5-beta2", "prerelease": True, "draft": False, "html_url": "beta2"},
        {"tag_name": "v0.3.5-beta10", "prerelease": True, "draft": False, "html_url": "beta10"},
        {"tag_name": "v0.3.5-beta1", "prerelease": True, "draft": False, "html_url": "beta"},
        {"tag_name": "v0.3.4", "prerelease": False, "draft": False, "html_url": "stable"},
    ]

    class Response(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(
        "hamqtt_store.services.update_provider.urlopen",
        lambda request, timeout: Response(json.dumps(releases)),
    )
    release = GitHubReleaseProvider("owner/repo", include_prereleases=True).latest()
    assert release.version == "0.3.5-beta10"
    assert release.is_prerelease is True


def test_github_provider_lists_all_eligible_releases_in_version_order(monkeypatch):
    releases = [
        {"tag_name": "v0.3.5-rc1", "prerelease": True, "draft": False, "html_url": "rc1"},
        {"tag_name": "v0.3.4", "prerelease": False, "draft": False, "html_url": "stable"},
        {"tag_name": "v0.3.5-beta2", "prerelease": True, "draft": False, "html_url": "beta2"},
        {"tag_name": "v0.3.3", "prerelease": False, "draft": False, "html_url": "old"},
    ]

    class Response(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(
        "hamqtt_store.services.update_provider.urlopen",
        lambda request, timeout: Response(json.dumps(releases)),
    )
    listed = GitHubReleaseProvider("owner/repo", include_prereleases=True).releases()
    assert [release.version for release in listed] == ["0.3.5-rc1", "0.3.5-beta2", "0.3.4", "0.3.3"]


def test_engine_command_builders_are_engine_specific_but_workflow_neutral():
    podman = engine_from_name("podman")
    docker = engine_from_name("docker")
    assert podman.pull_command()[:2] == ["podman-compose", "-p"]
    assert docker.pull_command()[:3] == ["docker", "compose", "-p"]
    assert "down" not in podman.start_application_command()
    assert "-v" not in docker.start_application_command()


def test_updater_health_is_public_but_api_requires_token(monkeypatch):
    monkeypatch.setattr(
        updater_server.GitHubReleaseProvider,
        "latest",
        lambda self: Release(
            version="0.3.5",
            tag="v0.3.5",
            release_url="https://github.com/jasakuva/JASA_HAMQTT_STORAGE/releases/tag/v0.3.5",
            release_notes_url="https://github.com/jasakuva/JASA_HAMQTT_STORAGE/releases/tag/v0.3.5",
            published_at=None,
            is_prerelease=False,
        ),
    )
    monkeypatch.setattr(
        updater_server,
        "settings",
        SimpleNamespace(
            updater_token="secret",
            hamqtt_engine="podman",
            update_repository="jasakuva/JASA_HAMQTT_STORAGE",
            update_include_prereleases=False,
            hamqtt_version="0.3.4",
        ),
    )
    app = updater_server.create_updater_app()
    client = app.test_client()
    assert client.get("/health").status_code == 200
    assert client.get("/v1/status").status_code == 401
    response = client.get("/v1/status", headers={"X-HAMQTT-Updater-Token": "secret"})
    assert response.status_code == 200
    assert response.json["current_version"] == "0.3.4"
    assert response.json["latest_version"] == "0.3.5"
    assert response.json["update_available"] is True


def test_updater_release_list_endpoint_returns_all_releases(monkeypatch):
    listed = [
        Release("0.3.5-rc1", "v0.3.5-rc1", "rc", "rc", None, True),
        Release("0.3.4", "v0.3.4", "stable", "stable", None, False),
    ]
    monkeypatch.setattr(
        updater_server.GitHubReleaseProvider,
        "releases",
        lambda self: listed,
    )
    monkeypatch.setattr(
        updater_server,
        "settings",
        SimpleNamespace(
            updater_token="secret",
            hamqtt_engine="podman",
            update_repository="jasakuva/JASA_HAMQTT_STORAGE",
            update_include_prereleases=True,
            hamqtt_version="0.3.3",
        ),
    )
    client = updater_server.create_updater_app().test_client()
    response = client.get("/v1/releases", headers={"X-HAMQTT-Updater-Token": "secret"})
    assert response.status_code == 200
    assert [release["version"] for release in response.json["releases"]] == ["0.3.5-rc1", "0.3.4"]