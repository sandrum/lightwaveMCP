"""
lw_mcp_ring.py

Read-path Master plug-in for the Claude <-> LightWave MCP connector, built
on the *real* mechanism for receiving Command Port traffic: LWComRing.

Why this replaces lw_mcp_master.py (LWEVNT_COMMAND approach): that was a
confirmed, empirically-tested dead end - event() never fired for Command
Port traffic no matter what. The correct mechanism, found in NewTek's own
bundled example (support/plugins/scripts/Python/Layout/Master/
command_port_test.py, shipped with every LightWave 2019.1.5 install), is:

  1. Hold an lwsdk.LWComRing() instance.
  2. In inst_acquire(), call self._comring.ringAttach(
       lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)
  3. Command Port traffic arrives at the ring_event(client_data, port_data,
     event_code, event_data) callback, event_code 0.
  4. Decode the raw bytes with self._comring.decodeData(('s:256',),
     event_data) -> a 1-tuple containing the string.
  5. Messages are expected in the form "{Topic} rest of message" - this
     matches the Ring(topic, command) method already present in the
     bundled lwcommandport client library's CommandPort base class, which
     formats exactly that: "{%s} %s" % (topic, command).

So the external client calls lw.Ring("MCP", "ping") (or "get_scene_info"),
which sends "{MCP} ping" over the same UDP Command Port used for AddNull
etc. This plug-in listens for the "MCP" topic specifically and writes its
answer to _mcp_response.json, which server.py polls (unchanged protocol
from the old, non-working attempt - only the delivery mechanism changes).

SETUP (must be done every fresh Layout session, same as the Command Port
itself):
  1. Utilities > Plugins > Add Plugins > lw_mcp_ring.py (registers the
     class - unlike the old single-shot enable script, this ships a
     ServerRecord so it needs a second step below).
  2. Utilities > Master Plugins > "Add Layout or Scene Master" dropdown >
     select "LW MCP Ring" > make sure its "On" checkbox is ticked.
     (Confirmed in earlier testing: LWMAST_LAYOUT-flagged masters still
     need this explicit activation step - just loading via Add Plugins is
     not enough to get inst_acquire() called.)
"""
import json
import os
import re

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_response.json")
DEBUG_LOG_PATH = os.path.join(_HERE, "_mcp_ring_debug.log")
RENDER_STATUS_PATH = os.path.join(_HERE, "_mcp_render_status.json")

TOPIC = "MCP"
_TOPIC_RE = re.compile(r"^\{(.+)\}\s*(.*)$")


def _log(line):
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _write_response(payload):
    tmp_path = RESPONSE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f)
    try:
        os.remove(RESPONSE_PATH)
    except OSError:
        pass
    os.rename(tmp_path, RESPONSE_PATH)


def _find_item(name):
    """Search all item types for a name. Returns the item ID or None."""
    ii = lwsdk.LWItemInfo()
    for item_type in (lwsdk.LWI_OBJECT, lwsdk.LWI_LIGHT, lwsdk.LWI_CAMERA):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            if ii.name(it) == name:
                return it
            it = ii.next(it)
    return None


def _vec_to_list(v):
    """Best-effort conversion of a PCore::Vector SWIG object to a plain
    list, since it isn't JSON-serializable directly. Confirmed live that
    LWLightInfo().color() returns this type."""
    try:
        return [v.x, v.y, v.z]
    except AttributeError:
        pass
    try:
        return list(v)
    except TypeError:
        pass
    return str(v)


def _get_selection():
    """Every item's name/type and whether it's currently selected.
    Confirmed live: LWItemInfo().selected(item) is the reliable signal -
    flags() & LWITEMF_SELECTED was tested and does NOT reflect actual
    selection state (returned the same value for every item regardless)."""
    ii = lwsdk.LWItemInfo()
    items = []
    for label, item_type in (
        ("OBJECT", lwsdk.LWI_OBJECT),
        ("LIGHT", lwsdk.LWI_LIGHT),
        ("CAMERA", lwsdk.LWI_CAMERA),
    ):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            items.append({
                "name": ii.name(it),
                "type": label,
                "selected": bool(ii.selected(it)),
            })
            it = ii.next(it)
    return {"items": items, "selected": [i["name"] for i in items if i["selected"]]}


def _get_camera_info(name):
    """Confirmed live signatures: resolution(id) takes just the item ID;
    focalLength/fStop/fovAngles/zoomFactor are animatable channels and
    need a second (time) argument - passing 0.0 (start of scene), NOT the
    live playhead position, since there's no confirmed way to query
    current time from Python yet. Good enough for non-animated cameras;
    a real "current time" query is still open (see ROADMAP.md)."""
    cam_id = _find_item(name)
    if cam_id is None:
        return {"error": "camera not found: %s" % name}
    ci = lwsdk.LWCameraInfo()
    return {
        "name": name,
        "resolution": list(ci.resolution(cam_id)),
        "focal_length_mm": ci.focalLength(cam_id, 0.0),
        "f_stop": ci.fStop(cam_id, 0.0),
        "fov_angles_h_v": list(ci.fovAngles(cam_id, 0.0)),
        "zoom_factor": ci.zoomFactor(cam_id, 0.0),
        "note": "animatable values evaluated at time=0.0, not the live playhead",
    }


