"""
lw_mcp_diag2.py - second-round probe: confirm actual method signatures
(selection, camera info, light info) against real live items, before
committing to lw_mcp_ring.py's permanent implementation. Topic "MCPDIAG2".
"""
import json
import os
import re

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_diag2_response.json")

TOPIC = "MCPDIAG2"
_TOPIC_RE = re.compile(r"^\{(.+)\}\s*(.*)$")


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
    ii = lwsdk.LWItemInfo()
    for item_type in (lwsdk.LWI_OBJECT, lwsdk.LWI_LIGHT, lwsdk.LWI_CAMERA):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            if ii.name(it) == name:
                return it, ii
            it = ii.next(it)
    return None, ii


def _probe():
    out = {}
    ii = lwsdk.LWItemInfo()

    # selection: list all items + selected flag via two different methods
    sel = []
    for label, item_type in (("OBJECT", lwsdk.LWI_OBJECT), ("LIGHT", lwsdk.LWI_LIGHT), ("CAMERA", lwsdk.LWI_CAMERA)):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            entry = {"type": label, "name": ii.name(it)}
            try:
                entry["selected()"] = ii.selected(it)
            except Exception as exc:
                entry["selected() FAILED"] = str(exc)
            try:
                entry["flags()"] = ii.flags(it)
                entry["flags()&SELECTED"] = bool(ii.flags(it) & lwsdk.LWITEMF_SELECTED)
            except Exception as exc:
                entry["flags() FAILED"] = str(exc)
            sel.append(entry)
            it = ii.next(it)
    out["items"] = sel

    # camera probe
    cam_id, _ = _find_item("Camera")
    cam_out = {"id": repr(cam_id)}
    if cam_id is not None:
        caminfo = lwsdk.LWCameraInfo()
        for method in ["focalLength", "fStop", "fovAngles", "zoomFactor", "resolution"]:
            try:
                cam_out[method] = repr(getattr(caminfo, method)(cam_id))
            except Exception as exc:
                cam_out[method + " FAILED"] = str(exc)
    out["camera"] = cam_out

    # light probe
    light_id, _ = _find_item("Light")
    light_out = {"id": repr(light_id)}
    if light_id is not None:
        lightinfo = lwsdk.LWLightInfo()
        for method in ["color", "intensity", "type", "range", "falloff"]:
            try:
                light_out[method] = repr(getattr(lightinfo, method)(light_id))
            except Exception as exc:
                light_out[method + " FAILED"] = str(exc)
    out["light"] = light_out

    return out


class mcp_diag2_master(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_diag2_master, self).__init__()

    def inst_copy(self, source):
        return None

    def inst_descln(self):
        return "Claude MCP diagnostic2 ring listener"

    def inst_acquire(self):
        self._comring = lwsdk.LWComRing()
        self._comring.ringAttach(lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)

    def inst_release(self):
        self._comring.ringDetach(lwsdk.LW_PORT_COMMAND_PORT, self)

    def ring_event(self, client_data, port_data, event_code, event_data):
        if event_code != 0:
            return
        data = self._comring.decodeData(('s:256',), event_data)
        if not data:
            return
        m = _TOPIC_RE.match(data[0])
        if not m:
            return
        topic, rest = m.group(1), m.group(2)
        if topic != TOPIC:
            return
        try:
            payload = {"result": _probe()}
        except Exception as exc:  # noqa: BLE001
            payload = {"error": str(exc)}
        _write_response(payload)

    def flags(self):
        return lwsdk.LWMAST_LAYOUT

    def event(self, ma):
        return 0.0


ServerTagInfo = [
    ("LW MCP Diag2", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Diag2", mcp_diag2_master): ServerTagInfo,
}
