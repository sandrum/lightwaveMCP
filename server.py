"""
server.py

MCP bridge between Claude and LightWave Layout, built on LightWave's
official Command Port.

VERIFIED STATUS (tested live against LightWave 2019.1.5, see PLAN.md for
the full log of what was tried):

- WRITES work end to end. lw.AddNull("TestFromMCP") sent from this
  machine's Python over UDP to Layout's Command Port produced a real Null
  item in the live scene, confirmed visually. Any of the ~800 native
  Layout commands exposed by the bundled `lwcommandport` client (copied
  here from support/python/lwcommandport in the LightWave install) should
  work the same way via lw_run_command below.
- READS do not work yet. The Command Port is one-way (UDP, fire and
  forget) with no response channel, so getting data back out requires
  LightWave itself to run some code and write a file. Two approaches were
  tried and both were ruled out empirically, not just in theory:
    1. A registered Generic-class plug-in invoked by name via
       `CommandInput <PluginName>` - LightWave's command resolver only
       recognizes native/compiled commands, not Python Generic plug-ins.
       Every attempt produced "Unknown command: <name>".
    2. A Master-class plug-in listening for LWEVNT_COMMAND (per the SDK
       doc's own master.html example) - confirmed via a debug log that
       this event never fires for ANY Command Port traffic, including
       commands that succeed (AddNull) and commands that don't resolve.
  lw_get_scene_info and lw_ping are left in below as documented stubs so
  the shape of the fix is obvious, but they will time out / error until
  a working read channel is found (candidates: LScript instead of Python
  for the notification hook, a compiled C plug-in registering a real
  named command, or parsing a scene file written via a native save
  command).

Requires: pip install "mcp[cli]"
"""

import json
import os
import time

from mcp.server.fastmcp import FastMCP

from lwcommandport.layout import Layout

HOST = "localhost"
PORT = 9735  # must match lw_enable_command_port.py

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_response.json")

mcp = FastMCP("lightwave")


def _layout():
    return Layout(address=HOST, port=PORT)


@mcp.tool()
def lw_run_command(command: str, args: list = None) -> str:
    """Send any native LightWave Layout command by name over the Command
    Port (e.g. command="AddLight", args=["Distant"]). This is a direct,
    one-way passthrough to LightWave's command language - the same
    commands available via hotkeys/menus/LScript. Confirmed working with
    AddNull; most of the ~800 commands in lwcommandport/layout/__init__.py
    should behave the same way. There is no response - this only tells
    you the command was sent, not whether LightWave accepted it."""
    lw = _layout()
    method = getattr(lw, command, None)
    if method is None:
        return json.dumps({"error": "no such command: %s" % command})
    try:
        method(*(args or []))
        return json.dumps({"result": "sent %s %s" % (command, args or [])})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_create_null(name: str = "MCP_Null") -> str:
    """Create a Null item in the current LightWave scene. Verified
    working: this sends AddNull over the Command Port and LightWave
    creates the item immediately."""
    try:
        _layout().AddNull(name)
        return json.dumps({"result": "sent AddNull %s" % name})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def _query(command, arg="", timeout=5.0):
    """NOT CURRENTLY WORKING - see module docstring. Left in place as the
    intended shape of the read path once a working notification mechanism
    is found; will reliably time out for now."""
    before_mtime = os.path.getmtime(RESPONSE_PATH) if os.path.exists(RESPONSE_PATH) else None

    cmd_string = ("LW_MCP_Query %s %s" % (command, arg)).strip()
    _layout().CommandInput(cmd_string)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(RESPONSE_PATH):
            mtime = os.path.getmtime(RESPONSE_PATH)
            if before_mtime is None or mtime > before_mtime:
                try:
                    with open(RESPONSE_PATH) as f:
                        return json.load(f)
                except (ValueError, OSError):
                    pass
        time.sleep(0.1)

    return {"error": "timed out - read path is not working yet, see PLAN.md"}


@mcp.tool()
def lw_ping() -> str:
    """NOT WORKING YET - always times out. See module docstring / PLAN.md
    for what's been ruled out and what to try next."""
    resp = _query("ping")
    return resp.get("result") or resp.get("error", "no response")


@mcp.tool()
def lw_get_scene_info() -> str:
    """NOT WORKING YET - always times out. See module docstring / PLAN.md
    for what's been ruled out and what to try next."""
    return json.dumps(_query("get_scene_info"))


if __name__ == "__main__":
    mcp.run()
