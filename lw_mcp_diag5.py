"""
lw_mcp_diag5.py - hardened retry of diag4 (which silently produced no
output at all, no error, no crash - Layout stayed responsive and the
main "MCP" ring listener kept working fine throughout). Theory: a SWIG
binding raised something not caught by "except Exception". This version
catches BaseException everywhere and writes incrementally (append mode,
flushed after every step) so partial progress survives even a silent
kill of the callback. Topic "MCPDIAG5".
"""
import os
import re

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(_HERE, "_mcp_diag5_log.txt")

TOPIC = "MCPDIAG5"
_TOPIC_RE = re.compile(r"^\{(.+)\}\s*(.*)$")


def _log(line):
    f = open(LOG_PATH, "a")
    f.write(line + "\n")
    f.flush()
    f.close()


def _find_item(name):
    ii = lwsdk.LWItemInfo()
    for item_type in (lwsdk.LWI_OBJECT, lwsdk.LWI_LIGHT, lwsdk.LWI_CAMERA):
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            if ii.name(it) == name:
                return it
            it = ii.next(it)
    return None


def _run():
    _log("=== run start ===")

    target = _find_item("TransformTest")
    _log("target=%r" % (target,))

    ci = lwsdk.LWChannelInfo()
    _log("LWChannelInfo() created ok")

    # Try the call that's most likely to be the crash point, in total
    # isolation, logging BEFORE and AFTER so we know if it returned at all.
    _log("about to call nextGroup(None)")
    try:
        g = ci.nextGroup(None)
        _log("nextGroup(None) returned: %r" % (g,))
    except BaseException as exc:
        _log("nextGroup(None) raised: %r (%s)" % (exc, type(exc)))
        g = "STOP"

    if g not in (None, "STOP"):
        _log("about to call groupName(g)")
        try:
            gn = ci.groupName(g)
            _log("groupName(g) returned: %r" % (gn,))
        except BaseException as exc:
            _log("groupName(g) raised: %r (%s)" % (exc, type(exc)))

        _log("about to call nextChannel(g, None)")
        try:
            c = ci.nextChannel(g, None)
            _log("nextChannel(g, None) returned: %r" % (c,))
        except BaseException as exc:
            _log("nextChannel(g, None) raised: %r (%s)" % (exc, type(exc)))
            c = None

        if c is not None:
            try:
                cn = ci.channelName(c)
                _log("channelName(c) returned: %r" % (cn,))
            except BaseException as exc:
                _log("channelName(c) raised: %r (%s)" % (exc, type(exc)))

    # separately, surf constants (much lower risk, no native calls)
    try:
        names = [n for n in dir(lwsdk) if n.startswith("SURF_")]
        _log("SURF_* constants (%d): %r" % (len(names), names))
    except BaseException as exc:
        _log("SURF_* probe raised: %r" % (exc,))

    _log("=== run end ===")


class mcp_diag5_master(lwsdk.IMaster):
    def __init__(self, context):
        super(mcp_diag5_master, self).__init__()

    def inst_copy(self, source):
        return None

    def inst_descln(self):
        return "Claude MCP diagnostic5 ring listener"

    def inst_acquire(self):
        self._comring = lwsdk.LWComRing()
        self._comring.ringAttach(lwsdk.LW_PORT_COMMAND_PORT, self, self.ring_event)
        _log("inst_acquire: ringAttach done")

    def inst_release(self):
        self._comring.ringDetach(lwsdk.LW_PORT_COMMAND_PORT, self)

    def ring_event(self, client_data, port_data, event_code, event_data):
        if event_code != 0:
            return
        try:
            data = self._comring.decodeData(('s:256',), event_data)
        except BaseException as exc:
            _log("decodeData raised: %r" % (exc,))
            return
        if not data:
            return
        m = _TOPIC_RE.match(data[0])
        if not m:
            return
        topic, rest = m.group(1), m.group(2)
        if topic != TOPIC:
            return
        _log("ring_event matched topic, calling _run()")
        try:
            _run()
        except BaseException as exc:
            _log("_run() raised at top level: %r (%s)" % (exc, type(exc)))

    def flags(self):
        return lwsdk.LWMAST_LAYOUT

    def event(self, ma):
        return 0.0


ServerTagInfo = [
    ("LW MCP Diag5", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Diag5", mcp_diag5_master): ServerTagInfo,
}
