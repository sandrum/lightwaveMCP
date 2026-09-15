# Claude ↔ LightWave 2019 MCP connector (proof of concept)

Built on LightWave 2019's official Command Port (`lwsdk.LWCommandPort`).
**Both writes and reads are proven working end to end**, confirmed live
through the real `lw_ping` (returned `"pong"`) and `lw_get_scene_info`
(correctly returned the live scene's actual items) MCP tools - see
`PLAN.md` for the full log, including several confirmed dead ends before
each working mechanism was found, and `ROADMAP.md` for what's been built
and what's explicitly out of scope.

## What works right now

**Layout writes**
- `lw_create_null` - sends `AddNull`, confirmed to create a real item.
- `lw_run_command` - generic passthrough to any of the ~800 native
  commands in `lwcommandport/layout/__init__.py`. One-way, no
  confirmation LightWave accepted it, just that it was sent.
- `lw_set_keyframe(name, frame, position, rotation, scale)` - wraps the
  common by-hand animation sequence (select, go to frame, set
  transform, create key) into one call. Confirmed live: two keyframes
  on a Null produce real interpolated motion, not just two writes.
  Note: `rotation` here is in **degrees** (Layout's UI/command-line
  convention); the read-side `lw_get_transform` reports rotation in
  **radians** (the SDK's convention) - a real unit mismatch to be aware
  of, not a bug.

**Layout reads** (all via `LWComRing`, see Setup step 2)
- `lw_ping`, `lw_get_scene_info` - round trip + live item list.
- `lw_get_selection` - every item's name/type/selected state.
- `lw_get_camera_info`, `lw_get_light_info` - resolution, focal length,
  f-stop, FOV, zoom / type, falloff, color, intensity, range.
- `lw_get_transform` - position/rotation/scale via `LWItemInfo.param()`.
- `lw_get_surface_info` - color, diffuse, luminosity, specularity,
  glossiness, reflection, transparency, smoothing via `LWSurfaceFuncs`.
- `lw_get_hierarchy` - every item's parent, plus IK target/goal/pole,
  by name. Useful before rigging on top of something already parented.
  Does **not** walk bone chains within an object yet (no boned object
  has been available to verify that traversal safely against).

  **Known limitation, carried forward:** camera/light/transform
  animatable values are evaluated at `time=0.0` (scene start), not
  LightWave's live playhead - querying the actual current frame from
  Python is still unsolved. Fine for non-animated items, wrong for
  animated ones.

**Render / camera automation**
- `lw_set_camera_resolution(width, height)` - wraps `FrameSize` (a
  scene-wide render global, not literally per-camera despite the name).
- `lw_render_frame(frame=None)`, `lw_render_scene()`, `lw_abort_render()`
  - one-way, fire-and-forget like every command here.
- `lw_get_render_status()` - the actual point of this group: real
  completion state (`rendering: true/false`, resolution, `frame_count`)
  read from `lwsdk.IFrameBuffer` callbacks (see Setup step 3), not a
  guess based on elapsed time. Confirmed live: resolution set, render
  triggered, status correctly went `true` -> `false` with matching
  numbers. Multi-frame `RenderScene` progress tracking is untested.

**Modeler**
- `modeler_run_command` - same pattern as `lw_run_command` but for
  Modeler's separate Command Port mechanism (see Setup step 4).
  Confirmed live: `command="new"` created a real new object layer.
- Modeler **reads are a confirmed dead end** - `modeler_ping` and
  `modeler_get_object_info` will always time out. Modeler has no
  `LWComRing`-equivalent, and the network Command Port only reaches
  native/compiled commands, not Python-registered ones (confirmed three
  independent ways, including against NewTek's own bundled sample
  plug-in). See `PLAN.md`/`ROADMAP.md` item 5 - not worth retrying
  without new information (NewTek support, or a newer SDK version).

**Reparenting** - `lw_set_parent(child, parent)` and `lw_get_item_id(name)`
- fixed a real gap: `ParentItem` (and the same family - `TargetItem`,
  `GoalItem`, `PoleItem`) silently no-ops when given an item's name
  instead of the plain numeric ID LightWave's Command Port actually
  expects for these specific commands (`SelectItem` is the one
  exception that really does resolve names). Root-caused by comparing
  Cmd History's log of a real UI-driven reparent (`ParentItem 10000000`)
  against this connector's failed attempts (`TargetItem 0` - silently
  coerced to a no-op, no error, no dialog). `lw_get_item_id` resolves a
  name to that numeric ID via `lwsdk.itemid_to_str()`; `lw_set_parent`
  wraps the full corrected sequence. Confirmed live on a fresh pair of
  Nulls with no manual UI interference - see `PLAN.md` for the full
  investigation. `TargetItem`/`GoalItem`/`PoleItem` aren't wrapped in
  their own convenience tools yet, but `lw_get_item_id` is generic and
  fixes the same root cause for any of them.

## Setup

**1. Enable the Command Port (once per Layout session)**

Utilities → Plugins → Add Plugins → select `lw_enable_command_port.py`.
It runs automatically on load (it's a "single-shot" plug-in) - the title
bar should change to show `(CP: 9735)`.

**2. Enable the read path (once per Layout session)**

Utilities → Plugins → Add Plugins → select `lw_mcp_ring.py`. Then
Utilities → Master Plugins → "Add Layout or Scene Master" dropdown →
select "LW MCP Ring4" (listed as "Claude MCP Command Port Ring listener")
→ make sure its "On" checkbox is ticked. Unlike step 1, this one needs
both the Add Plugins step and this activation step.

If `lw_ping` times out even after this, LightWave's Master Plugin
activation is known to be flaky in this environment - remove the
listener from the Master Plugins list, re-add the file via Add Plugins,
and reselect it from the dropdown. This has been needed after nearly
every fresh Layout launch throughout development; treat it as expected
friction, not a bug.

**3. Enable render completion signaling (once per Layout session,
optional - only needed for `lw_get_render_status`)**

Utilities → Plugins → Add Plugins → select `lw_mcp_render_monitor.py`.
Then Render → Render Properties → General tab → "Render Display"
dropdown → select "LW MCP Render Monitor". Unlike Master Plugins, this
only needs to be selected once - LightWave has no networked way to pick
the active Render Display, so this step can't be automated.

**4. Enable Modeler's Command Port (once per Modeler session, optional -
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

**5. Install the MCP server's dependency**

```
pip install "mcp[cli]" --break-system-packages
```

**6. Point Claude Desktop at `server.py`**

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

**7. Test**

With Layout running and steps 1-2 done, ask Claude to create a Null
item, then ask it to ping LightWave or get scene info. Check Layout -
the Null should appear immediately, and the ping/scene-info replies
should reflect the live scene.

If you ever see writes silently stop working (success responses but
nothing appears in Layout), suspect a hung or duplicate Layout process
first - Windows can end up running more than one `Layout.exe`
simultaneously, with the MCP query listener bound to a stale one while
the visible window is a different, disconnected process. Check the
Scene Editor (Utilities → Editors → Scene Editor) against query
responses to catch this; a clean restart of all Layout processes
reliably fixes it.

## Files

- `lw_enable_command_port.py` — run once inside Layout. Enables Layout writes. Working.
- `lw_mcp_ring.py` — Master plug-in enabling Layout reads via `LWComRing` (scene info, selection, camera/light/transform/surface/hierarchy/render-status/item-id queries). Needs both Add Plugins and Master Plugins activation. Working.
- `lw_mcp_render_monitor.py` — Render Display plug-in (`lwsdk.IFrameBuffer`) providing real render completion signaling for `lw_get_render_status`. Needs Add Plugins plus manual selection as the active Render Display. Working.
- `lw_enable_modeler_command_port.py` — run once inside Modeler (Add Plugins, then Utilities > Additional). Enables Modeler writes. Working.
- `lw_mcp_modeler_query.py` — Modeler read-path attempt. Works when invoked from inside Modeler's own UI, but confirmed unreachable over the network - kept for the record, not usable as-is. See `ROADMAP.md` item 5.
- `server.py` — MCP server Claude Desktop launches. Layout writes/reads, animation, render/camera automation, hierarchy queries, and Modeler writes all work; Modeler reads do not (see above).
- `lwcommandport/` — NewTek's official Command Port client (copied from the LightWave install), with one real bug fixed in `Ring()` (see `PLAN.md`).
- `lw_mcp_master.py`, `lw_mcp_query.py` — two earlier, unsuccessful attempts at solving Layout reads, kept for reference/history. Do not load.
- `lw_socket_master.py` — superseded very first draft. Do not load.
- `lw_mcp_diag.py`, `lw_mcp_diag2.py`, `lw_mcp_diag3.py`, `lw_diag_modeler_cp.py` — throwaway live-introspection probe plug-ins, not needed going forward.
- `PLAN.md` — full build log: what's verified, what failed, what to try next.
- `ROADMAP.md` — what's been built, in order, and why; the current state of every planned increment.
