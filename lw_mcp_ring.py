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


def _handle_query(text):
    parts = text.split(None, 1)
    command = parts[0] if parts else "ping"

    try:
        if command == "ping":
            payload = {"result": "pong"}
        elif command == "get_scene_info":
            payload = {"result": _get_scene_info()}
        else:
            payload = {"error": "unknown command: %s" % command}
    except Exception as exc:  # noqa: BLE001
        payload = {"error": str(exc)}

    _write_response(payload)


class mcp_ring_master(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_ring_master, self).__init__()
        self._comring = lwsdk.LWComRing()
        _log("mcp_ring_master instantiated")

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
    ("LW MCP Ring", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Ring", mcp_ring_master): ServerTagInfo,
}
