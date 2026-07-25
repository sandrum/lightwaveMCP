# Claude ↔ LightWave 2019 MCP connector — build plan

## Architecture (current, v2)

Pivoted away from a hand-rolled socket server inside a Master plug-in
(`lw_socket_master.py`, superseded) to LightWave 2019's own built-in
**Command Port**, after reading the actual SDK docs and source shipped
with this LightWave install:

- `sdk/lwpython2019.1.5.zip` — full local Python SDK docs (the online
  docs site and Chrome were both unreachable earlier in this session;
  turns out the same docs ship with the product).
- `bin/lwsdk/pris/layout/cs.py` — the internal convenience layer LightWave
  itself uses to issue commands (confirms `lwsdk.command("AddNull %s" %
  name)` etc.).
- `support/python/lwcommandport/` — NewTek's own external Python client
  for the Command Port, meant to be run outside LightWave. Copied into
  this project folder.

Why this is better than the original plan: no guessing at an
undocumented "tick" event, no custom threading/queueing inside the
plug-in, no thread-safety risk. LightWave's own listener already handles
main-thread synchronization.

Remaining asymmetry: the Command Port is one-way (UDP, fire-and-forget).
Writes (create/modify) work directly through it. Reads need a small
plug-in (`lw_mcp_query.py`) that LightWave runs on request and that
writes its answer to a JSON file `server.py` polls.

## Status by phase

1. **Access** — done. Computer-use access to Layout, Modeler, File
   Explorer, Notepad. File access to the LightWave install folder and
   the project folder.
2. **Verify the real API** — done. Confirmed against local docs/source:
   - `lwsdk.LWCommandPort().enable(port)` turns on the Command Port.
   - `lwcommandport.layout.Layout(address=, port=)` is the official
     external client; `.AddNull(name)` etc. are real, verified methods.
   - `lwsdk.GenericAccess()` / `ga.commandArguments()` / single-shot
     Generic plug-ins are the documented pattern for simple scripts.
   - `lwsdk.LWSceneInfo()` / `lwsdk.LWItemInfo().first/next/name()` are
     the real scene/item enumeration calls.
   - Confirmed the embedded interpreter is Python 2.7 (not 3) - plug-in
     code must be 2.7-compatible. `server.py` runs under the system
     Python (3.6, already installed) instead, since it's an external
     process.
3. **Files rewritten** for the new architecture:
   - `lw_enable_command_port.py` (single-shot, run once)
   - `lw_mcp_query.py` (registered plug-in, answers reads)
   - `lwcommandport/` (copied official client library)
   - `server.py` (rewritten to use the Command Port)
   All syntax-checked with `py_compile`. Not yet run inside a live Layout.

## Next steps

4. **Load and debug inside LightWave** (not started)
   - Load `lw_enable_command_port.py`, run it once, confirm the
     confirmation dialog appears.
   - Load `lw_mcp_query.py`, confirm no error dialog on load.
5. **Prove the round trip**
   - `pip install "mcp[cli]"` if not already present.
   - Run `server.py`'s tools directly (or via a quick standalone Python
     snippet using `lwcommandport.layout.Layout` + a poll of
     `_mcp_response.json`) to confirm `ping` → `"pong"`.
6. **Wire up Claude Desktop**
   - Add `server.py` to `claude_desktop_config.json`, restart Claude
     Desktop (user's own action - restarting the app isn't something
     this session can trigger), test `lw_ping` / `lw_get_scene_info` /
     `lw_create_null` end-to-end from a Claude conversation.
7. **Expand and verify**
   - Add more commands (transforms, surfaces, delete) the same way:
     writes via `lwcommandport.layout.Layout` methods directly, reads via
     `lw_mcp_query.py` + response file.
   - Final pass: a handful of real prompts end-to-end, confirm no
     regressions, document remaining gaps.

## Files

- `lw_enable_command_port.py` — run once inside Layout.
- `lw_mcp_query.py` — registered plug-in, answers read queries.
- `lwcommandport/` — NewTek's official Command Port client, copied in.
- `server.py` — external MCP bridge server.
- `README.md` — setup/testing instructions.
- `lw_socket_master.py` — superseded first draft; do not load.
