# OpenAI Secure MCP Tunnel for HA MQTT Store

This guide explains how to connect the private, read-only HA MQTT Store MCP
service to ChatGPT with the OpenAI Secure MCP Tunnel. It also covers inspecting,
testing, reinstalling, upgrading, and troubleshooting the Linux
`tunnel-client.service` deployment.

The secure tunnel is different from ngrok:

- `tunnel-client` makes an outbound HTTPS connection to OpenAI.
- HA MQTT Store does not need a public hostname, public HTTPS certificate, or
  inbound Internet firewall rule.
- ChatGPT selects the OpenAI tunnel by its `tunnel_...` ID instead of connecting
  to the private HAMQTT URL directly.
- The local tunnel administration UI remains on loopback and is reached from a
  remote workstation with SSH port forwarding.

## Architecture

```text
ChatGPT
   |
   | OpenAI-hosted tunnel service
   v
tunnel-client.service on the private Linux host
   |
   | http://127.0.0.1:8001/mcp
   v
hamqtt-mcp container (read-only MCP tools)
```

The three important values are:

| Value | Purpose |
|---|---|
| `CONTROL_PLANE_TUNNEL_ID` | Identifies the tunnel selected by ChatGPT and used by the daemon. It starts with `tunnel_`. |
| `CONTROL_PLANE_API_KEY` | Runtime API key used by the long-lived daemon to poll and return responses. |
| `MCP_SERVER_URL` | Private MCP destination reachable from the tunnel host; normally `http://127.0.0.1:8001/mcp` when HAMQTT runs on the same host. |

An OpenAI admin key is only needed for tunnel create, update, list, or delete
operations through the CLI. Do not use an admin key as the daemon's runtime key.

## Security notes

- HAMQTT MCP access is read-only, but it can reveal stored Home Assistant and
  MQTT data. Grant tunnel access only to intended users and workspaces.
- Never commit runtime API keys, admin keys, `.env` files, or systemd secret
  files to this repository.
- Keep the tunnel health/UI listener on `127.0.0.1`. Do not bind it to a LAN or
  public interface merely to view the UI remotely.
- Do not paste unredacted service definitions, environment files, journal
  output, support bundles, or screenshots into public issues.
- The HAMQTT MCP endpoint is currently unauthenticated on the local network.
  Prefer `127.0.0.1:8001` for a same-host tunnel client and restrict port 8001
  with host firewall policy when remote LAN access is not required.

## Prerequisites

Before installing the tunnel client:

1. Start HA MQTT Store and confirm `hamqtt-mcp` is running.
2. Open **Settings → Data sources → AI / MCP service** in HAMQTT.
3. Enable **MCP read access**, save, and restart `hamqtt-mcp`.
4. In OpenAI Platform Tunnels management, create or select a tunnel and record
   its complete `tunnel_...` ID.
5. Create a runtime API key for the daemon. The daemon and the ChatGPT connector
   operator need the appropriate Tunnels **Read** and **Use** permissions.

Inspect the local HAMQTT services before changing anything:

```bash
cd /path/to/VS_HAMQTT_STORE
podman-compose ps -a
podman logs --tail 100 hamqtt-mcp
curl -fsS http://127.0.0.1:8000/health
```

Do not remove `hamqtt-postgres-data` or `hamqtt-app-data` while installing or
repairing the tunnel.

## Inspect an existing installation

The established deployment uses the systemd unit `tunnel-client.service`. These
commands do not modify it:

```bash
sudo systemctl status tunnel-client.service --no-pager
sudo systemctl cat tunnel-client.service
sudo systemctl show tunnel-client.service -p ExecStart -p EnvironmentFiles
sudo journalctl -u tunnel-client.service -n 100 --no-pager
```

Review output locally before sharing it. Redact API keys, bearer tokens, and
other credentials. If a secret was placed directly in `ExecStart` or an inline
`Environment=` entry, move it to the protected environment file described below.

Find the installed binary and version:

```bash
command -v tunnel-client
readlink -f "$(command -v tunnel-client)"
tunnel-client --version
tunnel-client help quickstart
```

