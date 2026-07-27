"""
lw_mcp_diag4.py - probe LWChannelInfo iteration (for item transform,
ROADMAP item 1b) and SURF_* constants (for surface info, ROADMAP item
1c). Topic "MCPDIAG4".
"""
import json
import os
import re

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_diag4_response.json")

TOPIC = "MCPDIAG4"
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


def _probe_channels():
    out = {"groups": []}
    target = _find_item("TransformTest")
    out["target_id"] = repr(target)

    ci = lwsdk.LWChannelInfo()

    # Try calling nextGroup with no args, then with None, to see which
    # signature this build actually accepts, and what the end sentinel is.
    try:
        g = ci.nextGroup(None)
        out["nextGroup(None)_first_call"] = repr(g)
    except Exception as exc:
        out["nextGroup(None) FAILED"] = str(exc)
        g = None

    count = 0
    seen_groups = []
    while g is not None and count < 10:
        entry = {"group_repr": repr(g)}
        try:
            entry["groupName"] = ci.groupName(g)
        except Exception as exc:
            entry["groupName FAILED"] = str(exc)

        chan_count = 0
        chans = []
        try:
            c = ci.nextChannel(g, None)
        except Exception as exc:
            c = None
            entry["nextChannel FAILED"] = str(exc)
        while c is not None and chan_count < 15:
            chan_entry = {"chan_repr": repr(c)}
            try:
                chan_entry["channelName"] = ci.channelName(c)
            except Exception as exc:
                chan_entry["channelName FAILED"] = str(exc)
            try:
                parent = ci.channelParent(c)
                chan_entry["channelParent"] = repr(parent)
                chan_entry["matches_target"] = (parent == target)
            except Exception as exc:
                chan_entry["channelParent FAILED"] = str(exc)
            try:
                chan_entry["channelEvaluate(0.0)"] = ci.channelEvaluate(c, 0.0)
            except Exception as exc:
                chan_entry["channelEvaluate FAILED"] = str(exc)
            chans.append(chan_entry)
            chan_count += 1
            try:
                c = ci.nextChannel(g, c)
            except Exception as exc:
                chan_entry["nextChannel(advance) FAILED"] = str(exc)
                break
        entry["channels"] = chans
        seen_groups.append(entry)

        count += 1
        try:
            g = ci.nextGroup(g)
        except Exception as exc:
            out["nextGroup(advance) FAILED"] = str(exc)
            break

    out["groups"] = seen_groups
    out["group_iterations"] = count
    return out


def _probe_surf_constants():
    names = [n for n in dir(lwsdk) if n.startswith("SURF_")]
    return sorted(names)


def _probe():
    result = {}
    try:
        result["channels"] = _probe_channels()
    except Exception as exc:  # noqa: BLE001
        result["channels_error"] = str(exc)
    try:
        result["surf_constants"] = _probe_surf_constants()
    except Exception as exc:  # noqa: BLE001
        result["surf_constants_error"] = str(exc)
    return result


class mcp_diag4_master(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_diag4_master, self).__init__()

    def inst_copy(self, source):
        return None

    def inst_descln(self):
        return "Claude MCP diagnostic4 ring listener"

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
    ("LW MCP Diag4", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Diag4", mcp_diag4_master): ServerTagInfo,
}