def _get_light_info(name):
    """Same time=0.0 caveat as _get_camera_info."""
    light_id = _find_item(name)
    if light_id is None:
        return {"error": "light not found: %s" % name}
    li = lwsdk.LWLightInfo()
    return {
        "name": name,
        "type": li.type(light_id),
        "falloff": li.falloff(light_id),
        "color_rgb": _vec_to_list(li.color(light_id, 0.0)),
        "intensity": li.intensity(light_id, 0.0),
        "range": li.range(light_id, 0.0),
        "note": "animatable values evaluated at time=0.0, not the live playhead",
    }


def _get_transform(name):
    """Item position/rotation/scale. FOUND THE REAL API - does NOT use
    LWChannelInfo/nextGroup (confirmed crashing, see _probe_channels
    below). NewTek's C SDK docs (etwright.org/lwsdk/docs/globals/
    iteminfo.html) show LWItemInfo already has a direct `param(item,
    param_type, time, vector)` call for exactly this - position/rotation/
    scale are LWIP_POSITION/LWIP_ROTATION/LWIP_SCALING. Real-world Python
    plugin code (a bone-rigging tool, found via web search) confirmed the
    Python binding is the 3-arg form `item_info.param(item_id, type,
    time)` returning the vector directly (no separate out-parameter,
    matching the pattern already proven for LWCameraInfo/LWLightInfo in
    this file). Same time=0.0 caveat as camera/light info."""
    target = _find_item(name)
    if target is None:
        return {"error": "item not found: %s" % name}
    ii = lwsdk.LWItemInfo()
    return {
        "name": name,
        "position": _vec_to_list(ii.param(target, lwsdk.LWIP_POSITION, 0.0)),
        "rotation": _vec_to_list(ii.param(target, lwsdk.LWIP_ROTATION, 0.0)),
        "scale": _vec_to_list(ii.param(target, lwsdk.LWIP_SCALING, 0.0)),
        "note": "animatable values evaluated at time=0.0, not the live playhead",
    }


def _get_surface_info(name):
    """Surface/material info via LWSurfaceFuncs(). Real-world Python
    plugin code (OD_CopyPasteExternal on GitHub, found via web search)
    confirmed live calling conventions: byName(surfname, objname) and
    byObject(objname) return plain Python-iterable lists of surface IDs
    (not the NULL-terminated C array the SDK doc describes - SWIG handles
    that), and getFlt(surf, channel) returns a plain float directly
    (compared with `> 0` in the reference code), not the C pointer the
    doc describes. objname=None should match every object per the C doc.
    Untested against a real textured object as of this writing (the live
    scene only had a Null and default Light/Camera) - test with a real
    object before trusting this fully; wrap in the same try/except
    _handle_query already has so a bad channel name degrades to an error
    response rather than an unhandled exception."""
    surf_ids = lwsdk.LWSurfaceFuncs().byName(name, None)
    if not surf_ids:
        return {"error": "surface not found: %s" % name}
    surf = surf_ids[0]
    sf = lwsdk.LWSurfaceFuncs()
    return {
        "name": sf.name(surf),
        "color_rgb": _vec_to_list(sf.getFlt(surf, lwsdk.SURF_COLR)),
        "diffuse": sf.getFlt(surf, lwsdk.SURF_DIFF),
        "luminosity": sf.getFlt(surf, lwsdk.SURF_LUMI),
        "specularity": sf.getFlt(surf, lwsdk.SURF_SPEC),
        "glossiness": sf.getFlt(surf, lwsdk.SURF_GLOS),
        "reflection": sf.getFlt(surf, lwsdk.SURF_REFL),
        "transparency": sf.getFlt(surf, lwsdk.SURF_TRAN),
        "smoothing": sf.getFlt(surf, lwsdk.SURF_SMAN),
    }


