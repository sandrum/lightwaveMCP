"""
lw_mcp_diag6.py - identical to diag5 except self._comring is created in
__init__ (matching lw_mcp_ring.py's known-working pattern exactly)
instead of inst_acquire. Isolating this one variable since diag4/diag5
(which create it in inst_acquire) never fired ring_event at all, even as
the sole attached listener. Topic "MCPDIAG6".
"""
import os
import re

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(_HERE, "_mcp_diag6_log.txt")

TOPIC = "MCPDIAG6"
_TOPIC_RE = re.compile(r"^\{(.+)\}\s*(.*)$")


def _log(line):
    f = open(LOG_PATH, "a")
    f.write(line + "\n")
    f.flush()
    f.close()


class mcp_diag6_master(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_diag6_master, self).__init__()
        self._comring = lwsdk.LWComRing()
        _log("__init__: comring created")

    def inst_copy(self, source):
        return None

    def inst_descln(self):
        return "Claude MCP diagnostic6 ring listener"

    def inst_acquire(self):
        self._comring.ringAttach(lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)
        _log("inst_acquire: ringAttach done")

    def inst_release(self):
        self._comring.ringDetach(lwsdk.LW_PORT_COMMAND_PORT, self)

    def ring_event(self, client_data, port_data, event_code, event_data):
        _log("ring_event CALLED: event_code=%r" % (event_code,))
        if event_code != 0:
            return
        try:
            data = self._comring.decodeData(('s:256',), event_data)
        except BaseException as exc:
            _log("decodeData raised: %r" % (exc,))
            return
        if not data:
            return
        _log("ring_event: raw=%r" % (data[0],))
        m = _TOPIC_RE.match(data[0])
        if not m:
            return
        topic, rest = m.group(1), m.group(2)
        if topic != TOPIC:
            return
        _log("TOPIC MATCHED: %r" % (rest,))

    def flags(self):
        return lwsdk.LWMAST_LAYOUT

    def event(self, ma):
        return 0.0


ServerTagInfo = [
    ("LW MCP Diag6", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Diag6", mcp_diag6_master): ServerTagInfo,
}
