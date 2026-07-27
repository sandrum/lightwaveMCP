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


def _probe_channels(name):
    """Diagnostic for ROADMAP item 1b (item transform query). Ported
    verbatim from lw_mcp_diag4.py's _probe_channels, which was never
    confirmed live because diag4/5/6's ring_event never fired at all -
    routing it through this proven-working listener instead of chasing
    that mystery further."""
    out = {"groups": []}
    target = _find_item(name)
    out["target_id"] = repr(target)
    if target is None:
        out["error"] = "item not found: %s" % name
        return out

    ci = lwsdk.LWChannelInfo()

    try:
        g = ci.nextGroup(None)
        out["nextGroup(None)_first_call"] = repr(g)
    except Exception as exc:  # noqa: BLE001
        out["nextGroup(None) FAILED"] = str(exc)
        g = None

    count = 0
    seen_groups = []
    while g is not None and count < 10:
        entry = {"group_repr": repr(g)}
        try:
            entry["groupName"] = ci.groupName(g)
        except Exception as exc:  # noqa: BLE001
            entry["groupName FAILED"] = str(exc)

        chan_count = 0
        chans = []
        try:
            c = ci.nextChannel(g, None)
        except Exception as exc:  # noqa: BLE001
            c = None
            entry["nextChannel FAILED"] = str(exc)
        while c is not None and chan_count < 15:
            chan_entry = {"chan_repr": repr(c)}
            try:
                chan_entry["channelName"] = ci.channelName(c)
            except Exception as exc:  # noqa: BLE001
                chan_entry["channelName FAILED"] = str(exc)
            try:
                parent = ci.channelParent(c)
                chan_entry["channelParent"] = repr(parent)
                chan_entry["matches_target"] = (parent == target)
            except Exception as exc:  # noqa: BLE001
                chan_entry["channelParent FAILED"] = str(exc)
            try:
                chan_entry["channelEvaluate(0.0)"] = ci.channelEvaluate(c, 0.0)
            except Exception as exc:  # noqa: BLE001
                chan_entry["channelEvaluate FAILED"] = str(exc)
            chans.append(chan_entry)
            chan_count += 1
            try:
                c = ci.nextChannel(g, c)
            except Exception as exc:  # noqa: BLE001
                chan_entry["nextChannel(advance) FAILED"] = str(exc)
                break
        entry["channels"] = chans
        seen_groups.append(entry)

        count += 1
        try:
            g = ci.nextGroup(g)
        except Exception as exc:  # noqa: BLE001
            out["nextGroup(advance) FAILED"] = str(exc)
            break

    out["groups"] = seen_groups
    out["group_iterations"] = count
    return out


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
            payload = {"result": "pong-V2-MARKER"}
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
        elif command == "probe_channels":
            payload = {"result": _probe_channels(arg or "TransformTest")}
        elif command == "probe_surf":
            payload = {"result": _probe_surf_constants()}
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
