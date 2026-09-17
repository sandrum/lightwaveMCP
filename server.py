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
MODELER_RESPONSE_PATH = os.path.join(_HERE, "_mcp_modeler_response.json")

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


MODELER_QUERY_COMMAND = "LW_MCP_ModelerQuery"


def _modeler_query(command, arg="", timeout=5.0):
    """DOES NOT WORK OVER THE NETWORK - kept for the record and in case a
    future in-process invocation path is found. ROADMAP.md item 5:
    confirmed live (three ways, including against NewTek's own bundled
    sample plug-in, not just this project's code) that Modeler's network
    Command Port only reaches native/compiled commands, not
    Python-registered CommandSequence commands like
    lw_mcp_modeler_query.py's LW_MCP_ModelerQuery - unlike Layout, there
    is no LWComRing-style escape hatch for Modeler. This function will
    reliably time out. See PLAN.md "Modeler read path" for the full
    investigation. The plug-in itself works correctly when invoked from
    inside Modeler (e.g. Utilities > Additional menu) - it's specifically
    the external network call that never reaches it."""
    before_mtime = os.path.getmtime(MODELER_RESPONSE_PATH) if os.path.exists(MODELER_RESPONSE_PATH) else None

    cmd_string = ("%s %s %s" % (MODELER_QUERY_COMMAND, command, arg)).strip()
    m = _modeler()
    m._send_command(cmd_string)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(MODELER_RESPONSE_PATH):
            mtime = os.path.getmtime(MODELER_RESPONSE_PATH)
            if before_mtime is None or mtime > before_mtime:
                try:
                    with open(MODELER_RESPONSE_PATH) as f:
                        return json.load(f)
                except (ValueError, OSError):
                    pass
        time.sleep(0.1)

    return {"error": "timed out - is lw_mcp_modeler_query.py loaded (Add Plugins) in Modeler this session?"}


@mcp.tool()
def modeler_ping() -> str:
    """WILL ALWAYS TIME OUT - confirmed dead end, see PLAN.md "Modeler
    read path". Modeler's network Command Port doesn't route to
    Python-registered plug-in commands (unlike native ones like "new"),
    and Modeler has no LWComRing-style listener mechanism the way Layout
    does. Kept only for the record / in case a future workaround is
    found - don't spend time retrying this."""
    resp = _modeler_query("ping")
    return resp.get("result") or resp.get("error", "no response")


@mcp.tool()
def modeler_get_object_info() -> str:
    """WILL ALWAYS TIME OUT - see modeler_ping's docstring and PLAN.md
    "Modeler read path". Kept for the record only.

    (Intended behavior, unreachable over the network: point count,
    polygon count, and surface names for the foreground layer of the
    object currently open in Modeler, via lw_mcp_modeler_query.py.)"""
    return json.dumps(_modeler_query("get_object_info"))


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


@mcp.tool()
def lw_set_keyframe(name: str, frame: int, position: list = None, rotation: list = None, scale: list = None) -> str:
    """Create a keyframe for an item at a given frame, optionally setting
    its position/rotation/scale first. Wraps the common by-hand animation
    sequence (ROADMAP.md item 4) - select the item, go to the frame, set
    the transform, create the key - into one call instead of chaining
    4+ separate lw_run_command calls. Any of position/rotation/scale left
    as None (the default) is not touched - the item keeps whatever value
    it currently has at this frame, so you can create a key on just one
    channel type if that's all you want. position and scale are each
    [x, y, z] triples; rotation is [heading, pitch, bank] in degrees,
    matching Layout's UI and command-line convention (confirmed live:
    values entered here appear in the Motion Options panel unchanged -
    note this is a different unit than the read-path's lw_get_transform,
    which reports rotation in radians per the LWItemInfo SDK global).
    Uses the native SelectItem/GoToFrame/Position/Rotation/Scale/CreateKey
    commands - all proven-reachable via lw_run_command already."""
    lw = _layout()
    try:
        lw.SelectItem(name)
        lw.GoToFrame(frame)
        if position is not None:
            lw.Position(*position)
        if rotation is not None:
            lw.Rotation(*rotation)
        if scale is not None:
            lw.Scale(*scale)
        lw.CreateKey(frame)
        return json.dumps({"result": "keyframed %s at frame %d" % (name, frame)})
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
def lw_get_transform(name: str = "TransformTest") -> str:
    """Get an item's position, rotation, and scale from the live scene.
    Uses LWItemInfo().param() - confirmed via NewTek's C SDK docs and
    real-world Python plugin code, NOT the LWChannelInfo/nextGroup path
    that crashed Layout during development (see PLAN.md). Same time=0.0
    caveat as lw_get_camera_info/lw_get_light_info for animated items."""
    return json.dumps(_query("get_transform", name))


