"""Trusted release discovery for the updater service."""

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .versioning import compare_versions, parse_version, prerelease_key

VERSION_TAG = re.compile(r"^v?(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    release_url: str
    release_notes_url: str
    published_at: str | None
    is_prerelease: bool


def normalize_tag(tag: str) -> str | None:
    match = VERSION_TAG.fullmatch(tag.strip())
    return match.group("version") if match else None


class GitHubReleaseProvider:
    def __init__(self, repository: str, *, include_prereleases: bool = False, timeout: float = 5.0):
        self.repository = repository
        self.include_prereleases = include_prereleases
        self.timeout = timeout

    def latest(self) -> Release:
        request = Request(
            f"https://api.github.com/repos/{self.repository}/releases?per_page=20",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "hamqtt-store-updater"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                releases = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("release provider unavailable") from exc
        candidates = []
        for item in releases:
            if item.get("draft") or (item.get("prerelease") and not self.include_prereleases):
                continue
            version = normalize_tag(item.get("tag_name", ""))
            if version:
                candidates.append((version, item))
        if not candidates:
            release_kind = "stable or prerelease" if self.include_prereleases else "stable"
            raise RuntimeError(f"no valid {release_kind} release found")
        version, item = sorted(candidates, key=lambda value: _version_key(value[0]), reverse=True)[0]
        url = item.get("html_url", "")
        return Release(version, item["tag_name"], url, url, item.get("published_at"), bool(item.get("prerelease")))


def _version_key(version: str) -> tuple:
    parsed = parse_version(version)
    if not parsed:
        return (), False, ()
    return parsed.numbers, parsed.suffix == "", prerelease_key(parsed.suffix)


def is_newer_version(current: str | None, target: str | None) -> bool:
    """Return whether target is a strictly newer valid release than current."""
    return compare_versions(current, target) == -1