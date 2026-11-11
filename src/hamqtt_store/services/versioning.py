"""Application version parsing and update eligibility checks."""

import re
from dataclasses import dataclass


VERSION_PATTERN = re.compile(r"^v?(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")


@dataclass(frozen=True)
class ParsedVersion:
    value: str
    numbers: tuple[int, int, int]
    suffix: str


def parse_version(value: str | None) -> ParsedVersion | None:
    if not value:
        return None
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    normalized = match.group("version")
    main, _, suffix = normalized.partition("-")
    numbers = tuple(int(part) for part in main.split("."))
    return ParsedVersion(normalized, numbers, suffix)


def compare_versions(left: str | None, right: str | None) -> int | None:
    """Return -1, 0, or 1; return None when either version is not release-like."""
    parsed_left = parse_version(left)
    parsed_right = parse_version(right)
    if not parsed_left or not parsed_right:
        return None
    left_key = (parsed_left.numbers, parsed_left.suffix == "", prerelease_key(parsed_left.suffix))
    right_key = (parsed_right.numbers, parsed_right.suffix == "", prerelease_key(parsed_right.suffix))
    return (left_key > right_key) - (left_key < right_key)


def is_upgrade(current: str | None, target: str | None) -> bool:
    return compare_versions(current, target) == -1


def prerelease_key(suffix: str) -> tuple:
    if not suffix:
        return ()
    parts = []
    for part in re.findall(r"[A-Za-z]+|\d+", suffix):
        parts.append((1, int(part)) if part.isdigit() else (0, part))
    return tuple(parts)