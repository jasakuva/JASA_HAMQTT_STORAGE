# Release 0.3.5-rc2

Release date: 2026-11-11

HA MQTT Store `0.3.5-rc2` is a prerelease from the `feature-autoupdate`
branch. It is intended to test the GitHub release updater and prerelease
selection in the web UI. It is not a stable release.

## Highlights

- The Updates page has an **Include published prereleases** checkbox.
- The Updates page lists every eligible trusted release and offers a separate
  update action for each newer version.
- Checking or clearing the checkbox saves immediately through the existing
  CSRF-protected settings route.
- The preference is stored in `system_settings`.
- Stable releases remain the default; published beta and RC releases are
  included only when explicitly enabled.
- The publishing workflow creates the immutable `0.3.5-rc2` image tag and does
  not move `latest` for this prerelease.

## Testing the prerelease

Use the GitHub prerelease page to review the release notes, then install the
immutable image tag only in a test environment. Do not use `latest` as a way to
select prereleases.

The complete updater behavior and safe deployment rules are documented in
[`docs/UPDATER.md`](UPDATER.md).

## Validation

- 70 Python tests passed.
- Python compilation passed.
- Documentation validation passed.
- Root Compose configuration rendered successfully.
- `git diff --check` passed.