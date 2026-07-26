# Claude ↔ LightWave 2019 MCP connector (proof of concept)

Built on LightWave 2019's official Command Port (`lwsdk.LWCommandPort`).
**Both writes and reads are proven working end to end**, confirmed live
through the real `lw_ping` (returned `"pong"`) and `lw_get_scene_info`
(correctly returned the live scene's actual items) MCP tools - see
`PLAN.md` for the full log, including two confirmed dead ends for reads
before the working mechanism was found.

## What works right now

Ask Claude (once set up - see below) to:
- Create a Null item (`lw_create_null`) - sends `AddNull` over the
  Command Port, confirmed to create a real item in the live scene.
- Run any native Layout command (`lw_run_command`) - a generic passthrough
  to the ~800 commands in `lwcommandport/layout/__init__.py` (the same
  client library NewTek ships with LightWave). One-way, no confirmation
  that LightWave accepted it, just that it was sent.
- Ping LightWave (`lw_ping`) and get live scene info (`lw_get_scene_info`)
  - real round trips, built on `LWComRing` (see `PLAN.md` for how this
  read path actually works and the real NewTek client-library bug that
  had to be fixed to make it work).

## Setup

**1. Enable the Command Port (once per Layout session)**

Utilities → Plugins → Add Plugins → select `lw_enable_command_port.py`.
It runs automatically on load (it's a "single-shot" plug-in) - the title
bar should change to show `(CP: 9735)`.

**2. Enable the read path (once per Layout session)**

Utilities → Plugins → Add Plugins → select `lw_mcp_ring.py`. Then
Utilities → Master Plugins → "Add Layout or Scene Master" dropdown →
select "LW MCP Ring" (listed as "Claude MCP Command Port Ring listener")
→ make sure its "On" checkbox is ticked. Unlike step 1, this one needs
both the Add Plugins step and this activation step.

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

With Layout running and both plug-ins enabled, ask Claude to create a
Null item, then ask it to ping LightWave or get scene info. Check Layout
- the Null should appear immediately, and the ping/scene-info replies
should reflect the live scene.

If you ever see writes silently stop working (success responses but
nothing appears in Layout), suspect a hung Layout session first - a
clean restart of Layout (re-running steps 1-2) reliably fixes it. This
happened once during development and was mistaken for a code bug; it
wasn't.

## Files

- `lw_enable_command_port.py` — run once inside Layout. Enables writes. Working.
- `lw_mcp_ring.py` — Master plug-in enabling reads via `LWComRing`. Needs both Add Plugins and Master Plugins activation. Working.
- `server.py` — MCP server Claude Desktop launches. Writes and reads both work.
- `lwcommandport/` — NewTek's official Command Port client (copied from the LightWave install), with one real bug fixed in `Ring()` (see `PLAN.md`).
- `lw_mcp_master.py`, `lw_mcp_query.py` — two earlier, unsuccessful attempts at solving reads, kept for reference/history. Do not load.
- `lw_socket_master.py` — superseded very first draft. Do not load.
- `PLAN.md` — full build log: what's verified, what failed, what to try next.
