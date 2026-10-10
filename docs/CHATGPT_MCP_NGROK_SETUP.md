# Connect HA MQTT Store to ChatGPT with MCP and ngrok

This guide explains how to connect the local, read-only HA MQTT Store MCP service to ChatGPT Personal using a temporary public HTTPS endpoint created with ngrok.

The setup has three parts:

1. The HA MQTT Store application and MCP service run locally.
2. ngrok securely forwards a public HTTPS URL to the local MCP port.
3. ChatGPT is configured with the public URL plus `/mcp`.

## Important security notes

- The MCP service is read-only. It can expose stored Home Assistant and MQTT data, but it does not publish MQTT messages, call Home Assistant services, or write to the database.
- The MCP endpoint is currently unauthenticated. Anyone who obtains the temporary ngrok URL may be able to query it while the tunnel is running.
- Do not share the ngrok URL. Stop the tunnel immediately after use with `Ctrl+C`.
- Do not expose this endpoint for long-term or production use without adding authentication and other security controls.
- The ngrok URL normally changes when a new tunnel is started. Configure ChatGPT again if the URL changes.

## Prerequisites

Run the commands from:

```text
C:\Users\janne\Documents\VS_HAMQTT_STORE
```

You need:

- Podman and `podman-compose`.
- A working HA MQTT Store installation.
- An ngrok account and an installed ngrok client.
- A ChatGPT account that shows **Add custom MCP server** or **Create app**.

## 1. Start the local HA MQTT Store services

Start the Podman machine. It is safe if it is already running:

```powershell
podman machine start podman-machine-default
```

Build the image if the source code has changed:

```powershell
cd C:\Users\janne\Documents\VS_HAMQTT_STORE
podman build -t localhost/hamqtt-store:dev .
```

Start the database, web application, ingestion workers, and MCP service:

```powershell
podman-compose --in-pod false up -d postgres migrate web mqtt-ingestor ha-ingestor mcp
```

If old containers prevent recreation, remove only the application containers and start them again:

```powershell
podman rm -f hamqtt-migrate hamqtt-web hamqtt-mqtt-ingestor hamqtt-ha-ingestor hamqtt-mcp
podman-compose --in-pod false up -d postgres migrate web mqtt-ingestor ha-ingestor mcp
```

The PostgreSQL data is stored in the named volume `hamqtt-postgres-data`. Do not remove that volume unless you intentionally want to delete the local database.

## 2. Enable MCP read access in the web UI

