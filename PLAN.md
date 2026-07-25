# Claude ↔ LightWave 2019 MCP connector — build plan

## Phase 1 — Access
1. Computer-use access to LightWave, File Explorer, Notepad (to load/test the
   plugin and read SDK doc/sample files on screen).
2. Project folder access (done — `LightwaveMCP`).

## Phase 2 — Verify the real API
3. Read the local LightWave 2019 SDK docs/sample Master-plugin code to
   confirm the exact `lwsdk` names currently stubbed in `lw_socket_master.py`:
   - the tick/idle event constant used in `SocketMaster.event()`
   - the scene/item enumeration calls for `_get_scene_info()`
   - the item-creation call/command for `_create_null()`
4. Update `lw_socket_master.py` with the verified calls.

## Phase 3 — Load and debug inside LightWave
5. Open LightWave, load the plugin via Utilities → Plugins → Edit/Add Plugins.
6. Check Layout's error console for import tracebacks; fix, reload, repeat
   until it loads cleanly.

## Phase 4 — Prove the transport layer
7. Confirm the socket server accepts connections. This is the one step that
   needs you directly — I can't execute code on your machine, only drive its
   GUI. I'll hand you a short copy-paste Python snippet to run once in a
   terminal; it should print back `"pong"`.

## Phase 5 — Wire up Claude
8. `pip install "mcp[cli]"`.
9. Add `server.py` to Claude Desktop's MCP config; restart Claude Desktop
   (your action).
10. Test `lw_ping` / `lw_get_scene_info` / `lw_create_null` end-to-end from a
    Claude conversation.

## Phase 6 — Expand and verify
11. Add more commands one at a time (transforms, surfaces, delete), each
    verified the same load-test-confirm loop.
12. Final pass: run a handful of real prompts end-to-end, confirm no
    regressions, document remaining gaps.

## Files
- `lw_socket_master.py` — LightWave Master-class plugin (socket server, runs
  inside Layout).
- `server.py` — standalone MCP bridge server (runs outside LightWave; Claude
  Desktop launches it).
- `README.md` — setup/testing instructions.