def _probe_channels(name):
    """DISABLED as of this edit: lwsdk.LWChannelInfo().nextGroup(target,
    None) - called with an item ID (from LWItemInfo) as the first
    argument, satisfying the "takes exactly 3 arguments" signature error
    seen with nextGroup(None) alone - reproducibly took down the entire
    Layout process (no Python exception, no crash-report-worthy Python
    traceback, just silence in the debug log after "about to call" and
    then total unresponsiveness / an actual LightWave crash-reporter
    dialog on next Quit). Confirmed twice. There is no LWChannelInfo C
    header shipped with this install to check the real expected argument
    types, and guessing further risks more crashes/restarts. Leaving
    this stubbed out - ROADMAP item 1b (item transform query) is
    blocked on this until NewTek's actual SDK docs/header for
    LWChannelInfo can be consulted (see PLAN.md for the full writeup)."""
    target = _find_item(name)
    if target is None:
        return {"error": "item not found: %s" % name}
    return {
        "target_id": repr(target),
        "error": "probe disabled - nextGroup(item, prev) crashed Layout twice, "
                 "see PLAN.md 'LWChannelInfo crash' section",
    }


def _resolve_name(ii, item_id):
    """None for LWITEM_NULL (no relationship set), otherwise the item's
    name. Isolated so a bad/unexpected ID degrades to None instead of
    raising and killing the whole hierarchy query."""
    try:
        if item_id is None or item_id == lwsdk.LWITEM_NULL:
            return None
        return ii.name(item_id)
    except Exception:
        return None


def _get_hierarchy():
    """Parent/child and IK (target/goal/pole) relationships for every
    object/light/camera. Uses LWItemInfo.parent()/target()/goal()/
    pole() - confirmed via NewTek's official Python SDK docs (fetched
    live from static.lightwave3d.com/sdk/2015/python/globaliteminfo.html,
    since none ship with this install; this is the same LWItemInfo class
    already proven safe here for _get_transform's param() calls, NOT the
    LWChannelInfo path that crashed Layout - see PLAN.md). parent()
    returns an item ID or LWITEM_NULL, so each relationship is resolved
    to a name via a second LWItemInfo call rather than returned as a raw
    ID, matching how every other query in this file reports items.

    Deliberately NOT walking bone chains yet (LWItemInfo.first(LWI_BONE,
    object) / next() would be needed) - the current live scene has no
    boned object to test against, and given this project's real history
    of an unbounded-traversal crash in a different SDK area
    (LWChannelInfo/nextGroup, see PLAN.md), that's being left for a
    follow-up increment with a real bone hierarchy to verify against
    rather than shipped un-tested. Item-level parenting (nulls, objects,
    lights, cameras) is fully covered here."""
    ii = lwsdk.LWItemInfo()
    items = []
    for label, item_type in (
        ("OBJECT", lwsdk.LWI_OBJECT),
        ("LIGHT", lwsdk.LWI_LIGHT),
        ("CAMERA", lwsdk.LWI_CAMERA),
    ):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            entry = {
                "name": ii.name(it),
                "type": label,
                "parent": _resolve_name(ii, ii.parent(it)),
            }
            for key, getter in (("target", ii.target), ("goal", ii.goal), ("pole", ii.pole)):
                try:
                    entry[key] = _resolve_name(ii, getter(it))
                except Exception:
                    pass
            items.append(entry)
            it = ii.next(it)
    return {"items": items}


def _get_item_id(name):
    """Resolve an item's name to the plain numeric ID string LightWave's
    native item-reference commands (ParentItem, TargetItem, GoalItem,
    PoleItem) actually expect on the Command Port - confirmed via Cmd
    History showing real UI-driven actions log as e.g. "ParentItem
    10000000", never a name. SelectItem is the odd one out: its command
    handler resolves names internally (confirmed working via lw_name
    string args throughout this project), but ParentItem/TargetItem do
    not - passing a name silently coerces to argument 0 (a no-op), with
    no error and no dialog. lwsdk.itemid_to_str() (a module-level
    helper, found by grepping an old _introspect() diagnostic dump for
    "itemid" - sitting unused in lwsdk.dir() since long before this was
    identified as the actual root cause) converts the opaque NodeID
    handle _find_item() already returns into exactly that numeric string
    form. See PLAN.md 'ParentItem argument format' for the Cmd History
    evidence."""
    item = _find_item(name)
    if item is None:
        return {"error": "item not found: %s" % name}
    return {"name": name, "id": lwsdk.itemid_to_str(item)}


def _get_render_status():
    """Reads the status file written by lw_mcp_render_monitor.py's
    IFrameBuffer.open()/close() callbacks (ROADMAP.md item 6). Separate
    plug-in/file from this one because Frame Buffer is a different
    LightWave plug-in architecture (Render Display server) than Master
    (LWComRing) - this query just surfaces its output over the read
    path already proven here, rather than requiring a second polling
    mechanism on the client side."""
    if not os.path.exists(RENDER_STATUS_PATH):
        return {
            "rendering": None,
            "note": "no render has been triggered yet this session, or "
                    "lw_mcp_render_monitor.py isn't set as the active Render "
                    "Display (Render Globals > Render Display tab) - see "
                    "lw_mcp_render_monitor.py's docstring",
        }
    try:
        with open(RENDER_STATUS_PATH) as f:
            return json.load(f)
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}