The upstream default health address is `127.0.0.1:8080`. The HAMQTT deployment
described here deliberately uses `127.0.0.1:8081`; inspect the service and its
environment file if neither port responds.

## Clean installation or reinstall on Linux amd64

The example below uses the verified `v0.0.16` Linux amd64 release from October
15, 2026. Before a future reinstall, check the official release page and replace
`VERSION` with the version you intend to deploy. Use the matching architecture
archive for ARM64 hosts.

Install the required utilities:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl unzip
```

Download and verify the release:

```bash
VERSION=v0.0.16
ARCH=linux-amd64
WORKDIR="$(mktemp -d)"
cd "$WORKDIR"

curl -fLO "https://github.com/openai/tunnel-client/releases/download/${VERSION}/tunnel-client-${VERSION}-${ARCH}.zip"
curl -fLO "https://github.com/openai/tunnel-client/releases/download/${VERSION}/SHA256SUMS.txt"
grep "  tunnel-client-${VERSION}-${ARCH}.zip$" SHA256SUMS.txt | sha256sum -c -
unzip "tunnel-client-${VERSION}-${ARCH}.zip"
./tunnel-client --version
```

The full release archive includes `tunnel-client` and its pinned `cloudflared`
companion. Install both so the release remains complete even when the basic MCP
runtime does not need the companion:

```bash
sudo install -d -m 0755 /opt/tunnel-client
sudo install -m 0755 tunnel-client /opt/tunnel-client/tunnel-client
sudo install -m 0755 cloudflared /opt/tunnel-client/cloudflared
sudo ln -sfn /opt/tunnel-client/tunnel-client /usr/local/bin/tunnel-client
sudo ln -sfn /opt/tunnel-client/cloudflared /usr/local/bin/cloudflared
```

Create a locked-down service account and configuration directory:

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin tunnel-client 2>/dev/null || true
sudo install -d -o root -g tunnel-client -m 0750 /etc/tunnel-client
```

Create `/etc/tunnel-client/tunnel-client.env`:

```bash
sudoedit /etc/tunnel-client/tunnel-client.env
```

Use this content and replace the placeholders locally:

```dotenv
CONTROL_PLANE_TUNNEL_ID=tunnel_REPLACE_WITH_COMPLETE_ID
CONTROL_PLANE_API_KEY=REPLACE_WITH_RUNTIME_API_KEY
MCP_SERVER_URL=http://127.0.0.1:8001/mcp
HEALTH_LISTEN_ADDR=127.0.0.1:8081
```

Protect the file:

```bash
sudo chown root:tunnel-client /etc/tunnel-client/tunnel-client.env
sudo chmod 0640 /etc/tunnel-client/tunnel-client.env
```

Create `/etc/systemd/system/tunnel-client.service`:

```ini
[Unit]
Description=OpenAI Secure MCP Tunnel for HA MQTT Store
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=tunnel-client
Group=tunnel-client
WorkingDirectory=/opt/tunnel-client
EnvironmentFile=/etc/tunnel-client/tunnel-client.env
ExecStart=/opt/tunnel-client/tunnel-client run --log.level=info --log.format=json
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
```

Validate configuration before enabling the daemon. Load the same protected
environment as the service without printing it:

