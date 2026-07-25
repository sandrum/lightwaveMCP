# Claude ↔ LightWave 2019 MCP connector (proof of concept)

Built on LightWave 2019's official Command Port (`lwsdk.LWCommandPort`).
**Writes are proven working end to end** (tested live - see `PLAN.md` for
the full log). **Reads are not solved yet** - two approaches were tried
and both ruled out by direct testing; `PLAN.md` documents exactly what was
tried and what to try next.

## What works right now

Ask Claude (once set up - see below) to:
- Create a Null item (`lw_create_null`) - sends `AddNull` over the
  Command Port, confirmed to create a real item in the live scene.
- Run any native Layout command (`lw_run_command`) - a generic passthrough
  to the ~800 commands in `lwcommandport/layout/__init__.py` (the same
  client library NewTek ships with LightWave). One-way, no confirmation
  that LightWave accepted it, just that it was sent.

## What doesn't work yet

`lw_ping` and `lw_get_scene_info` - anything that needs data back *out*
of LightWave. The Command Port is one-way (UDP, fire-and-forget); getting
a response out requires LightWave to run code and write a file
somewhere, and every mechanism tried for triggering that from the outside
failed in testing. See `PLAN.md` for specifics and next ideas (the most
promising untried one: parsing a scene file written via the native
`SaveSceneAs` command, instead of any custom plug-in).

## Setup

**1. Enable the Command Port (once per Layout session)**

Utilities → Plugins → Add Plugins → select `lw_enable_command_port.py`.
It runs automatically on load (it's a "single-shot" plug-in) - the title
bar should change to show `(CP: 9735)`.

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
      "command": "python",
      "args": ["C:\\Users\\sandr\\IdeaProjects\\LightwaveMCP\\server.py"]
    }
  }
}
```

Restart Claude Desktop.

**4. Test**

With Layout running and the Command Port enabled, ask Claude to create a
Null item. Check Layout - it should appear immediately.

## Files

- `lw_enable_command_port.py` — run once inside Layout. Working.
- `server.py` — MCP server Claude Desktop launches. Writes work, reads don't yet.
- `lwcommandport/` — NewTek's official Command Port client (copied from the LightWave install).
- `lw_mcp_master.py`, `lw_mcp_query.py` — two different attempts at solving reads, both instructive dead ends, kept for reference.
- `lw_socket_master.py` — superseded very first draft. Do not load.
- `PLAN.md` — full build log: what's verified, what failed, what to try next.
