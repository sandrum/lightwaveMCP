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
- Get the current selection (`lw_get_selection`), a camera's settings
  (`lw_get_camera_info`), or a light's settings (`lw_get_light_info`) -
  all confirmed live. Note: animatable camera/light values (focal
  length, color, intensity, etc.) are evaluated at scene start
  (time=0.0), not LightWave's live playhead - see `PLAN.md`/`ROADMAP.md`
  for why and what it would take to fix.
- Run any native **Modeler** command (`modeler_run_command`) - same
  pattern as `lw_run_command` but for Modeler, which uses a different
  Command Port mechanism (see Setup step 3 below). Confirmed live:
  `command="new"` created a real new object layer. Modeler *reads*
  aren't solved yet - see `ROADMAP.md`.

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

**3. Enable Modeler's Command Port (once per Modeler session, optional -
only needed for `modeler_run_command`)**

Modeler uses a different mechanism than Layout - not
`LWCommandPort().enable()`, but `ModCommand()` + executing a command
called `ENABLECOMMANDPORT`. In Modeler: Utilities → Plugins → Add
Plugins → select `lw_enable_modeler_command_port.py` (this only
*registers* it - Modeler treats single-file plug-ins differently than
Layout). Then Utilities → Additional → find and click
`lw_enable_modeler_command_port` in the list to actually run it. Title
bar should change to show `(CP: 9736)`. Note: the script may report
"failure" internally (a real bug in this SDK build's `ModCommand.
execute()` return code, not an actual failure) - trust the title bar,
not any printed result.

**4. Install the MCP server's dependency**

```
pip install "mcp[cli]" --break-system-packages
```

**5. Point Claude Desktop at `server.py`**

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

**6. Test**

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

- `lw_enable_command_port.py` — run once inside Layout. Enables Layout writes. Working.
- `lw_mcp_ring.py` — Master plug-in enabling Layout reads via `LWComRing`. Needs both Add Plugins and Master Plugins activation. Working.
- `lw_enable_modeler_command_port.py` — run once inside Modeler (Add Plugins, then Utilities > Additional). Enables Modeler writes. Working.
- `server.py` — MCP server Claude Desktop launches. Layout writes/reads and Modeler writes all work.
- `lwcommandport/` — NewTek's official Command Port client (copied from the LightWave install), with one real bug fixed in `Ring()` (see `PLAN.md`).
- `lw_mcp_master.py`, `lw_mcp_query.py` — two earlier, unsuccessful attempts at solving Layout reads, kept for reference/history. Do not load.
- `lw_socket_master.py` — superseded very first draft. Do not load.
- `lw_mcp_diag.py`, `lw_mcp_diag2.py`, `lw_mcp_diag3.py`, `lw_diag_modeler_cp.py` — throwaway live-introspection probe plug-ins, not needed going forward.
- `PLAN.md` — full build log: what's verified, what failed, what to try next.
- `ROADMAP.md` — prioritized list of what to build next.