```bash
sudo -u tunnel-client bash -c 'set -a; source /etc/tunnel-client/tunnel-client.env; set +a; /opt/tunnel-client/tunnel-client doctor --explain'
```

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tunnel-client.service
sudo systemctl status tunnel-client.service --no-pager
```

Remove the temporary download directory after installation:

```bash
rm -rf "$WORKDIR"
```

## Upgrade the tunnel client

An upgrade replaces binaries, not the tunnel object or HAMQTT data. Preserve:

- `/etc/tunnel-client/tunnel-client.env`
- `/etc/systemd/system/tunnel-client.service`
- the existing `CONTROL_PLANE_TUNNEL_ID`

Inspect the service first, download and checksum the desired release as in the
installation section, then replace the binaries and restart:

```bash
sudo systemctl status tunnel-client.service --no-pager
sudo install -m 0755 tunnel-client /opt/tunnel-client/tunnel-client
sudo install -m 0755 cloudflared /opt/tunnel-client/cloudflared
sudo systemctl restart tunnel-client.service
tunnel-client --version
curl -i http://127.0.0.1:8081/readyz
```

If the new version fails, inspect the journal before changing configuration:

```bash
sudo journalctl -u tunnel-client.service -n 200 --no-pager
```

## Test HAMQTT locally

Check the container and web health first:

```bash
cd /path/to/VS_HAMQTT_STORE
podman-compose ps -a
curl -fsS http://127.0.0.1:8000/health
podman logs --tail 100 hamqtt-mcp
```

A browser or plain `GET` to the MCP URL can return HTTP 400 with a message such
as `Missing session ID`. Streamable HTTP MCP expects protocol requests and
session handling, so this response still proves that the HTTP route is
reachable. It is not by itself a tunnel failure.

```bash
curl -i http://127.0.0.1:8001/mcp
```

For a protocol-level check, send an MCP initialize request:

```bash
curl -i -X POST http://127.0.0.1:8001/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl-check","version":"1.0"}}}'
```

A JSON or event-stream initialize response, often with an `Mcp-Session-Id`
header, confirms that the local MCP server is answering protocol traffic.

## Test the tunnel client

Check liveness, readiness, detailed component state, and the UI:

```bash
curl -i http://127.0.0.1:8081/healthz
curl -i http://127.0.0.1:8081/readyz
curl -fsS 'http://127.0.0.1:8081/health?details=true'
curl -fsS http://127.0.0.1:8081/health/mcp
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8081/ui
```

Expected results:

- `/healthz` returns HTTP 200 when the process is alive.
- `/readyz` returns HTTP 200 only when startup readiness checks have passed;
  HTTP 503 means the process is running but not ready.
- `/health?details=true` and `/health/mcp` explain control-plane and MCP state.
- `/ui` returns the local administration interface.

Also verify service state and recent polling activity:

```bash
sudo systemctl is-enabled tunnel-client.service
sudo systemctl is-active tunnel-client.service
sudo journalctl -u tunnel-client.service --since '10 minutes ago' --no-pager
```

Do not declare the tunnel ready based only on an active process or `/healthz`.
Use `/readyz` and the UI Overview/Logs pages.

## Open the loopback-only UI from Windows

Because the UI listens on Linux loopback, `http://jasaserver01:8081` should not
work. From Windows PowerShell, keep this SSH session open:

```powershell
ssh -L 8081:127.0.0.1:8081 janne@jasaserver01
```

Then open:

```text
http://127.0.0.1:8081/ui
```

If Windows port 8081 is occupied, use a different local port:

```powershell
ssh -L 18081:127.0.0.1:8081 janne@jasaserver01
```

Open `http://127.0.0.1:18081/ui`. This changes only the Windows-side port; the
Linux service still listens on `127.0.0.1:8081`.

## Connect ChatGPT

Product labels can change, but the connection model is stable:

1. Confirm the daemon reports ready and the UI shows the expected complete
   `tunnel_...` ID and HAMQTT MCP destination.
2. Open ChatGPT **Settings → Connectors** or the available custom
   connector/app management page for the workspace.
3. Create or edit the MCP connector and choose **Tunnel** as the connection
   method.
4. Select the existing tunnel or enter its complete `tunnel_...` ID.
5. Save and allow ChatGPT to discover the read-only HAMQTT tools.
6. Enable the connector in a new chat if the interface requires it.

Do not enter `http://jasaserver01:8001/mcp`, `http://127.0.0.1:8001/mcp`, or
the local UI URL into ChatGPT. Those addresses are local to the private network.
ChatGPT connects through the selected OpenAI tunnel.

Test with a read-only request:

```text
Use HA MQTT Store to show the stored data summary.
```

Other useful tests:

```text
List the available Home Assistant entities.
```

```text
Show the newest MQTT topics and their current values.
```

## Routine management