1. Open [http://localhost:8000/settings](http://localhost:8000/settings).
2. Find **AI / MCP service**.
3. Enable **MCP read access**.
4. Leave **Access level** set to **Read only**.
5. Save the MCP settings.

Restart the MCP container after changing the setting:

```powershell
podman restart hamqtt-mcp
```

The local MCP endpoint is:

```text
http://localhost:8001/mcp
```

## 3. Install and authenticate ngrok

If ngrok is not installed, install it using the official ngrok installation method for Windows. Then verify it is available:

```powershell
ngrok version
```

Authenticate the local ngrok client with the authtoken from your ngrok account:

```powershell
ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN
```

Replace `YOUR_NGROK_AUTHTOKEN` with the real token. Do not put the token in this document or commit it to the repository.

Authentication is normally needed only once per Windows user account.

## 4. Start the ngrok HTTPS tunnel

Keep the local MCP service running, then open a separate PowerShell window and run:

```powershell
ngrok http 8001
```

ngrok displays a forwarding address similar to:

```text
Forwarding  https://example-name.ngrok-free.app -> http://localhost:8001
```

Copy the HTTPS address and append `/mcp`:

```text
https://example-name.ngrok-free.app/mcp
```

Use the exact hostname shown by your own ngrok process. Do not use `http://localhost:8001/mcp` in ChatGPT because ChatGPT cannot reach your computer's localhost.

### Optional: check the tunnel locally

With ngrok running, its local inspection API is normally available at `http://127.0.0.1:4040`:

```powershell
curl.exe -sS http://127.0.0.1:4040/api/tunnels
```

The response contains the current `public_url`. The MCP URL is that value followed by `/mcp`.

## 5. Add the custom MCP server in ChatGPT Personal

The wording may vary slightly by ChatGPT version and language.

1. Open ChatGPT.
2. Open **Apps**, **Add-ons**, **Plugins**, or the new-chat tools menu.
3. Select **Add custom MCP server** or **Create app**.
4. Enter the following values:

| ChatGPT field | Value |
|---|---|
| Name | `HA MQTT Store` |
| Description | `Read-only Home Assistant and MQTT data` |
| Connection / Server URL | `https://YOUR-NGROK-HOST.ngrok-free.app/mcp` |
| Authentication | `No authentication` / `Ei todennusta` |

Replace `YOUR-NGROK-HOST.ngrok-free.app` with the hostname printed by ngrok. The URL must end in `/mcp`.

5. Read the warning about custom MCP servers.
6. Select the confirmation checkbox.
7. Click **Create app** / **Luo lisäosa**.
8. Start a new chat and enable **HA MQTT Store** from the tools or apps menu.

The server may expose tools for system summaries, Home Assistant entities and history, MQTT topics and messages, parsed fields, current values, and the object catalog.

## 6. Test the connection

Try a read-only request in a new ChatGPT conversation, for example:

```text
Use HA MQTT Store to show the stored data summary.
```

Other useful test requests:

```text
List the available Home Assistant entities.
```

```text
Show the newest MQTT topics and their current values.
```

If ChatGPT cannot connect, keep the ngrok PowerShell window open and check the troubleshooting section below.

## 7. Stop the public connection when finished

In the PowerShell window running ngrok, press:

```text
Ctrl+C
```

This invalidates the temporary public forwarding address. You can also stop the MCP container if it is not needed:

```powershell
podman stop hamqtt-mcp
```

To start it again later:

```powershell
podman start hamqtt-mcp
```

## Troubleshooting

### ChatGPT says the URL is invalid

- Confirm that the URL starts with `https://`.
- Confirm that it ends with `/mcp`.
- Use the current URL printed by ngrok; old free tunnel URLs may no longer exist.
- Make sure ngrok is still running.

### ChatGPT cannot connect to the server

Check the local services:

```powershell
curl.exe -sS http://localhost:8000/health
podman ps
podman logs hamqtt-mcp
```

Check the ngrok tunnel:

```powershell
curl.exe -sS http://127.0.0.1:4040/api/tunnels
```

The MCP container should be running as `hamqtt-mcp`, and the tunnel should forward to local port `8001`.

A plain browser `GET` request to `/mcp` may return HTTP `400` because Streamable HTTP MCP expects a valid MCP protocol request and session. That response alone does not mean the service is broken.

### The MCP tools report that access is disabled

Open [http://localhost:8000/settings](http://localhost:8000/settings), enable **MCP read access**, keep the level at **Read only**, save, and restart the container:

```powershell
podman restart hamqtt-mcp
```

### The custom MCP option is missing in ChatGPT Personal

Custom MCP/developer controls are not available on every account, plan, workspace, or interface version. Check both:

- The **Apps** or **Add-ons** settings page.
- The tools menu when creating a new chat.

If neither place contains **Add custom MCP server** or **Create app**, this ChatGPT account cannot currently add a custom MCP server through the visible UI. Use Codex as an alternative:

```powershell
cd C:\Users\janne\Documents\VS_HAMQTT_STORE
codex mcp add hamqtt-store -- python -m hamqtt_store.cli mcp
```

The Codex command uses the local stdio MCP transport and does not require ngrok.

### The ngrok URL changes

This is normal for a temporary free tunnel. Start ngrok again, copy the new HTTPS hostname, append `/mcp`, and update the custom app connection URL in ChatGPT.

## Quick-start checklist

```text
[ ] Podman machine is running
[ ] hamqtt-mcp container is running
[ ] MCP read access is enabled at http://localhost:8000/settings
[ ] ngrok authentication has been configured
[ ] ngrok http 8001 is still running
[ ] ChatGPT URL is the current HTTPS ngrok URL ending in /mcp
[ ] ChatGPT authentication is set to No authentication
[ ] ngrok is stopped with Ctrl+C after use
```