def _probe_surf_constants():
    names = [n for n in dir(lwsdk) if n.startswith("SURF_")]
    return sorted(names)


def _get_scene_info():
    scene = lwsdk.LWSceneInfo()
    iteminfo = lwsdk.LWItemInfo()

    items = []
    for item_type in (lwsdk.LWI_OBJECT, lwsdk.LWI_LIGHT, lwsdk.LWI_CAMERA):
        item = iteminfo.first(item_type, lwsdk.LWITEM_NULL)
        while item != lwsdk.LWITEM_NULL:
            items.append(iteminfo.name(item))
            item = iteminfo.next(item)

    return {
        "scene_name": scene.name,
        "filename": scene.filename,
        "items": items,
    }


def _introspect():
    """Diagnostic: find real lwsdk class/method names for extending the
    read path (item transform, selection, surface, camera/light info).
    Temporary - not part of the permanent tool surface."""
    interesting_substrings = [
        "Channel", "Surface", "Camera", "Light", "Item", "Select",
        "State", "Transform", "Scene", "Bound",
    ]
    names = dir(lwsdk)
    matches = sorted(set(
        n for n in names
        if any(s.lower() in n.lower() for s in interesting_substrings)
    ))

    probes = {}
    for expr in [
        "lwsdk.LWItemInfo()",
        "lwsdk.LWSceneInfo()",
        "lwsdk.LWChannelInfo()",
        "lwsdk.LWStateQueryFuncs()",
        "lwsdk.LWSurfaceFuncs()",
        "lwsdk.LWCameraInfo()",
        "lwsdk.LWLightInfo()",
        "lwsdk.LWObjectInfo()",
        "lwsdk.LWObjectFuncs()",
    ]:
        try:
            obj = eval(expr)
            probes[expr] = [m for m in dir(obj) if not m.startswith("_")]
        except Exception as exc:  # noqa: BLE001
            probes[expr] = "FAILED: %s" % exc

    return {"matches": matches, "probes": probes}


def _handle_query(text):
    parts = text.split(None, 1)
    command = parts[0] if parts else "ping"
    arg = parts[1].strip() if len(parts) > 1 else ""

    try:
        if command == "ping":
            payload = {"result": "pong"}
        elif command == "get_scene_info":
            payload = {"result": _get_scene_info()}
        elif command == "introspect":
            payload = {"result": _introspect()}
        elif command == "get_selection":
            payload = {"result": _get_selection()}
        elif command == "get_camera_info":
            payload = {"result": _get_camera_info(arg or "Camera")}
        elif command == "get_light_info":
            payload = {"result": _get_light_info(arg or "Light")}
        elif command == "get_transform":
            payload = {"result": _get_transform(arg or "TransformTest")}
        elif command == "get_surface_info":
            payload = {"result": _get_surface_info(arg)}
        elif command == "probe_channels":
            payload = {"result": _probe_channels(arg or "TransformTest")}
        elif command == "probe_surf":
            payload = {"result": _probe_surf_constants()}
        elif command == "get_render_status":
            payload = {"result": _get_render_status()}
        elif command == "get_hierarchy":
            payload = {"result": _get_hierarchy()}
        elif command == "get_item_id":
            payload = {"result": _get_item_id(arg)}
        else:
            payload = {"error": "unknown command: %s" % command}
    except Exception as exc:  # noqa: BLE001
        payload = {"error": str(exc)}

    _write_response(payload)


class mcp_ring_master_v4(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_ring_master_v4, self).__init__()
        self._comring = lwsdk.LWComRing()
        _log("mcp_ring_master_v4 instantiated")

    # LWInstanceFuncs ---------------------------------------------------
    def inst_copy(self, source):
        return None

    def inst_descln(self):
        return "Claude MCP Command Port Ring listener"

    def inst_acquire(self):
        self._comring.ringAttach(lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)
        _log("ringAttach called")

    def inst_release(self):
        self._comring.ringDetach(lwsdk.LW_PORT_COMMAND_PORT, self)
        _log("ringDetach called")

    # ComRing -------------------------------------------------------------
    def ring_event(self, client_data, port_data, event_code, event_data):
        if event_code != 0:
            return
        data = self._comring.decodeData(('s:256',), event_data)
        if not data:
            _log("ring_event: decodeData failed")
            return
        raw = data[0]
        _log("ring_event: raw=%r" % (raw,))
        m = _TOPIC_RE.match(raw)
        if not m:
            return
        topic, rest = m.group(1), m.group(2)
        if topic != TOPIC:
            return
        _handle_query(rest.strip())

    # LWMaster ------------------------------------------------------------
    def flags(self):
        return lwsdk.LWMAST_LAYOUT

    def event(self, ma):
        return 0.0


ServerTagInfo = [
    ("LW MCP Ring4", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Ring4", mcp_ring_master_v4): ServerTagInfo,
}
