# Claude ↔ LightWave 2019 MCP connector — build plan

## Item hierarchy query (ROADMAP.md item 7) — DONE

User asked for a way to understand an object's existing parent/child
(and rigging-relevant IK target/goal/pole) relationships before rigging
on top of it. Found the real API the same way as items 1b/1c/6 - fetched
NewTek's official Python SDK docs live rather than guessing
(`static.lightwave3d.com/sdk/2015/python/globaliteminfo.html` - the
`docs.lightwave3d.com` 2025 docs didn't have this specific page indexed,
but the 2015 static docs cover the same `LWItemInfo` class already
proven safe in this project). Confirmed real methods: `parent(item)`,
`target(item)`, `goal(item)`, `pole(item)`, each returning an item ID or
`LWITEM_NULL`.

Shipped `lw_get_hierarchy` (via a new `get_hierarchy` query in
`lw_mcp_ring.py`). Each relationship ID is resolved to a name via a
second `LWItemInfo.name()` call so the response matches every other
query's convention of reporting names, not raw IDs.

**Live-verified with a real relationship, not just an empty scene:**
queried a flat scene (`Light`, `Camera`, no parents) and got `parent:
null` for both, as expected. Then created `ParentTest`/`ChildTest`
nulls and tried to reparent via `lw_run_command("ParentItem",
["ParentTest"])` after `SelectItem("ChildTest")` - **this did NOT
work**: re-querying showed `ChildTest.parent` still `null`, and the
Motion Options panel confirmed `Parent Item: (none)`. Root cause not
yet investigated (worth a follow-up if this connector needs to *write*
parenting, not just read it - possibly needs an item ID rather than a
name, or a different command entirely). Set the parent for real via the
Motion Options panel's "Parent Item" dropdown instead, then re-queried:
`lw_get_hierarchy` correctly returned `{"name": "ChildTest", "parent":
"ParentTest", ...}`. The read side is proven correct against ground
truth; the write side for parenting specifically is not yet solved.

**Deliberately out of scope this round:** bone chain traversal
(`LWItemInfo.first(LWI_BONE, object)` / `next()`) - the live scene had
no boned object to safely verify traversal against, and this project has
a real precedent (`LWChannelInfo`/`nextGroup`) for an SDK traversal call
crashing Layout, so it wasn't shipped un-tested. Follow-up once there's
a real rigged object to test against.

## Render / camera automation (ROADMAP.md item 6) — DONE

The real problem here was never "how do I trigger a render" - RenderFrame/
RenderScene are ordinary native commands, already reachable via
lw_run_command. It was that every command sent through this project's
Command Port client is one-way UDP fire-and-forget (confirmed by reading
`CommandPort._send_command` in `lwcommandport/__init__.py` - it only ever
calls `sendto()`, nothing reads a response), so firing a render command
and assuming it succeeded/finished would just be guessing, which is
exactly what this roadmap item said to avoid.

**Found the real completion signal via NewTek's official docs, not more
live probing.** No docs ship with this 2019.1.5 install, so fetched
docs.lightwave3d.com's 2025 Python SDK reference live (same fetch
pattern that worked for item 1b/1c's `LWItemInfo.param`) and found the
Frame Buffer handler class (`lwsdk.IFrameBuffer` /
`FrameBufferFactory`) - LightWave's actual plug-in architecture for
"Render Display" servers. Real engine-driven callbacks, not polling:
`open(width, height)` when a render session begins, `write()` per
scanline, `close()` when it's complete, `pause()` only during
interactive (F9/manual-advance) renders, not automatic ones.

Shipped `lw_mcp_render_monitor.py`, a Frame Buffer plug-in that ignores
actual pixel data and just records lifecycle state
(`{"rendering": bool, "frame_count": int, "width", "height", "updated"}`)
to `_mcp_render_status.json` on open()/close(). Extended `lw_mcp_ring.py`
with a `get_render_status` query that reads that file and returns it
over the already-proven LWComRing read path - no second polling
mechanism needed. New tools: `lw_render_frame`, `lw_render_scene`,
`lw_abort_render`, `lw_get_render_status`, `lw_set_camera_resolution`
(wraps `FrameSize` - confirmed this is a scene-wide render global in
LightWave, not literally a per-camera setting, despite the name).

**One real wrinkle, discovered live rather than assumed:** LightWave has
no networked way to select which Frame Buffer plug-in is the active
Render Display (`SetRenderDisplay`/`RenderDisplayOptions` take no
arguments per the local command list) - it's chosen once via Render
Properties > General tab > "Render Display" dropdown. Same one-time
manual-UI-step pattern this whole project already leans on for Master
Plugins activation. Confirmed via the dropdown itself listing "LW MCP
Render Monitor" right alongside the built-in options once the plug-in is
loaded, so at least the registration side needs zero guessing.

