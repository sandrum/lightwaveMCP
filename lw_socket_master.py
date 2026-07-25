"""
lw_socket_master.py

LightWave 2019 Master-class Python plugin. Opens a local TCP socket server
so an external MCP bridge process (server.py, in this same folder) can send
scene-editing commands to LightWave Layout from Claude.

ARCHITECTURE
------------
- A background thread (_run_server / _handle_client) accepts TCP connections
  and reads one JSON command per line, e.g. {"command": "ping", "params": {}}
- LightWave's SDK is not thread-safe, so scene edits can't happen on that
  background thread. Instead each incoming command is queued
  (_command_queue) and executed on LightWave's *main* thread, from the
  Master plugin's periodic "tick" event (see SocketMaster.event below).
- The background thread blocks (with a timeout) waiting for the main thread
  to finish the job, then writes the JSON result back over the socket.

This mirrors how blender-mcp bridges Blender (bpy.app.timers on the main
thread + a socket thread) to an external MCP server.

VERIFY BEFORE USE
------------------
I could not reach the live LightWave 2019 Python SDK docs in this session
(static.lightwave3d.com and Chrome were both unreachable), so the pieces
below that are LightWave-specific are best-effort based on the general
Python-plugin conventions LightWave has used since v11 (IMaster /
MasterFactory, ServerTagInfo/ServerRecord registration). Anything marked
VERIFY should be checked against:
  1. The SDK docs installed alongside LightWave 2019 itself (look for an
     "SDK" folder near the LightWave install, with a python/ subfolder of
     docs and sample .py plugins).
  2. A working Master-class sample plugin, to confirm the exact tick/idle
     event constant name and the registration boilerplate.
The pure networking/threading code (sockets, queue, threading) is standard
Python and does not need verification - that part will work as-is.
"""

import json
import queue
import socket
import threading

import lwsdk

HOST = "127.0.0.1"
PORT = 9799  # change if this collides with something else on your machine

_command_queue = queue.Queue()
_server_started = False


def _handle_client(conn, addr):
    """Background thread: read newline-delimited JSON commands, hand each
    one to the main thread via _command_queue, wait for the result, and
    write the JSON response back."""
    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    request = json.loads(line.decode("utf-8"))
                except ValueError as exc:
                    conn.sendall((json.dumps({"error": f"bad json: {exc}"}) + "\n").encode("utf-8"))
                    continue

                done = threading.Event()
                result_box = {}

                def _job(request=request, done=done, result_box=result_box):
                    try:
                        result_box["result"] = _execute_command(request)
                    except Exception as exc:  # noqa: BLE001
                        result_box["error"] = str(exc)
                    finally:
                        done.set()

                _command_queue.put(_job)
                done.wait(timeout=10)

                if "error" in result_box:
                    payload = {"error": result_box["error"]}
                elif done.is_set():
                    payload = {"result": result_box.get("result")}
                else:
                    payload = {"error": "timed out waiting for LightWave's main thread"}

                conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    finally:
        conn.close()


def _run_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=_handle_client, args=(conn, addr), daemon=True).start()


def _execute_command(request):
    """Runs on LightWave's main thread. Dispatch table for supported
    commands - add new ones here as the connector grows."""
    cmd = request.get("command")
    params = request.get("params", {})

    if cmd == "ping":
        return "pong"

    if cmd == "get_scene_info":
        return _get_scene_info()

    if cmd == "create_null":
        return _create_null(params.get("name", "MCP_Null"))

    raise ValueError(f"unknown command: {cmd}")


def _get_scene_info():
    # VERIFY: wire up real scene/item enumeration here. LightWave's Python
    # SDK exposes this through global service classes documented under
    # "Scene Info" / "Item Info" in the SDK reference - check your local
    # docs for the exact class and method names for LW 2019, then replace
    # this stub.
    raise NotImplementedError("TODO: call the lwsdk scene-info service here")


def _create_null(name):
    # VERIFY: item creation from Python is normally done by invoking
    # LightWave's internal command language (the same commands LScript's
    # LWM.command() would call) rather than a direct SDK "create" function.
    # Check the SDK's command-sequence / generic command execution docs and
    # your local sample plugins for the right calling convention, then
    # replace this stub with the real call, e.g. creating an item named
    # `name` and returning its item ID.
    raise NotImplementedError("TODO: call the lwsdk item-creation command here")


class SocketMaster(lwsdk.IMaster):
    """Master-class plugin: LightWave instantiates this once and keeps it
    alive for the session, delivering periodic events through .event(). We
    use that as our main-thread hook to drain _command_queue."""

    def __init__(self, context, data):
        lwsdk.IMaster.__init__(self)
        global _server_started
        if not _server_started:
            threading.Thread(target=_run_server, daemon=True).start()
            _server_started = True

    def event(self, ev, evdata):
        # VERIFY: confirm the idle/tick event constant name for LW 2019 -
        # this assumes lwsdk.LWMASTER_TICK exists; if your SDK uses a
        # different name, swap it in below (getattr() just avoids an
        # AttributeError crash if the guess is wrong, at the cost of the
        # queue never draining until you fix the name).
        if ev == getattr(lwsdk, "LWMASTER_TICK", None):
            while not _command_queue.empty():
                job = _command_queue.get_nowait()
                job()
        return lwsdk.AFUNC_OK


ServerName = "MCP_Socket_Master"

ServerTagInfo = [
    (ServerName, lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory(ServerName, SocketMaster): ServerTagInfo,
}
