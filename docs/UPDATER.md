# GitHub release updater

The Updates page uses GitHub Releases as the source of available HA MQTT Store
versions. Stable releases and prereleases are both supported, but prereleases
are opt-in.

## Selecting prerelease updates

1. Sign in to the web UI and open **Settings → Updates**.
2. Enable **Include published prereleases** to include published beta and release
   candidate releases in the list.
3. Disable it to show stable releases only.

The checkbox submits immediately when it changes. The preference is stored in
the `system_settings` table through `POST /settings/updates`; no separate Save
button is required. The form remains protected by the application's session and
CSRF checks.

Only GitHub releases marked as published are eligible. A prerelease is not
copied to the `latest` container tag: the publishing workflow updates `latest`
only for a non-prerelease GitHub release. Production installations should use
an immutable version tag when a specific release must be pinned.

## Version sources

- Local development keeps the application version at `0.3.3` until the next
  release is intentionally prepared.
- Published container versions are selected with `HAMQTT_VERSION` in Compose
  deployment files.
- The default `latest` image is the newest stable image. It must not be used as
  a prerelease selector.
- The GitHub provider compares normalized semantic versions and keeps release
  tags separate from arbitrary Git references.

## Safe deployment behavior

Updates run through the existing migration-before-application-start workflow.
PostgreSQL and application-data volumes must be preserved. Do not use
`podman-compose down -v`, `docker compose down -v`, or remove
`hamqtt-postgres-data` / `hamqtt-app-data` during a normal update.

The canonical project workflow is Podman with `podman-compose`; Docker Compose
is supported by the published Linux deployment documentation where explicitly
described. The updater must not switch engines during one operation.

## Validation

After changing updater behavior, run:

```powershell
python -m pytest -q
python -m compileall -q src
python tools/validate_docs.py
podman-compose config
git diff --check
```

The current test suite covers stable-only selection, opt-in published beta
selection, semantic version ordering, API authentication, and engine-specific
command construction.