@mcp.tool()
def lw_get_surface_info(name: str) -> str:
    """Get a surface/material's color, diffuse, luminosity, specularity,
    glossiness, reflection, transparency, and smoothing by surface name.
    Uses LWSurfaceFuncs(), confirmed via real-world Python plugin code
    for calling conventions - less thoroughly live-tested than other
    tools here (see PLAN.md), so treat unexpected errors as a signal to
    check the debug log rather than retry blindly."""
    return json.dumps(_query("get_surface_info", name))


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


@mcp.tool()
def lw_set_camera_resolution(width: int, height: int) -> str:
    """Set the render resolution (ROADMAP.md item 6 camera setup half).
    Wraps the native FrameSize(width, height) command - this is a
    scene-wide render global in LightWave, not a per-camera setting
    (LightWave only renders through one camera at a time, selected via
    SelectItem), despite the name suggesting otherwise."""
    try:
        _layout().FrameSize(width, height)
        return json.dumps({"result": "sent FrameSize %d %d" % (width, height)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_render_frame(frame: int = None) -> str:
    """Render a single frame (ROADMAP.md item 6). If frame is given,
    goes to that frame first (GoToFrame), then sends RenderFrame - both
    proven-reachable native commands. This call returns immediately once
    the command is sent, same one-way-fire-and-forget limitation as
    every other command here (see lwcommandport/__init__.py's
    _send_command) - it does NOT wait for the render to finish. Poll
    lw_get_render_status() afterward to know when it's actually done;
    see that tool's docstring for the required one-time setup."""
    lw = _layout()
    try:
        if frame is not None:
            lw.GoToFrame(frame)
        lw.RenderFrame()
        return json.dumps({"result": "sent RenderFrame%s" % (" (frame %d)" % frame if frame is not None else "")})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_render_scene() -> str:
    """Render the full configured frame range to disk/animation output
    (native RenderScene command). Same fire-and-forget caveat as
    lw_render_frame - use lw_get_render_status() to track progress and
    completion."""
    try:
        _layout().RenderScene()
        return json.dumps({"result": "sent RenderScene"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_abort_render() -> str:
    """Abort an in-progress render (native AbortRender command)."""
    try:
        _layout().AbortRender()
        return json.dumps({"result": "sent AbortRender"})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_get_render_status() -> str:
    """Get the live render state - whether a render is in progress, the
    resolution, and a frame_count that increments each time the render
    engine opens a new frame buffer (see lw_mcp_render_monitor.py).
    Solves the actual problem in ROADMAP.md item 6: lw_render_frame/
    lw_render_scene are one-way fire-and-forget commands with no
    built-in completion signal, so this reads real callback-driven state
    (IFrameBuffer.open()/close()) over the LWComRing read path instead
    of guessing based on elapsed time.

    Requires a ONE-TIME manual setup step beyond the usual Add Plugins +
    Master Plugins dance: lw_mcp_render_monitor.py must additionally be
    selected as the active Render Display (Render Globals > Render
    Display tab) - LightWave has no networked way to select it, per
    lw_mcp_render_monitor.py's docstring. Before that's done, or before
    any render has been triggered this session, rendering will be null,
    not a real in-progress/done state."""
    return json.dumps(_query("get_render_status"))


@mcp.tool()
def lw_get_item_id(name: str) -> str:
    """Get the plain numeric ID string (e.g. "10000000") LightWave's
    native item-reference commands (ParentItem, TargetItem, GoalItem,
    PoleItem) actually expect as their argument over the Command Port -
    NOT the item's name, despite their docstrings saying "(itemid)" the
    same way SelectItem's does. Root-caused by comparing Cmd History's
    log of a real, working UI-driven reparent (logged as literally
    "ParentItem 10000000") against this connector's failed attempts with
    a name string (logged as "TargetItem 0" - silently coerced to a
    no-op ID, no error, no dialog). SelectItem is the one exception that
    really does resolve names internally. See lw_set_parent for the
    wrapped fix; use this directly only if you need the raw ID for a
    command lw_set_parent doesn't cover yet (TargetItem/GoalItem/
    PoleItem)."""
    return json.dumps(_query("get_item_id", name))


def _resolve_item_id(name):
    """Shared by lw_set_parent/lw_set_target/lw_set_goal/lw_set_pole -
    all four native commands share the same "wants a numeric ID, not a
    name" quirk (see lw_get_item_id's docstring), so they share this
    resolve-then-select-then-send shape too."""
    id_resp = _query("get_item_id", name)
    return id_resp.get("result", {}).get("id"), id_resp


def _set_reference_item(command, item, reference):
    """Common body for lw_set_parent/lw_set_target/lw_set_goal/
    lw_set_pole. Resolves BOTH item and reference to numeric IDs -
    confirmed live that SelectItem(name) only reliably switches the
    "current item" pointer this command family reads for Objects.
    Tested targeting a Camera by name ("SelectItem Camera"): the
    current OBJECT (an unrelated Null) got the target applied instead
    of the Camera. Cmd History of the equivalent manual action (select
    Camera, Motion Options, set Target Item) showed the real working
    sequence uses SelectItem on the Camera's own numeric ID (e.g.
    "SelectItem 30000000" - Camera/Light/Object each have their own ID
    range, confirmed 10000000/20000000/30000000 respectively), not its
    name. See PLAN.md 'ParentItem argument format' for the original
    numeric-ID finding this extends."""
    item_id, item_resp = _resolve_item_id(item)
    if not item_id:
        return json.dumps({"error": "could not resolve item: %s" % item, "detail": item_resp})
    ref_id, ref_resp = _resolve_item_id(reference)
    if not ref_id:
        return json.dumps({"error": "could not resolve item: %s" % reference, "detail": ref_resp})
    lw = _layout()
    try:
        lw.SelectItem(item_id)
        getattr(lw, command)(ref_id)
        return json.dumps({"result": "%s(%s) -> %s (ids %s -> %s)" % (command, item, reference, item_id, ref_id)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


@mcp.tool()
def lw_set_parent(child: str, parent: str) -> str:
    """Reparent one item to another (ROADMAP.md's previously-unsolved
    write gap - see PLAN.md 'ParentItem argument format'). Confirmed
    root cause: ParentItem (and this whole command family - TargetItem/
    GoalItem/PoleItem) silently no-ops when given a name string instead
    of the numeric item ID it actually expects, AND relying on
    SelectItem(name) to pick the item being modified is only reliable
    for Objects - resolves both child and parent to their numeric IDs
    before sending, rather than trusting SelectItem's name resolution
    at all. Confirmed live: lw_get_hierarchy correctly showed the new
    parent afterward, matching ground truth from the Motion Options
    panel, on a fresh untouched pair of Nulls."""
    return _set_reference_item("ParentItem", child, parent)


@mcp.tool()
def lw_set_target(item: str, target: str) -> str:
    """Set an item's IK/camera/light target (e.g. point a Camera or
    Light at a Null) - same fix as lw_set_parent. Confirmed live for
    all three categories: targeting by Camera name alone
    (SelectItem("Camera")) applied the target to an unrelated,
    already-current Object instead of the Camera - Cmd History of the
    equivalent manual action showed the real working sequence selects
    the Camera by its own numeric ID (e.g. "SelectItem 30000000", not
    "SelectItem Camera"). Object/Light/Camera IDs live in separate
    numeric ranges (confirmed 10000000/20000000/30000000 respectively).
    Fixed by resolving both `item` and `target` to numeric IDs first.
    Confirmed live after the fix: both Camera.target and Light.target
    correctly showed the new target via lw_get_hierarchy. See PLAN.md
    'ParentItem argument format' for the full history."""
    return _set_reference_item("TargetItem", item, target)


@mcp.tool()
def lw_set_goal(item: str, goal: str) -> str:
    """Set an item's IK goal (GoalItem) - same numeric-ID-for-both-
    arguments fix as lw_set_parent/lw_set_target. Confirmed live: no
    bones/true IK chain needed to test, since goal()/pole() are
    generic per-item properties in the SDK (lw_get_hierarchy already
    queries them for every item type) - set on a plain Null,
    lw_get_hierarchy correctly showed the new goal afterward."""
    return _set_reference_item("GoalItem", item, goal)


@mcp.tool()
def lw_set_pole(item: str, pole: str) -> str:
    """Set an item's IK pole (PoleItem) - same fix as lw_set_goal.
    Confirmed live the same way, set alongside a goal on the same
    plain Null with lw_get_hierarchy correctly showing both
    afterward."""
    return _set_reference_item("PoleItem", item, pole)


@mcp.tool()
def lw_get_hierarchy() -> str:
    """Get parent/child and IK (target/goal/pole) relationships for every
    object, light, and camera in the scene - e.g. before rigging on top
    of an object that's already parented to something else. Each item
    reports its own name/type plus the name of its parent (None if it
    has none), and its IK target/goal/pole items if any are set. Uses
    LWItemInfo.parent()/target()/goal()/pole(), confirmed via NewTek's
    official SDK docs - the same LWItemInfo class already proven safe
    elsewhere in this connector (lw_get_transform), not the LWChannelInfo
    path that crashed Layout during development (see PLAN.md).

    Does NOT currently walk bone chains within an object (only top-level
    item parenting) - that's a follow-up once there's a real boned
    object to verify traversal against safely; see PLAN.md."""
    return json.dumps(_query("get_hierarchy"))


if __name__ == "__main__":
    mcp.run()
