"""Small HTTP client used by the web container to call the updater service."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import settings


class UpdaterUnavailable(RuntimeError):
    pass


def _request(path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if settings.updater_token:
        headers["X-HAMQTT-Updater-Token"] = settings.updater_token
    request = Request(f"{settings.updater_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise UpdaterUnavailable("Updater service is unavailable") from exc
    if not isinstance(result, dict):
        raise UpdaterUnavailable("Updater returned an invalid response")
    return result


def get_status() -> dict:
    return _request("/v1/status")


def get_latest_release() -> dict:
    return _request("/v1/releases/latest")


def create_job(target_version: str, *, operation: str = "update") -> dict:
    return _request("/v1/jobs", method="POST", payload={"operation": operation, "target_version": target_version})


def get_job(job_id: int) -> dict:
    return _request(f"/v1/jobs/{job_id}")


def rollback_job(job_id: int) -> dict:
    return _request(f"/v1/jobs/{job_id}/rollback", method="POST", payload={})