```bash
# Status
sudo systemctl status tunnel-client.service --no-pager

# Recent logs
sudo journalctl -u tunnel-client.service -n 100 --no-pager

# Follow logs
sudo journalctl -u tunnel-client.service -f

# Restart after a configuration change
sudo systemctl restart tunnel-client.service

# Stop and start
sudo systemctl stop tunnel-client.service
sudo systemctl start tunnel-client.service

# Disable automatic startup
sudo systemctl disable --now tunnel-client.service
```

Stopping the daemon makes the private MCP server unavailable through the tunnel,
but it does not delete the remote tunnel object or HAMQTT data.

## Troubleshooting

### `control plane API key is required`

Confirm `CONTROL_PLANE_API_KEY` exists in the protected environment file and
that the service account can read the file. Use a runtime API key, not an admin
key.

### `tunnel ID is required` or invalid tunnel ID

Set the complete `CONTROL_PLANE_TUNNEL_ID`. Do not shorten the ID or remove a
namespace from a namespaced tunnel ID.

### `MCP server URL is required`

Set:

```dotenv
MCP_SERVER_URL=http://127.0.0.1:8001/mcp
```

If the tunnel client and HAMQTT run on different hosts, use a private address
that is reachable from the tunnel-client host and protect that network path.

### `/healthz` works but `/readyz` returns 503

The process is alive but a startup dependency is not ready. Inspect:

```bash
curl -fsS 'http://127.0.0.1:8081/health?details=true'
curl -fsS http://127.0.0.1:8081/health/mcp
sudo journalctl -u tunnel-client.service -n 200 --no-pager
```

Common causes are a wrong tunnel ID, a runtime key without Tunnels **Use**,
HAMQTT MCP being disabled, an incorrect MCP URL, or port 8001 being unreachable.

### Platform lists the tunnel but ChatGPT cannot select or use it

Verify all three separately:

1. The ChatGPT connector selected the same tunnel ID used by the daemon.
2. The tunnel is scoped to the intended workspace and the connector operator
   has Tunnels **Read** and **Use**.
3. The local daemon is still running and `/readyz` returns HTTP 200.

A remote tunnel object can continue to exist while its local runtime is stopped.

### The local UI cannot be opened from Windows

- Keep the SSH command running.
- Open the forwarded Windows address, not `jasaserver01:8081`.
- Confirm Linux responds locally with
  `curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8081/ui`.
- If the service uses upstream's default port 8080 instead, update both sides
  of the SSH forward accordingly.

### HAMQTT returns `Missing session ID`

This is expected for a plain browser `GET` to the Streamable HTTP MCP endpoint.
Use the initialize test, tunnel readiness checks, and an actual ChatGPT tool
call to test the complete path.

### The service repeatedly restarts

```bash
sudo systemctl status tunnel-client.service --no-pager
sudo journalctl -u tunnel-client.service -b --no-pager
sudo -u tunnel-client bash -c 'set -a; source /etc/tunnel-client/tunnel-client.env; set +a; /opt/tunnel-client/tunnel-client doctor --explain'
```

Correct the first reported configuration or connectivity error before changing
unrelated settings.

## Quick checklist

```text
[ ] hamqtt-mcp is running
[ ] HAMQTT MCP read access is enabled
[ ] http://127.0.0.1:8001/mcp is reachable on the tunnel host
[ ] tunnel-client.service is active
[ ] /healthz returns HTTP 200
[ ] /readyz returns HTTP 200
[ ] /ui shows the expected tunnel ID and MCP destination
[ ] ChatGPT uses the same tunnel ID
[ ] ChatGPT can complete a read-only HAMQTT request
[ ] No runtime API key or admin key was committed or shared
```

## Official references

- [OpenAI tunnel-client repository](https://github.com/openai/tunnel-client)
- [Latest tunnel-client release](https://github.com/openai/tunnel-client/releases/latest)
- [OpenAI Platform Tunnels management](https://platform.openai.com/settings/organization/tunnels)
- [OpenAI Platform runtime API keys](https://platform.openai.com/settings/organization/api-keys)
- [ChatGPT connector settings](https://chatgpt.com/#settings/Connectors)
