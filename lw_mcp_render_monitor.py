"""
lw_mcp_render_monitor.py

Render-completion signal for ROADMAP.md item 6. Layout's Command Port
render commands (RenderFrame, RenderScene, RenderSelected) are one-way
fire-and-forget UDP sends (see lwcommandport/__init__.py's
_send_command - no response is ever read back), so there is no way to
know from the client side when a render actually finishes without
extending the read path. Firing RenderFrame and immediately assuming
success would just be guessing, which is exactly what ROADMAP.md item 6
calls out as the thing to avoid.

The real mechanism: register a custom "Frame Buffer" / Render Display
plug-in (lwsdk.IFrameBuffer / FrameBufferFactory), confirmed via
NewTek's official Python SDK docs (docs.lightwave3d.com/2025/
frame-buffer-class.html - fetched live since no docs ship with this
2019.1.5 install; this handler type's Python surface is not called out
as having changed across SDK versions). Real callbacks driven by the
render engine itself, not something we have to poll or guess at:

  - open(width, height): called when a rendering session begins.
  - write(r, g, b, a): called once per scanline as the frame renders.
  - close(): called when the rendering session is complete.
  - pause(display_name): called for F9/manual frame advance, but NOT
    during automatic (batch) rendering - useful signal on its own that
    a render is running non-interactively.

This plug-in ignores actual pixel data in write() - we don't need to
see the image, just know the render's state - and writes state to
_mcp_render_status.json on open()/close(). lw_mcp_ring.py's
"get_render_status" query reads that file and returns it over the
already-proven LWComRing read path, so no second polling mechanism is
needed on the client side beyond what lw_ping/_query already do.

OPEN QUESTION (see PLAN.md for what live testing finds): whether
open()/close() fire once per whole render session or once per frame
within a multi-frame RenderScene animation isn't precisely documented.
frame_count below increments on every open() so either behavior is
observable and distinguishable live rather than assumed.

SETUP (once per fresh Layout session):
  1. Utilities > Plugins > Add Plugins > lw_mcp_render_monitor.py
  2. Render > Render Globals (or F9's panel) > Render Display tab (the
     UI location for the active Frame Buffer/display server) > select
     "LW MCP Render Monitor". This is a one-time manual UI step, same
     as the Master Plugins activation dance the rest of this project
     already depends on - confirmed via the local build's command list
     that SetRenderDisplay/RenderDisplayOptions take no arguments (see
     lwcommandport/layout/__init__.py), so there's no way to select it
     over the network; it must be chosen once in the UI.
"""
import json
import os
import time

import lwsdk

__lwver__ = "11"

_HERE = os.path.dirname(os.path.abspath(__file__))
STATUS_PATH = os.path.join(_HERE, "_mcp_render_status.json")
DEBUG_LOG_PATH = os.path.join(_HERE, "_mcp_render_debug.log")


def _log(line):
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _write_status(payload):
    payload["updated"] = time.time()
    tmp_path = STATUS_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f)
    try:
        os.remove(STATUS_PATH)
    except OSError:
        pass
    os.rename(tmp_path, STATUS_PATH)


class mcp_render_monitor(lwsdk.IFrameBuffer):
    def __init__(self, context):
        super(mcp_render_monitor, self).__init__()
        self._frame_count = 0
        _log("mcp_render_monitor instantiated, context=%r" % (context,))

    # LWFrameBuffer -------------------------------------------------------
    def open(self, width, height):
        self._frame_count += 1
        _log("open: width=%d height=%d frame_count=%d" % (width, height, self._frame_count))
        _write_status({
            "rendering": True,
            "width": width,
            "height": height,
            "frame_count": self._frame_count,
        })
        return None

    def write(self, r, g, b, a):
        # Intentionally ignoring pixel data - we only care about the
        # open/close lifecycle as a completion signal.
        return None

    def close(self):
        _log("close: frame_count=%d" % self._frame_count)
        _write_status({
            "rendering": False,
            "frame_count": self._frame_count,
        })

    def pause(self, display_name):
        _log("pause: display_name=%r" % (display_name,))


ServerTagInfo = [
    ("LW MCP Render Monitor", lwsdk.SRVTAG_USERNAME | lwsdk.LANGID_USENGLISH),
]

ServerRecord = {
    lwsdk.FrameBufferFactory("LW_MCP_RenderMonitor", mcp_render_monitor): ServerTagInfo,
}
