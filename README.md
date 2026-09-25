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
- `lw_load_object(filename)` (ROADMAP2.md item 2) - loads a real mesh
  object (`.lwo`) into the scene via the native `LoadObject` command,
  closing this connector's biggest capability gap up to this point:
  previously only Nulls could be created directly in Layout, and real
  geometry needed a separate Modeler round-trip. Confirmed live:
  loading a small rig-part `.lwo` produced real triangle geometry
  visible in the viewport and a working item (`connector_01` appeared
  in `lw_get_scene_info`, `lw_get_transform` returned a valid
  position). `filename` must be an absolute path readable by the
  LightWave process.
- **Scene file I/O** (ROADMAP2.md item 3) - `lw_save_scene_as(filename)`,
  `lw_load_scene(filename)`, `lw_clear_scene()`, `lw_save_object(name,
  filename)`. Confirmed live end to end: saved a real scene, verified
  its file content referenced the actual items with correct numeric
  IDs, cleared the scene, reloaded it, and confirmed every item came
  back. Loading from outside LightWave's configured Content Directory
  pops a blocking "Change Content Directory?" dialog a one-way command
  can't dismiss - answering "No" still lets the scene load.
  `lw_save_object` has a real, documented limitation: for a freshly
  loaded multi-layer object (via `lw_load_object`), `SelectItem` by
  name or by its regular numeric ID may not switch the current object
  the *first* time this session - a genuine manual click was needed
  once before automation-only selection became reliable for that
  object. See `PLAN.md` "Scene file I/O" for the full investigation.
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
  **Now also walks bone chains within each object** (`LWItemInfo.first(
  LWI_BONE, object)`/`next()`) - confirmed live and safe against a real
  2-bone chain, unlike `LWChannelInfo`/`nextGroup`, which crashed
  Layout outright (see `PLAN.md`). Bones don't need a real mesh object
  to test against - `AddBone`/`AddChildBone` attach directly to a Null.
- `lw_get_current_time` - the live playhead's frame and time (seconds).

  **Formerly a known limitation, now solved:** camera/light/transform
  animatable values (`lw_get_camera_info`/`lw_get_light_info`/
  `lw_get_transform`) used to be hardcoded to `time=0.0` (scene start)
  instead of LightWave's live playhead. Fixed via `lwsdk.LWTimeInfo()`
  - confirmed live: keyframed a Null at frame 0/frame 30, moved the
  playhead to frame 15 with `GoToFrame`, and `lw_get_transform`
  correctly returned the interpolated frame-15 position instead of the
  frame-0 default. See `PLAN.md` for the full investigation.

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
  numbers. **Multi-frame `RenderScene` progress tracking is now
  confirmed live too** - `frame_count` correctly climbs across a
  multi-frame render rather than stalling or jumping straight to done.
  One real subtlety found along the way: the real per-frame signal is
  `IFrameBuffer.begin()` (`open()`/`close()` only fire once for the
  whole render session), and `begin()` fires once per **enabled render
  buffer** per frame (Render Properties > Buffers), not once per frame
  alone - divide `frame_count` by the number of enabled buffers if an
  exact frame count matters. Also fixed a real bug: the counter was
  continuing to climb across separate renders in the same session
  instead of resetting. See `PLAN.md` for the full investigation.
  Bonus: `SetRenderDisplay` turns out to be scriptable after all
  (`lw_run_command("SetRenderDisplay", ["LW MCP Render Monitor"])`) -
  a wrapped-method bug, not a real LightWave limitation.

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

**Item relationships** - `lw_set_parent(child, parent)`,
`lw_set_target(item, target)`, `lw_set_goal(item, goal)`,
`lw_set_pole(item, pole)`, `lw_get_item_id(name)`
- fixed a real gap: `ParentItem`/`TargetItem`/`GoalItem`/`PoleItem`
  silently no-op when given an item's name instead of the plain numeric
  ID LightWave's Command Port actually expects for these specific
  commands. Two related bugs, both root-caused via Cmd History
  (Utilities → Commands → Cmd History, which logs the literal native
  command any UI action runs): (1) these commands need a numeric ID
  argument, not a name - `SelectItem` is the one exception that really
  does resolve names; (2) `SelectItem(name)` itself is only reliable
  for Objects - Camera/Light need `SelectItem` called with their own
  numeric ID too, not their name, to correctly become the "current
  item" this command family reads. Each item-type category has its own
  ID range (Objects `10000000+`, Lights `20000000+`, Cameras
  `30000000+`). `lw_get_item_id` resolves a name to its numeric ID via
  `lwsdk.itemid_to_str()`; the four `lw_set_*` tools resolve BOTH
  arguments to IDs and never trust `SelectItem`'s name resolution.
  Confirmed live: `lw_set_parent`/`lw_set_target` work for all three
  item categories (Object/Light/Camera); `lw_set_goal`/`lw_set_pole`
  confirmed too - no bones/true IK chain needed to test, since
  `goal()`/`pole()` are generic per-item properties, set and read back
  correctly on a plain Null - see `PLAN.md` for the full investigation.

**Light/object visibility linking** (ROADMAP2.md item 1) -
`lw_include_light(light, obj)`, `lw_exclude_light(light, obj)`,
`lw_include_object_light(obj, light)`, `lw_exclude_object_light(obj,
light)` - wraps `IncludeObject`/`ExcludeObject`/`IncludeLight`/
`ExcludeLight`, controlling which objects a light illuminates (Light
Properties → Objects tab / Item Properties → Lights tab - the same
underlying data either way, confirmed to stay in sync from both
sides). Same numeric-ID fix as the item-relationship tools above.
Confirmed live end to end via the actual UI panels, not just Cmd
History: adding, and toggling Include ↔ Exclude, both correctly
updated the same list entry rather than creating duplicates.

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

Utilities → Plugins → Add Plugins → select `lw_mcp_render_monitor.py`
(needs re-adding each fresh Layout session, same as `lw_mcp_ring.py` -
the Render Display dropdown can visually keep showing "LW MCP Render
Monitor" as a leftover preference even when the underlying plug-in
class isn't actually loaded this session, which looks like it worked
but silently doesn't). Then Render → Render Properties → General tab →
"Render Display" dropdown → select "LW MCP Render Monitor" - or script
it: `lw_run_command("SetRenderDisplay", ["LW MCP Render Monitor"])`
(this command does take an argument over the network; an earlier
version of this doc claimed it didn't, based on a wrapped-method bug
now fixed). If Add Plugins reports the plug-in can't be added/is
locked, it's because it's currently the active Render Display - switch
the display away first (e.g. to "Image Viewer"), reload, then switch
back.

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
