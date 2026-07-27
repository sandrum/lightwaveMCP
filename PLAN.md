# Claude ↔ LightWave 2019 MCP connector — build plan

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
