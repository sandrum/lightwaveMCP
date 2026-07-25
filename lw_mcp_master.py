"""
lw_mcp_master.py

Registered Master-class plug-in that answers read-only queries sent over
the Command Port.

Why this replaces the lw_mcp_query.py Generic-plugin approach: testing
inside a live Layout session showed that CommandInput's command resolver
only recognizes real, pre-registered LightWave commands (native ones like
AddNull, or LWCommandFunc-class plug-ins) - a plain Generic-class plug-in
(lwsdk.IGeneric / GenericFactory) is NOT reachable by name through
CommandInput, even with a menu tag. Sending "CommandInput LW_MCP_Query
ping" reliably produced "Unknown command: LW_MCP_Query".

However, per the Master Class docs' own example (master.html), a Master
plug-in with LWMASTF_RECEIVE_NOTIFICATIONS gets an LWEVNT_COMMAND event
for input submitted through the Command Port, with the raw text available
via ma.data_as_string() - independent of whether that text resolves to a
real command. So instead of trying to register a new named command, this
plug-in listens for that event and inspects the raw string itself,
treating anything prefixed with MCP_QUERY: as its own mini protocol.

Wire format: external caller sends (via CommandInput):

    MCP_QUERY:<command> [optional single arg]

e.g. "MCP_QUERY:ping" or "MCP_QUERY:get_scene_info". This plug-in writes
its answer to _mcp_response.json next to this script (same file/protocol
lw_mcp_query.py used - server.py's polling logic is unchanged).

The "Unknown command" error LightWave prints for the unresolved
CommandInput text is expected and harmless - it happens after this
plug-in has already had its chance to react to the notification.
"""

import json
import os

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_response.json")

PREFIX = "MCP_QUERY:"


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


DEBUG_LOG_PATH = os.path.join(_HERE, "_mcp_debug.log")


def _log(line):
    with open(DEBUG_LOG_PATH, "a") as f:
        f.write(line + "\n")


class mcp_master(lwsdk.IMaster):
    def __init__(self, context):
        # NOTE: the SDK doc's own example shows __init__(self, context,
        # count), but the actual factory in this LightWave 2019.1.5 build
        # calls klass(context) with a single argument - confirmed via a
        # live TypeError ("__init__() takes exactly 3 arguments (2
        # given)") when the two-arg form was used.
        super(mcp_master, self).__init__()
        _log("mcp_master instantiated (context=%r)" % (context,))

    def flags(self):
        # LWMAST_LAYOUT (not LWMAST_SCENE) - persistent across scene
        # clearing, so it's instantiated once at load time rather than
        # only on scene load/clear events. LWMAST_SCENE masters may not
        # get created at all until a scene event happens, which would
        # explain event() never firing after just adding the plug-in.
        return lwsdk.LWMAST_LAYOUT | lwsdk.LWMASTF_RECEIVE_NOTIFICATIONS

    def event(self, ma):
        # Temporary instrumentation: log every event this plug-in ever
        # receives, so we can see empirically which eventCode values
        # actually fire and when, instead of guessing from docs.
        try:
            msg = ma.data_as_string()
        except Exception as exc:  # noqa: BLE001
            msg = "<data_as_string failed: %s>" % exc
        _log("event: code=%r msg=%r" % (ma.eventCode, msg))

        if ma.eventCode == lwsdk.LWEVNT_COMMAND:
            if msg and msg.startswith(PREFIX):
                _handle_query(msg[len(PREFIX):].strip())
        return 0.0


ServerTagInfo = [
    ("LW MCP Master", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.MasterFactory("LW_MCP_Master", mcp_master): ServerTagInfo,
}
