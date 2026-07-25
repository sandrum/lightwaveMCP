"""
lw_mcp_query.py

A small registered LightWave Generic plug-in that answers read-only
queries about the current scene. LightWave's Command Port (see
lw_enable_command_port.py) is one-way / fire-and-forget (it's UDP, no
response channel), so this plug-in's answer can't be sent directly back
over the network. Instead it writes a JSON response to a fixed file next
to this script, which the external server.py polls after issuing the
query.

Invocation: once this plug-in is loaded (Utilities > Plugins > Add
Plugin), it becomes invokable by its internal name, exactly like any
built-in command (e.g. "AddNull"). server.py triggers it externally via
the Command Port's CommandInput command:

    CommandInput LW_MCP_Query ping
    CommandInput LW_MCP_Query get_scene_info

The text after "LW_MCP_Query" is passed through to this plug-in as
ga.commandArguments() (see the "add_null.py" example in the SDK's
Anatomy doc for this same pattern).

VERIFY: this was written directly against the LightWave 2019 Python SDK
docs and the lwsdk source shipped with this install (bin/lwsdk/pris/),
but has not yet been run inside Layout. See PLAN.md for the load/debug
step where this gets checked for real.
"""

import json
import os

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_response.json")


def _write_response(payload):
    tmp_path = RESPONSE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f)
    # best-effort atomic-ish replace (os.replace is py3-only; this runs
    # under LightWave's embedded Python 2.7, so fall back to remove+rename)
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


class mcp_query(lwsdk.IGeneric):
    def __init__(self, context):
        super(mcp_query, self).__init__()

    def process(self, ga):
        if not ga.valid():
            return lwsdk.AFUNC_OK

        raw_args = ga.commandArguments()
        parts = (raw_args or "ping").split(None, 1)
        command = parts[0]

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
        return lwsdk.AFUNC_OK


ServerTagInfo = [
    ("LW MCP Query", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.GenericFactory("LW_MCP_Query", mcp_query): ServerTagInfo,
}
