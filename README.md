# Claude ↔ LightWave 2019 MCP connector (proof of concept)

Two files, mirroring how `blender-mcp` bridges Claude to Blender:

- `lw_socket_master.py` — a LightWave **Master-class** Python plugin. Runs
  inside Layout, opens a TCP socket on `127.0.0.1:9799`, and executes
  queued commands on LightWave's main thread.
- `server.py` — a standalone **MCP server** (not run inside LightWave).
  Claude Desktop launches this via stdio; it forwards tool calls over TCP
  to the plugin above.

```
Claude  <--stdio-->  server.py  <--TCP:9799-->  lw_socket_master.py (inside Layout)
```

## Status: transport layer done, scene commands are stubs

The networking/threading code in both files is standard Python and should
work as written. The actual LightWave scene-editing calls
(`_get_scene_info`, `_create_null` in `lw_socket_master.py`) are
placeholders — see `PLAN.md` for the verification steps in progress.

## Setup

**1. Load the plugin in LightWave Layout**

- Utilities tab → Plugins → Edit Plugins (or Add Plugins) → point it at
  `lw_socket_master.py`.
- Confirm it loads without errors (Layout's error log / console will show
  Python tracebacks if `import lwsdk` or the class definitions fail).
- It should appear as a Master plugin named `MCP_Socket_Master` — make sure
  it's enabled (Master plugins can be toggled on/off in the same panel).

**2. Install the MCP server's dependency**

```
pip install "mcp[cli]" --break-system-packages
```

**3. Point Claude Desktop at `server.py`**

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lightwave": {
      "command": "python3",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

Restart Claude Desktop.

**4. Test**

With Layout running and the plugin loaded, ask Claude to call `lw_ping`.
If it returns `"pong"`, the transport layer (socket + threading + MCP) is
solid end to end.

See `PLAN.md` for the full build plan and current status.
