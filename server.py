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

- READS now work too, via LWComRing (not LWEVNT_COMMAND - that was a
  confirmed dead end, see PLAN.md). The working mechanism, found in
  NewTek's own bundled sample
  (support/plugins/scripts/Python/Layout/Master/command_port_test.py):
  a Master plug-in calls lwsdk.LWComRing().ringAttach(
  lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event) and receives Command
  Port traffic wrapped as "{Topic} message". The client-side Ring(topic,
  command) method that formats that wrapper already existed in NewTek's
  bundled lwcommandport client - but it has a real bug under Python 3:
  `"{{0}} {1}".format(topic, command)` produces the literal string
  "{0} message" instead of "{MCP} message" (doubled braces escape to a
  literal brace instead of substituting). Confirmed live via
  _mcp_ring_debug.log. Fixed in lwcommandport/__init__.py.

  See lw_mcp_ring.py for the Master plug-in that must be loaded (Add
  Plugins) AND activated (Master Plugins panel) once per Layout session,
  alongside lw_enable_command_port.py.

Requires: pip install "mcp[cli]"
"""

import json
import os
import time

from mcp.server.fastmcp import FastMCP

from lwcommandport.layout import Layout
from lwcommandport.modeler import Modeler

HOST = "localhost"
PORT = 9735  # must match lw_enable_command_port.py
MODELER_PORT = 9736  # must match lw_enable_modeler_command_port.py

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_response.json")

mcp = FastMCP("lightwave")


def _layout():
    return Layout(address=HOST, port=PORT)


def _modeler():
    return Modeler(address=HOST, port=MODELER_PORT)


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
def modeler_run_command(command: str, args: list = None) -> str:
    """Send any native LightWave Modeler command by name over Modeler's
    Command Port (a different mechanism than Layout's - see
    lw_enable_modeler_command_port.py). E.g. command="new" for New
    Object, command="boolean" for Boolean CSG, command="load",
    args=["path/to/file.lwo"] to load an object. See the Modeler class
    in lwcommandport/modeler/__init__.py for the full wrapped command
    list (mesh cleanup, extrude/clone/array tools, file ops). One-way,
    no confirmation LightWave accepted it - requires
    lw_enable_modeler_command_port.py to have been run in the current
    Modeler session first."""
    m = _modeler()
    method = getattr(m, command, None)
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


RING_TOPIC = "MCP"


def _query(command, arg="", timeout=5.0):
    """Read path over LWComRing. Requires lw_mcp_ring.py to be loaded AND
    activated (Utilities > Master Plugins) in the current Layout session -
    see lw_mcp_ring.py's docstring for the two-step setup. Sends
    "{MCP} <command> <arg>" via the (bug-fixed) Ring() method, then polls
    _mcp_response.json for the plug-in's answer."""
    before_mtime = os.path.getmtime(RESPONSE_PATH) if os.path.exists(RESPONSE_PATH) else None

    cmd_string = ("%s %s" % (command, arg)).strip()
    _layout().Ring(RING_TOPIC, cmd_string)

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

    return {"error": "timed out - is lw_mcp_ring.py loaded AND activated in Master Plugins this session?"}


@mcp.tool()
def lw_ping() -> str:
    """Round-trip check that the read path (LWComRing) is alive. Returns
    "pong" if lw_mcp_ring.py is loaded and activated in the current Layout
    session, otherwise a timeout error explaining the two-step setup."""
    resp = _query("ping")
    return resp.get("result") or resp.get("error", "no response")


@mcp.tool()
def lw_get_scene_info() -> str:
    """Get the current scene name, filename, and item list (objects,
    lights, cameras) from the live LightWave scene via the LWComRing read
    path (see lw_mcp_ring.py)."""
    return json.dumps(_query("get_scene_info"))


@mcp.tool()
def lw_get_selection() -> str:
    """Get every item's name/type and whether it's currently selected in
    Layout, plus a convenience list of just the selected names. Confirmed
    live against LWItemInfo().selected() - note that flags() &
    LWITEMF_SELECTED does NOT reliably reflect selection state despite
    the name (tested, returned the same value for every item)."""
    return json.dumps(_query("get_selection"))


@mcp.tool()
def lw_get_camera_info(name: str = "Camera") -> str:
    """Get a camera's resolution, focal length, f-stop, field of view,
    and zoom factor. Note: animatable values (focal length, f-stop, fov,
    zoom) are evaluated at time=0.0, not the live playhead position -
    querying the actual current time isn't solved yet (see ROADMAP.md).
    Fine for cameras that aren't animated."""
    return json.dumps(_query("get_camera_info", name))


@mcp.tool()
def lw_get_light_info(name: str = "Light") -> str:
    """Get a light's type, falloff, color (RGB), intensity, and range.
    Same time=0.0 caveat as lw_get_camera_info for the animatable
    values."""
    return json.dumps(_query("get_light_info", name))


@mcp.tool()
def lw_probe_channels(name: str = "TransformTest") -> str:
    """DIAGNOSTIC, temporary: probes lwsdk.LWChannelInfo() group/channel
    traversal against the named item, routed through the proven
    lw_mcp_ring.py listener (the dedicated diag4/5/6 Master plugins never
    received ring_event callbacks at all - root-caused to a stale/GC'd
    instance, see PLAN.md). Will be replaced by lw_get_transform once the
    real API shape is known."""
    return json.dumps(_query("probe_channels", name))


@mcp.tool()
def lw_probe_surf() -> str:
    """DIAGNOSTIC, temporary: lists SURF_* constants from lwsdk, routed
    through lw_mcp_ring.py. Will be replaced by lw_get_surface_info."""
    return json.dumps(_query("probe_surf"))


if __name__ == "__main__":
    mcp.run()
