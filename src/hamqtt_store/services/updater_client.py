"""Small HTTP client used by the web container to call the updater service."""

import json
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import settings


class UpdaterUnavailable(RuntimeError):
    pass


def _request(path: str, *, method: str = "GET", payload: dict | None = None, query: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if settings.updater_token:
        headers["X-HAMQTT-Updater-Token"] = settings.updater_token
    url = f"{settings.updater_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise UpdaterUnavailable("Updater service is unavailable") from exc
    if not isinstance(result, dict):
        raise UpdaterUnavailable("Updater returned an invalid response")
    return result


def get_status(*, include_prereleases: bool = False) -> dict:
    return _request("/v1/status", query={"include_prereleases": str(include_prereleases).lower()})


def get_latest_release(*, include_prereleases: bool = False) -> dict:
    return _request(
        "/v1/releases/latest",
        query={"include_prereleases": str(include_prereleases).lower()},
    )


def get_releases(*, include_prereleases: bool = False) -> list[dict]:
    result = _request(
        "/v1/releases",
        query={"include_prereleases": str(include_prereleases).lower()},
    )
    releases = result.get("releases")
    if not isinstance(releases, list):
        raise UpdaterUnavailable("Updater returned an invalid release list")
    return releases


def create_job(target_version: str, *, operation: str = "update", include_prereleases: bool = False) -> dict:
    return _request(
        "/v1/jobs",
        method="POST",
        payload={
            "operation": operation,
            "target_version": target_version,
            "include_prereleases": include_prereleases,
        },
    )


def get_job(job_id: int) -> dict:
    return _request(f"/v1/jobs/{job_id}")


def rollback_job(job_id: int) -> dict:
    return _request(f"/v1/jobs/{job_id}/rollback", method="POST", payload={})