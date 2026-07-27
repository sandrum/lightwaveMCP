"""
lw_mcp_diag3.py - confirm the time-parameter signature for animatable
camera/light properties (focalLength, color, intensity, etc. all failed
with "takes exactly 3 arguments" in diag2 - testing with an explicit
float time argument). Topic "MCPDIAG3".
"""
import json
import os
import re

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_diag3_response.json")

TOPIC = "MCPDIAG3"
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
                return it
            it = ii.next(it)
    return None


def _probe():
    out = {}
    cam_id = _find_item("Camera")
    cam_out = {}
    if cam_id is not None:
        caminfo = lwsdk.LWCameraInfo()
        for method in ["focalLength", "fStop", "fovAngles", "zoomFactor"]:
            try:
                cam_out[method] = repr(getattr(caminfo, method)(cam_id, 0.0))
            except Exception as exc:
                cam_out[method + " FAILED"] = str(exc)
    out["camera"] = cam_out

    light_id = _find_item("Light")
    light_out = {}
    if light_id is not None:
        lightinfo = lwsdk.LWLightInfo()
        for method in ["color", "intensity", "range"]:
            try:
                light_out[method] = repr(getattr(lightinfo, method)(light_id, 0.0))
            except Exception as exc:
                light_out[method + " FAILED"] = str(exc)
    out["light"] = light_out
    return out


class mcp_diag3_master(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_diag3_master, self).__init__()

    def inst_copy(self, source):
        return None

    def inst_descln(self):
        return "Claude MCP diagnostic3 ring listener"

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
    ("LW MCP Diag3", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Diag3", mcp_diag3_master): ServerTagInfo,
}
