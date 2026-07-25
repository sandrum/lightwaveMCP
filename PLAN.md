# Claude ↔ LightWave 2019 MCP connector — build plan

## Current status (tested live against a running Layout 2019.1.5)

**Writes: working, verified.** `lw.AddNull("TestFromMCP")`, sent from an
external Python process over UDP to LightWave's Command Port, produced a
real Null item in the live scene - confirmed visually via screenshot.
`lw_run_command` in `server.py` generalizes this to any of the ~800 native
commands in the bundled `lwcommandport` client.

**Reads: not working yet.** Two approaches were tried and both ruled out
by direct testing, not just reasoning from docs:

1. Registered Generic-class plug-in (`lw_mcp_query.py`), invoked by name
   via `CommandInput LW_MCP_Query ping`. Result every time: `Unknown
   command: "LW_MCP_Query"`. LightWave's command resolver only recognizes
   native/compiled commands (like AddNull) - Python `IGeneric` plug-ins
   aren't added to that namespace no matter what `ServerTagInfo` tags are
   set (tried USERNAME alone, then USERNAME+BUTTONNAME+MENU).
2. Master-class plug-in (`lw_mcp_master.py`) listening for
   `LWEVNT_COMMAND`, per the exact pattern in the SDK doc's own
   `master.html` example. Added debug logging of every event the plug-in
   ever receives. Confirmed via the log:
   - The plug-in only actually starts receiving events once activated in
     the **Master Plugins** panel (Utilities → Master Plugins) - simply
     loading it via Add Plugins is not enough, and this panel resets on
     every Layout restart (needs re-adding each session).
   - Its `event()` fires for ordinary UI actions (opening a dropdown,
     selecting a menu item) with codes 290, 1, 309, 256.
   - It does **not** fire at all for Command Port traffic - tested with
     both an unresolved string (`MCP_QUERY:ping`) and a genuinely valid,
     successful command (`AddNull`). Neither produced any event.
   - There is no idle/tick event exposed to Python either (confirmed
     earlier by grepping the entire local SDK doc set for
     `LWMASTF_*`/`LWEVNT_*` constants - only 5 exist, none idle-related).

Also fixed two real bugs found via live tracebacks along the way:
- `lwsdk.LWMessageFuncs().info(text)` actually requires two arguments
  (`info(text, None)`), despite the SDK doc's own example showing one.
- `lwsdk.IMaster.__init__` is called by the factory as `klass(context)`
  (one arg), despite the SDK doc's own example showing
  `__init__(self, context, count)`.
Both suggest the local docs (and possibly the online ones, unreachable
this session) are somewhat out of sync with this LightWave build - worth
remembering if more of this surfaces.

## What's left for reads (not attempted yet, in rough order of promise)

- **Scene-file export + external parse.** Native commands are the only
  thing confirmed to work reliably. `SaveSceneAs <path>` is a native
  command; if it actually writes a `.lws` file (started testing this,
  didn't get a confirmed result before pausing), `server.py` could parse
  that plain-text file directly for scene state instead of needing any
  custom read plug-in at all. Worth finishing this check first - it sidesteps
  the entire plug-in/event problem.
- **LScript instead of Python** for the notification hook - LScript is
  the older, more mature scripting path in LightWave and may have working
  equivalents where the Python bindings are incomplete/undocumented.
- **A compiled C/C++ plug-in** using the real SDK could register a true
  named command (the class native commands like AddNull actually use)
  that Python's exposed classes don't have access to. Confirmed via the
  docs' own Handler Interfaces list: only Master, Generic, CommandSequence
  (Modeler-only), and various I/O handler classes are exposed to Python -
  no plain "Command" class.

## Files

- `lw_enable_command_port.py` — run once inside Layout to turn on the
  Command Port. Working.
- `server.py` — external MCP bridge server. `lw_run_command` and
  `lw_create_null` work; `lw_ping`/`lw_get_scene_info` do not yet.
- `lwcommandport/` — NewTek's official Command Port client, copied from
  the LightWave install. Working, this is what makes writes work.
- `lw_mcp_master.py` — Master-class plug-in with the LWEVNT_COMMAND
  attempt for reads. Loads and runs without error, but its event handler
  never fires for Command Port traffic (see above) - not currently useful
  but left in place with debug logging for whoever picks this up next.
- `lw_mcp_query.py` — Generic-class plug-in, the first (also unsuccessful)
  attempt at reads. Kept for reference/history.
- `lw_socket_master.py` — superseded very first draft (custom TCP socket
  server, relied on a tick event that doesn't exist). Do not load.
- `README.md` — setup/testing instructions.

## Setup (for what currently works)

1. In Layout: Utilities → Plugins → Add Plugins → `lw_enable_command_port.py`
   (runs once automatically, enables Command Port on 9735 - title bar
   should show `(CP: 9735)`).
2. `pip install "mcp[cli]"`.
3. Add `server.py` to Claude Desktop's MCP config, restart Claude Desktop.
4. Ask Claude to call `lw_create_null` or `lw_run_command` - these work.
   `lw_ping`/`lw_get_scene_info` will time out until the read path above
   gets solved.
