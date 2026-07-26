# Claude ↔ LightWave 2019 MCP connector — build plan

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

## Files

- `lw_enable_command_port.py` — run once inside Layout to turn on the
  Command Port. Working.
- `lw_mcp_ring.py` — the working read-path Master plug-in (LWComRing).
  Must be both loaded (Add Plugins) and activated (Master Plugins panel)
  each fresh Layout session.
- `server.py` — external MCP bridge server. `lw_run_command`,
  `lw_create_null`, `lw_ping`, and `lw_get_scene_info` all work now
  (reads require `lw_mcp_ring.py` to be active - see above).
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
