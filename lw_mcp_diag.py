"""
lw_mcp_diag.py

Standalone, isolated diagnostic Master plug-in using the same LWComRing
mechanism as lw_mcp_ring.py, but under a distinct class/topic name
("LW_MCP_Diag" / topic "MCPDIAG") so it can be freshly added without
colliding with the already-registered "LW_MCP_Ring" (which LightWave
refused to re-register in place after an edit - "Plugins were not found
or could not be added"). Purpose: introspect the live lwsdk module to
find real class/method names for item transform, selection, surface, and
camera/light info, needed to extend the permanent read path. Throwaway -
not part of the shipped tool surface.
"""
import json
import os
import re

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_diag_response.json")

TOPIC = "MCPDIAG"
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


def _introspect():
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


class mcp_diag_master(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_diag_master, self).__init__()

    def inst_copy(self, source):
        return None

    def inst_descln(self):
        return "Claude MCP diagnostic ring listener"

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
            payload = {"result": _introspect()}
        except Exception as exc:  # noqa: BLE001
            payload = {"error": str(exc)}
        _write_response(payload)

    def flags(self):
        return lwsdk.LWMAST_LAYOUT

    def event(self, ma):
        return 0.0


ServerTagInfo = [
    ("LW MCP Diag", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Diag", mcp_diag_master): ServerTagInfo,
}