**Live-verified twice, end to end:**
1. Manually via `lw_run_command("RenderFrame")` before the new server.py
   tools were loaded (Claude Desktop hadn't been restarted yet):
   `_mcp_render_status.json` went from not-existing, to
   `{"rendering": true, "frame_count": 1, "width": 1280, "height": 720}`
   the instant the Render Status dialog appeared, to
   `{"rendering": false, "frame_count": 1}` the instant "Continue" was
   clicked to dismiss it.
2. After restarting to load the new tools: `lw_set_camera_resolution(640,
   360)` -> confirmed 640x360 in the Render Status dialog ->
   `lw_render_frame(frame=0)` -> `lw_get_render_status()` returned
   `rendering: true` with matching width/height while the dialog was still
   up -> dismissed it -> `lw_get_render_status()` returned `rendering:
   false`. Real state read from the render engine's own callbacks, not a
   timer or guess.

Not yet tested: multi-frame `RenderScene` (whether frame_count increments
once per frame or the open/close cycle behaves differently for
animations - the docstring in lw_mcp_render_monitor.py calls this out as
an open question worth checking before relying on frame_count for
progress-bar-style tracking across a whole animation render).

## Animation helper tools (ROADMAP.md item 4) — DONE

Shipped `lw_set_keyframe(name, frame, position=None, rotation=None,
scale=None)` in `server.py`, wrapping the by-hand sequence
(`SelectItem` → `GoToFrame` → `Position`/`Rotation`/`Scale` → `CreateKey`)
into one call. All five native commands were already proven-reachable via
`lw_run_command`, so this was API design, not new SDK territory.

Live-verified end to end on a fresh Null (`AnimTest`, recreated via
`lw_create_null` after the prior session's scene was lost to a Layout
restart):

- `lw_set_keyframe("AnimTest", frame=0, position=[0,0,0])`
- `lw_set_keyframe("AnimTest", frame=30, position=[5,5,5])`

Confirmed via screenshot at three scrubbed timeline positions, not just
the tool's own "success" response:
- Frame 0: Position readout `0m, 0m, 0m`, item at the origin.
- Frame 30: Position readout `5m, 5m, 5m`, with a visible motion path
  from the origin.
- Frame 15 (midpoint): Position readout `3.104m, 3.104m, 3.104m` - not
  the linear midpoint (2.5), consistent with Layout's default TCB spline
  interpolation kicking in between the two keys. This is the real proof:
  the item is genuinely animating between keyframes, not just being
  written to twice.

One documented unit mismatch: `lw_set_keyframe`'s `rotation` argument is
in degrees (Layout's native command-line/UI convention, confirmed live -
values entered here show unchanged in the Motion Options panel), while
`lw_get_transform`'s rotation reading is in radians (the `LWItemInfo` SDK
global's convention). Not a bug, just two different native conventions
on the write side vs. the read side - noted in both tools' docstrings.

## Modeler read path (ROADMAP.md item 5) — researched, confirmed blocked

**Finding: there is currently no known way to get query answers out of a
running Modeler session over the network.** This is a real, well-evidenced
architectural limitation, not a bug in this project's code - confirmed
using NewTek's own bundled sample plugin, not just ours.

Modeler has no Master-plugin/`LWComRing` equivalent at all - confirmed via
`Glob` against the local install: `support/plugins/scripts/Python/Modeler/`
only has a `CommandSequence` folder, no `Master` folder, and NewTek's SDK
docs (docs.lightwave3d.com) confirm Modeler's Python plugin architecture is
`CommandSequence`-only. The natural next idea - since a `CommandSequence`
plug-in registers as an ordinary invocable command, and
`modeler_run_command` already proves arbitrary *native* command names are
invocable over Modeler's Command Port - was to invoke a custom
`CommandSequence` plug-in the same way, passing a query string as its
trailing argument (`mod_command.argument`, confirmed to exist and carry
trailing text via a public third-party plug-in,
github.com/heimlich1024/OD_CopyPasteExternal) and have it answer via a
response file, exactly like the Layout read path but without needing a
persistent listener.

**This does not work.** Live-tested three ways, all failed identically -
no exception, no error dialog, just silence:
- `modeler_ping()` (routed through `_send_command` via the wrapped
  `Modeler` class) - timed out, and `_mcp_modeler_debug.log` was never
  created, meaning `process()` never ran.
- Raw UDP packets sent directly from Modeler's own PCore Python console
  (`socket.sendto(b'LW_MCP_ModelerQuery ping', ('localhost', 9736))` and a
  quoted-display-name variant `"LW MCP Modeler Query" ping`) - `sendto()`
  itself succeeded (returned the byte count, no exception), but the debug
  log still never gained a new line.
- The exact same test against **NewTek's own bundled sample plug-in**
  (`support/plugins/scripts/Python/Modeler/CommandSequence/
  enumerate_surfaces.py`, registered factory ID `LW_PyEnumSurfaces`) via
  raw socket - no observable effect either.

Meanwhile, invoking our plug-in through the UI (Utilities > Additional >
"LW MCP Modeler Query") worked immediately and correctly - `process()`
ran, `mod_command.argument` was empty as expected for a menu click, and
the response file was written. So the plug-in code itself is correct; the
network Command Port specifically does not route to it.

**Conclusion:** despite the `--command-port` documentation's description
("feed LightWave Command Sequence commands directly into the
application"), the network Command Port for both Layout and Modeler
appears to only reach LightWave's native/compiled command table - not
Python-registered plug-in commands. This is the exact same failure mode
that ruled out Layout's very first read-path attempt (`CommandInput
LW_MCP_Query ping` → `"Unknown command"`, documented above) - except for
Modeler there is no known `LWComRing`-style escape hatch, since Modeler
has no persistent Master-plugin architecture at all. Every avenue found
in the SDK docs and every bundled sample either issues commands
*from within* an already-running plug-in (`lookup`/`execute`/`evaluate`,
requires already being invoked some other way first) or requires the
same blocked network invocation to get started.

**Practical alternative, not a true "live" read path:** since Modeler
objects are ordinary `.lwo` files, an external client can already inspect
point/poly counts and surface names by loading the saved file directly
(bypassing Modeler's Python API entirely) - this is exactly how `TestBox.lwo`
was independently useful for testing the surface query in item 1c. This
only reflects saved state, not in-memory unsaved edits, so it's a
real but limited substitute, not a real-time query mechanism.

`lw_mcp_modeler_query.py` and the `modeler_ping`/`modeler_get_object_info`
tools are left in place since they work correctly when invoked from
inside Modeler (e.g. manually, or possibly from a future in-process
bridge) - just not from an external network client as originally hoped.

## Item transform + surface query (ROADMAP.md items 1b/1c) — DONE

**Resolved.** Tracked down NewTek's real SDK docs (etwright.org/lwsdk,
mirrored from the official SDK - the local install ships no headers) and
found real-world working Python plugin code on GitHub
(heimlich1024/OD_CopyPasteExternal) to confirm exact Python calling
conventions. Two real findings unblocked both items without ever going
back through `LWChannelInfo`:

- `LWItemInfo` already has a **direct** `param(item, param_type, time)`
  call for position/rotation/scale (`LWIP_POSITION`/`LWIP_ROTATION`/
  `LWIP_SCALING`) - documented in the C SDK
  (etwright.org/lwsdk/docs/globals/iteminfo.html) and confirmed via a
  real third-party Python plugin's usage pattern
  (`item_info.param(item_id, type, time)` returning the vector directly,
  matching the pattern already proven for `LWCameraInfo`/`LWLightInfo`
  in this file). This completely avoids `LWChannelInfo`/`nextGroup`,
  which is the crash confirmed below. Implemented as `_get_transform()`
  / `lw_get_transform`.
- `LWSurfaceFuncs().byName(surfname, objname)` and `.getFlt(surf,
  channel)` were confirmed via the same real-world plugin code to
  return plain Python lists/floats in the SWIG binding (not the C
  pointers the doc describes). Implemented as `_get_surface_info()` /
  `lw_get_surface_info`.

**Both confirmed live, end to end, with no crashes:**
- `lw_get_transform("TransformTest")` returned the correct default
  transform (`position [0,0,0]`, `rotation [0,0,0]`, `scale [1,1,1]`);
  after moving the item with `lw_run_command("Position", [1.5, 2,
  -0.5])`, a re-query correctly returned `position [1.5, 2.0, -0.5]` -
  proof this reads real live state, not just defaults.
- `lw_get_surface_info("Default")` against a real object (`TestBox.lwo`,
  a unit box built in Modeler and loaded into Layout for this test)
  returned sensible real values: `color_rgb [0.502, 0.502, 0.502]`,
  `diffuse 1.0`, `specularity 0.5`, `glossiness 0.4`, `transparency
  0.0`, `reflection 0.0`, `smoothing -1.5625`. The `smoothing` value's
  sign/exact meaning under the newer Principled BSDF shading model
  isn't fully decoded (magnitude is close to the ~89.5° smoothing angle
  shown in the Surface Editor, in radians) - flagged as a minor open
  question, not a blocker; the mechanism itself is proven safe and
  working.

The diagnostic `_probe_channels`/`lw_probe_channels` stub (crash
writeup below) and `_probe_surf_constants`/`lw_probe_surf` are now
superseded by the real tools and can be removed in a future cleanup
pass, but are left in place for now since they're harmless.

## LWChannelInfo crash (root cause of the original block, kept for the record)

`lwsdk.LWChannelInfo().nextGroup(...)` is the documented way to walk an
item's animation channels (position/rotation/scale live under one
"group" per item). Live probing found real, reproducible problems:

- `nextGroup(None)` (one arg, matching the SDK doc's example) raises
  `LWChannelInfo_nextGroup() takes exactly 3 arguments (2 given)` -
  confirming the doc is wrong about arity for this build; the real
  signature needs a second positional argument.
- `nextGroup(target, None)`, passing a real item ID (obtained from
  `LWItemInfo`, a SWIG object of type `NodeID`) as that second argument,
  **reproducibly crashes the entire Layout process** - no Python
  exception, no traceback, the debug log simply stops after logging
  "about to call nextGroup(target, None)". Confirmed twice, each time
  requiring a full process/machine restart to recover (the second
  occurrence left Layout in a state where even Quit triggered LightWave's
  native crash-reporter dialog). This is almost certainly a native/SWIG
  crash from passing the wrong ID type - `LWChannelInfo` most likely
  expects a different kind of handle (e.g. a channel-group ID) than the
  `NodeID` that `LWItemInfo` hands back, and the binding doesn't
  type-check before dereferencing.
- There is no `LWChannelInfo` C header shipped with this install to
  confirm the real expected argument types (only Python-only headers -
  numpy, PySide, shiboken, win32com - were found anywhere under the
  install directory). Guessing further risks more crashes.

**Decision: stopped guessing.** `_probe_channels()` in `lw_mcp_ring.py`
is now a safe stub - it resolves the target item and returns its ID
plus an explanation, without calling `nextGroup`. Confirmed live (see
below) that this stub is completely safe: repeated calls do not crash
or destabilize Layout. Real transform queries are blocked until NewTek's
actual SDK docs/headers for `LWChannelInfo` can be consulted, or until
someone finds a working reference sample (the same way the read path
itself was eventually solved via NewTek's bundled `command_port_test.py`
rather than guesswork).

**Two operational lessons from chasing this, worth remembering for any
future LightWave MCP debugging session:**

1. **Zombie Layout processes.** Multiple `Layout.exe` processes can run
   at once silently, and an old background one can stay bound to the
   Command Port and keep answering UDP queries with stale scene state
   and stale plugin code, while the window you're actually looking at
   and interacting with is a completely different, disconnected
   process. This produced a long, confusing detour (phantom items in
   query responses that didn't exist in the visible Scene Editor). If
   query results ever look stale or impossible, check Task Manager for
   more than one `Layout.exe` before doubting the code.
2. **"Remove" in Master Plugins doesn't fully deregister a plugin.**
   Repeated Add/Remove cycles during iteration created many duplicate
   entries in Layout's internal plugin catalog (visible in Utilities >
   Edit Plugins, grouped by category - accumulated ~10 stale entries
   this session: Diag through Diag6, Master, Ring through Ring3). Full
   removal requires selecting the entry in **Edit Plugins** (not Master
   Plugins) and clicking **Delete**. Separately, Layout persists "should
   this identifier be active" state at the *application* level, not the
   scene level - a fresh Layout launch after a full machine restart
   prompted "Plug-in Missing: No plug-in of type MasterHandler found
   with name LW_MCP_Ring4. Would you like to load it from disk?",
   confirming this survives across sessions independent of any scene
   file.

Also observed, not fully root-caused: `inst_acquire()`/`ringAttach()`
firing for a freshly-registered Master Plugin is intermittent in this
environment - sometimes the debug log shows the class instantiated but
never followed by "ringAttach called", with no clear trigger. Toggling
the "On" checkbox does not reliably fix it. The only workaround found is
repeating Remove → Add Plugins → reselect-from-dropdown until one
attempt works (usually within 1-3 tries). Current final verified state:
this cycle succeeded, and `lw_ping`, `lw_get_scene_info`, `lw_probe_surf`,
and the now-safe `lw_probe_channels` were all confirmed live against a
freshly-restarted Layout with no crash. Notably, `lw_probe_channels`'s
`target_id` field for a real Null item resolves to a SWIG object of type
`NodeID` (`<Swig Object of type 'NodeID' at 0x...>`) - concrete evidence
for the type-mismatch theory above, and a useful starting point if
`LWChannelInfo`'s real expected ID type is ever tracked down.

**Surface/material query (ROADMAP.md item 1c) is now done too** - see
the "DONE" section above. It turned out not to need `LWChannelInfo` at
all (surfaces have their own dedicated `LWSurfaceFuncs` global), so it
was never actually at risk from the crash above - it was just
sequenced behind item 1b out of caution until a working docs-first
approach was proven.

## Modeler write path (ROADMAP.md item 2)

Confirmed live end to end. Modeler uses a completely different
enable mechanism than Layout - not `lwsdk.LWCommandPort().enable()`, but
`lwsdk.ModCommand()` + looking up and executing a native command called
`"ENABLECOMMANDPORT"` (see `lw_enable_modeler_command_port.py`, adapted
from NewTek's own bundled sample). Two real findings from getting this
working:

- **Modeler treats single-file plug-ins differently than Layout.**
  Loading via Add Plugins only *registers* it as a "Modeling Command" -
  unlike Layout's Generic single-shot scripts, it does not run
  automatically. It has to be separately invoked afterward via
  Utilities > Additional > (the script's name, alphabetical in a long
  list).
- **`ModCommand.execute()`'s reported result code is unreliable.**
  Enabling the port returned `result=0` ("failure" per NewTek's own
  sample comment) both when the port was genuinely free and when it was
  already successfully bound and listening. Confirmed via a UDP
  bind-conflict test (the same ground-truth trick used earlier to debug
  Layout's Command Port) that the enable actually succeeded regardless
  of what the return code said - the title bar showing `(CP: 9736)` is
  the reliable signal, not the result code. This is a third confirmed
  bug/inconsistency in this SDK build's Python bindings, alongside
  `LWMessageFuncs.info()`'s arg count and `IMaster.__init__`'s arg count.

`modeler_run_command` in `server.py` mirrors `lw_run_command`, using the
previously-unused `Modeler` class in `lwcommandport/modeler/__init__.py`
(mesh cleanup, extrude/clone/array tools, booleans, file ops). Confirmed
live via the real MCP tool: sent `command="new"`, Modeler's title bar
changed from "Unnamed" to "Unnamed 1", confirming a real new object
layer was created.

**Not yet done: Modeler reads.** Modeler's plugin architecture
(`CommandSequence`) is different from Layout's Master-plugin model that
`LWComRing` uses for reads - see ROADMAP.md item 5 for what's still
open.

## Current status (tested live against a running Layout 2019.1.5)

**Writes: working, verified, twice over.** `lw.AddNull(...)` sent over UDP
to LightWave's Command Port produces a real Null item in the live scene -
confirmed visually via screenshot, including a from-scratch clean-session
retest (`CleanTest1`/`CleanTest2`, both showed up in the Scene Editor).
`lw_run_command` in `server.py` generalizes this to any of the ~800 native
commands in the bundled `lwcommandport` client.

Note: an earlier round of testing appeared to show writes silently
failing (no items appearing despite "success" responses). Root cause was
NOT a code bug - the Layout session itself had hung (stuck PCore Console,
unresponsive dialogs, Add Plugins silently not executing anything). A
clean Layout restart immediately fixed it. If writes ever appear to stop
working, suspect a hung session before suspecting the connector.

**Reads: now working.** Two earlier approaches were tried and both ruled
out by direct testing:

1. Registered Generic-class plug-in (`lw_mcp_query.py`), invoked by name
   via `CommandInput LW_MCP_Query ping`. Result every time: `Unknown
   command: "LW_MCP_Query"`. LightWave's command resolver only recognizes
   native/compiled commands (like AddNull) - Python `IGeneric` plug-ins
   aren't added to that namespace.
2. Master-class plug-in (`lw_mcp_master.py`) listening for
   `LWEVNT_COMMAND`, per the SDK doc's own `master.html` example.
   Confirmed via debug log that this event never fires for Command Port
   traffic at all (fires for ordinary UI actions only).

**The working mechanism: `LWComRing`.** Found in NewTek's own bundled
sample, which ships with every LightWave 2019.1.5 install:
`support/plugins/scripts/Python/Layout/Master/command_port_test.py`.
A Master plug-in holds an `lwsdk.LWComRing()` instance and calls
`ringAttach(lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)` in
`inst_acquire()`. Command Port traffic arrives at `ring_event(...)` with
`event_code == 0`, decoded via `self._comring.decodeData(('s:256',),
event_data)`. Messages are expected wrapped as `"{Topic} message"`.

This is implemented in `lw_mcp_ring.py`, listening for topic `"MCP"`.
Confirmed live: after loading and activating it, sending
`Ring("MCP", "ping")` produced a real `ring_event` callback (captured in
`_mcp_ring_debug.log`).

**A real bug found along the way, in NewTek's own bundled client
library:** the `Ring(topic, command)` method in
`lwcommandport/__init__.py`, under Python 3, did:
```python
command = "{{0}} {1}".format(topic, command)
```
Doubled braces in `str.format` escape to a literal brace rather than
substituting - so this produces the literal string `"{0} ping"` instead
of `"{MCP} ping"`. Confirmed live via the debug log showing
`raw='{0} ping'`. Fixed to `"{{{0}}} {1}".format(topic, command)` (three
braces before, two after - correctly escapes to one literal `{`/`}`
around the substituted topic).

Also fixed two earlier real bugs found via live tracebacks:
- `lwsdk.LWMessageFuncs().info(text)` actually requires two arguments
  (`info(text, None)`), despite the SDK doc's own example showing one.
- `lwsdk.IMaster.__init__` is called by the factory as `klass(context)`
  (one arg), despite the SDK doc's own example showing
  `__init__(self, context, count)`.
These all suggest the local docs (and the bundled sample client code)
are somewhat out of sync with this LightWave build/Python version - worth
remembering if more of this surfaces.

## Setup for the read path (per fresh Layout session)

1. Utilities → Plugins → Add Plugins → `lw_mcp_ring.py`.
2. Utilities → Master Plugins → "Add Layout or Scene Master" dropdown →
   select "LW MCP Ring" (shows as "Claude MCP Command Port Ring
   listener") → confirm its "On" checkbox is ticked.
3. Restart the `server.py` MCP process (i.e. restart Claude Desktop) at
   least once after pulling this fix, so it picks up the corrected
   `lwcommandport/__init__.py` - it's imported once at process start and
   caches the old buggy version otherwise. Note: closing/reopening the
   Claude Desktop window is not enough to restart the underlying MCP
   subprocess on Windows - use Task Manager to End Task every "Claude"
   process, then relaunch.

**CONFIRMED LIVE END TO END** via the real `lw_ping` and `lw_get_scene_info`
MCP tools after this restart: `lw_ping` returned `"pong"`, and
`lw_get_scene_info` correctly returned the live scene's actual item list
(`CleanTest1`, `CleanTest2`, `Light`, `Camera`) - both nulls created
earlier in this same session via `lw_create_null`. Full read+write round
trip is proven working, not just theorized.

## Read path, round 2: selection, camera, light (ROADMAP.md item 1)

Added `lw_get_selection`, `lw_get_camera_info`, `lw_get_light_info` -
all confirmed live via the real MCP tools after a server restart. Found
the exact method signatures by writing three small throwaway probe
plug-ins (`lw_mcp_diag.py`, `diag2`, `diag3` - safe to ignore/leave
unloaded, kept only as a record of what was tried) that dumped live
`dir(lwsdk)` results and tested real method calls against the actual
scene, rather than guessing from static docs:

- `LWItemInfo().selected(item)` → 0/1, the reliable selection signal.
  Important: `flags() & LWITEMF_SELECTED` looked plausible from the name
  but is **not** reliable - tested live, returned the same flags value
  (37) for every item regardless of actual selection state.
- `LWCameraInfo`/`LWLightInfo` split into two calling conventions:
  non-animated properties take just the item ID (`resolution(id)`,
  `falloff(id)`, `type(id)`), while animatable ones need a second `time`
  argument (`focalLength(id, time)`, `color(id, time)`, etc.) - confirmed
  working with `time=0.0`.
- `LWLightInfo().color()` returns a `PCore::Vector` SWIG object, not
  JSON-serializable directly - converted via `.x`/`.y`/`.z`.

**Open limitation:** `time=0.0` means these evaluate at scene start, not
LightWave's live playhead position. There's no confirmed way yet to
query the actual current time from Python - fine for non-animated
cameras/lights, wrong for animated ones. See ROADMAP.md.

**Descoped, promoted to their own roadmap items:** item transform
(position/rotation/scale - needs `LWChannelInfo` group/channel
traversal with an unclear iteration-end sentinel) and surface/material
info (needs `SURF_*` constants not yet found via introspection).

## Files

- `lw_enable_command_port.py` — run once inside Layout to turn on the
  Command Port. Working.
- `lw_mcp_ring.py` — the working read-path Master plug-in (LWComRing).
  Must be both loaded (Add Plugins) and activated (Master Plugins panel)
  each fresh Layout session.
- `server.py` — external MCP bridge server. `lw_run_command`,
  `lw_create_null`, `lw_ping`, `lw_get_scene_info`, `lw_get_selection`,
  `lw_get_camera_info`, `lw_get_light_info`, and `modeler_run_command`
  all work now (reads require `lw_mcp_ring.py` to be active - see
  above; `modeler_run_command` requires
  `lw_enable_modeler_command_port.py` to have been run in Modeler).
- `lw_enable_modeler_command_port.py` — run once inside Modeler (via Add
  Plugins, then Utilities > Additional - see above for why it's two
  steps) to turn on Modeler's Command Port on 9736. Working, confirmed
  live.
- `lw_mcp_diag.py`, `lw_mcp_diag2.py`, `lw_mcp_diag3.py`,
  `lw_diag_modeler_cp.py` — throwaway live-introspection probe plug-ins
  used to find the real method signatures/behavior documented above. Not
  needed going forward; safe to ignore or unload.
- `lw_mcp_ring.py`'s `_probe_channels()` / `server.py`'s
  `lw_probe_channels` — temporary, safe (crash-disabled) diagnostic for
  the blocked `LWChannelInfo` transform query above. Returns the
  resolved item ID and an error explaining the block, does not call
  `nextGroup`. To be replaced by a real `lw_get_transform` once a safe
  calling convention is found.
- `lw_mcp_ring.py`'s `_probe_surf_constants()` / `server.py`'s
  `lw_probe_surf` — lists `SURF_*` constants from `lwsdk` (confirmed
  live, ~48 found, e.g. `SURF_COLR`, `SURF_DIFF`, `SURF_REFL`,
  `SURF_TRAN`). Never implicated in any crash. Still needs live
  `LWSurfaceFuncs().byName()`/`getFlt()` probing to become a real
  `lw_get_surface_info` tool (item 1c).
- `lwcommandport/` — NewTek's official Command Port client, copied from
  the LightWave install, with one bug fixed (`Ring()`'s Python 3 topic
  formatting - see above). This is what makes both writes and reads work.
- `lw_mcp_master.py` — superseded Master-class plug-in with the
  LWEVNT_COMMAND attempt for reads. Confirmed dead end, kept for
  reference/history only. Do not load.
- `lw_mcp_query.py` — superseded Generic-class plug-in, the first (also
  unsuccessful) attempt at reads. Kept for reference/history only. Do not
  load.
- `lw_socket_master.py` — superseded very first draft (custom TCP socket
  server, relied on a tick event that doesn't exist). Do not load.
- `lw_diag_items.py`, `lw_diag2.py` — throwaway diagnostics used while
  chasing the hung-session issue above. Not needed going forward.
- `README.md` — setup/testing instructions.

## Setup (current, full read+write path)

1. In Layout: Utilities → Plugins → Add Plugins → `lw_enable_command_port.py`
   (runs once automatically, enables Command Port on 9735 - title bar
   should show `(CP: 9735)`).
2. Utilities → Plugins → Add Plugins → `lw_mcp_ring.py`, then Utilities →
   Master Plugins → "Add Layout or Scene Master" → "LW MCP Ring" (make
   sure "On" is checked).
3. `pip install "mcp[cli]"`.
4. Add `server.py` to Claude Desktop's MCP config, restart Claude Desktop
   (needed at least once after this fix, to pick up the corrected
   `lwcommandport/__init__.py`).
5. Ask Claude to call `lw_create_null`, `lw_run_command`, `lw_ping`, or
   `lw_get_scene_info` - all confirmed working as of this write-up
   (`lw_ping`/`lw_get_scene_info` verification pending the Claude Desktop
   restart in step 4 taking effect - see PLAN.md status above).

## ParentItem argument format (ROADMAP.md item 8, closing the item 7 gap)

Session goal: solve the previously-documented gap where `ParentItem`
via `lw_run_command` did not actually reparent items, confirmed only
readable via the UI-set relationship. Live LightWave 2019.1.5 was
available this session (a real Layout process, both Command Port and
`lw_mcp_ring.py` active), so this was investigated with real
round-trips rather than more static guessing.

**Wrong theories tested and ruled out live, in order:**

1. *Hidden modal requester.* Many LightWave generic commands pop a
   dialog when they can't parse their argument, and a network-invoked
   command can't dismiss it. Ruled out: took a screenshot of Layout
   immediately after sending `ParentItem` - no dialog, just the normal
   viewport, status bar showing `Current Item: ChildTest`, `Sel: 1`.
2. *Needs a UI redraw to flush a queued scene-graph rebuild.* A first
   test appeared to succeed - after the user opened Scene Editor,
   `lw_get_hierarchy` showed `ChildTest.parent: "ParentTest"` where it
   had shown `null` moments before. Tested the theory directly: created
   a second pair (`ParentTest2`/`ChildTest2`), sent the same
   `SelectItem`/`ParentItem` sequence, then asked the user to click once
   in the viewport (a trivial redraw trigger) and re-checked. Still
   `null`. Ruled out.
3. *Just needs more elapsed real time.* Polled `lw_get_hierarchy`
   repeatedly across a couple of minutes with no further action. Still
   `null` for the second pair throughout. Ruled out.
4. *The apparent first "success" was real.* Directly contradicted by
   the user: "it didn't work. I parented the items myself." - meaning
   the Scene Editor screenshot that appeared to show `ChildTest` nested
   under `ParentTest` was the user manually dragging it while looking at
   that panel, not the network command taking effect. The untouched
   second pair staying `null` the whole time is independent confirmation
   of the same thing. Real lesson: a single apparent success right after
   a UI interaction, with no isolated control case, is not evidence -
   this cost real time before the fresh, untouched `ParentTest2`/
   `ChildTest2` pair caught it.

**Root cause, found via Utilities > Commands > Cmd History:** this
panel logs the literal native command LightWave runs for any action,
UI-driven or network-driven. Asked the user to open it, then manually
reparent a pair via Motion Options (the same manual method already
proven to work, used originally to verify the read side). The log
showed:

```
ParentItem 10000000
SelectItem 10000000
```

A plain numeric ID, not a name. Meanwhile this connector's own failed
network attempts (`SelectItem Camera` then `TargetItem ChildTest`,
testing whether the failure was `ParentItem`-specific or affected the
whole "reference another item" command family) logged as:

```
TargetItem 0
```

Confirming `TargetItem` fails identically to `ParentItem` - not a
`ParentItem`-specific bug, but a shared argument-parsing convention
across this command family (`ParentItem`, `TargetItem`, `GoalItem`,
`PoleItem` all share the same `(itemid)` signature in
`lwcommandport/layout/__init__.py`). When given a name string these
commands can't parse as a numeric ID, they silently coerce the argument
to `0` - a bogus/no-op ID - rather than erroring, resolving by name, or
opening a dialog. `SelectItem` is the one exception: its own Cmd
History entries (`SelectItem 10000003` for a name-based call) prove its
command handler really does resolve names to IDs internally, unlike
this family. This inconsistency across LightWave's native commands
appears to be a genuine, longstanding NewTek API quirk, not something
introduced by this connector.

The IDs are sequential per item, assigned in creation order starting
at `10000000` for the Object category in this scene: `ParentTest` was
the first Null created this session and got `10000000`; `ParentTest2`
(the 3rd Null created) got `10000002`; `ChildTest2` (4th) got
`10000003`.

**Getting the numeric ID from Python:** the missing piece had been
sitting unused in this project since early on. `_mcp_diag_response.json`
- the output of `lw_mcp_ring.py`'s `_introspect()` diagnostic from a
much earlier session - lists module-level `lwsdk` helper functions
never connected to this problem until now: `find_scene_item_by_name`,
`itemid_to_str`, `str_to_itemid`. `_find_item(name)` (already existing
in `lw_mcp_ring.py`, used by every read query) already returns the
opaque `NodeID` handle for a name; `lwsdk.itemid_to_str()` converts
that handle into exactly the numeric string Cmd History showed
(confirmed live: `lw_get_item_id("ParentTest3")` returned `"10000004"`,
matching the expected sequential position for the 5th Null created).

**Fix, confirmed live end-to-end:** added a `get_item_id` query to
`lw_mcp_ring.py` (wraps `_find_item` + `itemid_to_str`), exposed as
`lw_get_item_id(name)` in `server.py`, plus `lw_set_parent(child,
parent)` wrapping the full corrected sequence (resolve parent's numeric
ID via the read path, `SelectItem(child)` by name since that's proven
to work, `ParentItem(id)`). Tested against a completely fresh,
untouched pair (`ParentTest3`/`ChildTest3`) specifically to avoid
repeating mistake #4 above - `lw_get_hierarchy` afterward correctly
showed `{"name": "ChildTest3", "parent": "ParentTest3", ...}`.

**Not yet wrapped in their own tools, but fixed by the same mechanism:**
`TargetItem`, `GoalItem`, `PoleItem` share the identical root cause and
argument convention. `lw_get_item_id` already produces the correct
argument for any of them via `lw_run_command` (e.g. `lw_run_command
"TargetItem" [lw_get_item_id result]`); a dedicated wrapper analogous
to `lw_set_parent` is a quick follow-up if IK rigging through this
connector is ever needed, not attempted this session since it wasn't
the reported gap.

## Second finding: SelectItem(name) isn't reliable for Camera/Light either (follow-up session)

Wrapped `TargetItem`/`GoalItem`/`PoleItem` as `lw_set_target`/
`lw_set_goal`/`lw_set_pole`, reusing `lw_set_parent`'s shape (resolve
the reference's numeric ID, `SelectItem(item)` by name, send
`command(id)`). Live-tested `lw_set_target(item="Camera",
target="ChildTest")` against real LightWave - it silently applied the
target to `ChildTest3` (an unrelated Null that happened to be the
already-current Object) instead of Camera. Confirmed via
`lw_get_selection` this wasn't a timing issue (waited, re-checked,
`SelectItem("Camera")` provably changed nothing observable).

Root cause, again found via Cmd History (select Camera in Layout,
Motion Options, set Target Item to ChildTest manually):

```
EditCameras 30000000
SelectItem 30000000
MotionOptions
TargetItem 10000001
```

The real working sequence selects the Camera by its own **numeric ID**
(`30000000`), not by name. So `SelectItem(name)`'s internal name
resolution - which does work reliably for Objects (confirmed
repeatedly, e.g. `SelectItem ChildTest2` logged as `SelectItem
10000003`) - is not reliable for Camera/Light. This also revealed each
item-type category has its own numeric ID range: Objects start at
`10000000`, Lights at `20000000`, Cameras at `30000000` (confirmed:
`lw_get_item_id("Camera")` returned `"30000000"`, `lw_get_item_id`
against the scene's one Light returned `"20000000"`).

**Fix:** `_set_reference_item()` in `server.py` now resolves BOTH the
`item` and the `reference` to numeric IDs before sending anything -
`SelectItem(item_id)`, not `SelectItem(item_name)`. Never rely on
SelectItem's name resolution for this command family again, even
though it happens to work for Objects; resolving both sides uniformly
is simpler than tracking which categories are "safe" by name.
Confirmed live after the fix: `lw_set_target("Camera", "ChildTest")`
correctly showed `Camera.target: "ChildTest"` via `lw_get_hierarchy`,
and `lw_set_target("Light", "ParentTest4")` correctly showed
`Light.target: "ParentTest4"`. Re-verified `lw_set_parent` still works
after the change (no regression) on a fresh pair, `ParentTest4`/
`ChildTest4`.

Process note: this fix needed two Claude Desktop restarts to verify -
the first restart left a stale `server.py` process still running
(confirmed via `tasklist`/`Get-CimInstance Win32_Process`, two
processes with the same command line, one clearly older), meaning the
live connection may have still been talking to the pre-fix code. A
fully-quit-and-reopened restart (both processes freshly spawned
seconds apart) was needed before the new tool definitions actually
took effect. Worth checking process list rather than assuming a
restart worked if a just-fixed tool still shows the old behavior.

## lw_set_goal/lw_set_pole live verification (closing the last untested tool)

Expected this to need setting up a real IK chain (bones, or at least a
proper Full-Body IK setup) to test meaningfully. Turned out not to:
`goal()`/`pole()` are generic per-item properties in the SDK -
`lw_get_hierarchy` has queried them for every item type since
ROADMAP.md item 7, regardless of whether the item is actually part of
an active IK chain. So both were tested directly against a plain Null
already in the scene (`ChildTest3`, which by this point already had a
parent and a target set from earlier testing):

- `lw_set_goal("ChildTest3", "ParentTest2")` -> `lw_get_hierarchy`
  correctly showed `"goal": "ParentTest2"`.
- `lw_set_pole("ChildTest3", "ParentTest")` -> `lw_get_hierarchy`
  correctly showed `"pole": "ParentTest"`, alongside the still-correct
  `parent`/`target`/`goal` from earlier - all four relationship types
  set correctly on one item at once, a good comprehensive confirmation
  that the fix generalizes across the whole command family rather than
  being coincidentally right for `ParentItem`/`TargetItem` alone.

No further work needed here - all four `lw_set_*` tools are now fully
live-confirmed.
