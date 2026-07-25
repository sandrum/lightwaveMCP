# Claude ↔ LightWave 2019 MCP connector (proof of concept)

Built on LightWave 2019's **official Command Port** (`lwsdk.LWCommandPort`),
not a hand-rolled socket server. See `PLAN.md` for the full story, including
why the first design (`lw_socket_master.py`, now superseded) got replaced.

## Architecture

```
Claude  <--stdio-->  server.py  <--UDP, Command Port-->  Layout
                          |
                          `--reads--> _mcp_response.json <--writes-- lw_mcp_query.py (plug-in, inside Layout)
```

- **Writes** (e.g. creating a Null) go straight through LightWave's own
  built-in commands (`AddNull`, etc.) via the `lwcommandport` Python client
  NewTek ships at `support/python/lwcommandport` in the LightWave install
  (copied into this folder so `server.py` can just `import` it). One-way,
  fire-and-forget, but official and safe - LightWave's own listener handles
  main-thread execution internally.
- **Reads** (e.g. scene info) need a way back out, and the Command Port is
  one-way UDP with no response channel. So `lw_mcp_query.py` is a small
  registered plug-in, loaded once inside Layout, that `server.py` invokes
  by name over the Command Port (`CommandInput LW_MCP_Query get_scene_info`)
  and that writes its answer to `_mcp_response.json`, which `server.py`
  polls.

## Files

- `lw_enable_command_port.py` — run **once** inside Layout to turn on the
  Command Port (single-shot Generic plug-in, no persistent state).
- `lw_mcp_query.py` — registered plug-in that answers read queries by
  writing `_mcp_response.json`.
- `lwcommandport/` — NewTek's own Python client for the Command Port,
  copied from the LightWave install, used by `server.py`.
- `server.py` — the MCP server Claude Desktop launches; bridges tool calls
  to the above.
- `lw_socket_master.py` — superseded first draft, kept for history only.
  Do not load it as a plug-in.

## Status

Written and syntax-checked, not yet run inside a live Layout session.
See `PLAN.md` for the remaining load/test steps.

## Setup

**1. Enable the Command Port (once per Layout session)**

- Utilities → Plugins → Add Plugin → select `lw_enable_command_port.py`.
- Run it once (it should pop up a confirmation message). It has no UI of
  its own beyond that message - it's a "single-shot" plug-in.

**2. Load the query plug-in**

- Utilities → Plugins → Add Plugin → select `lw_mcp_query.py`.
- It should load silently (no confirmation dialog) since it's a
  persistent registered plug-in, not single-shot.

**3. Install the MCP server's dependency**

```
pip install "mcp[cli]" --break-system-packages
```

**4. Point Claude Desktop at `server.py`**

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lightwave": {
      "command": "python",
      "args": ["C:\\Users\\sandr\\IdeaProjects\\LightwaveMCP\\server.py"]
    }
  }
}
```

Restart Claude Desktop.

**5. Test**

With Layout running (Command Port enabled, query plug-in loaded), ask
Claude to call `lw_ping`. If it returns `"pong"`, the whole round trip
(MCP → Command Port → plug-in → response file → MCP) works end to end.
