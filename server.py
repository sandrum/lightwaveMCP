"""
server.py

MCP bridge between Claude and LightWave Layout, built on LightWave's
official Command Port rather than a hand-rolled socket server.

- Writes (create/modify scene state) go straight through LightWave's own
  built-in commands (e.g. AddNull) via the bundled `lwcommandport` Python
  client (copied here from support/python/lwcommandport in the LightWave
  install - it's a plain-stdlib package, no LightWave runtime needed to
  import it).
- Reads go through a small registered plug-in (lw_mcp_query.py) that this
  script invokes via the Command Port's CommandInput command, then reads
  back from the JSON file that plug-in writes (_mcp_response.json, next
  to these scripts) - the Command Port itself is one-way/UDP, so this
  file is the only way to get data back out.

Prerequisites (see PLAN.md):
1. Layout running.
2. lw_enable_command_port.py has been run once inside Layout (turns on
   the Command Port on PORT below).
3. lw_mcp_query.py is loaded as a plug-in inside Layout.

Requires: pip install "mcp[cli]"
"""

import json
import os
import time

from mcp.server.fastmcp import FastMCP

from lwcommandport.layout import Layout

HOST = "localhost"
PORT = 9735  # must match lw_enable_command_port.py

_HERE = os.path.dirname(os.path.abspath(__file__))
RESPONSE_PATH = os.path.join(_HERE, "_mcp_response.json")

mcp = FastMCP("lightwave")


def _layout():
    return Layout(address=HOST, port=PORT)


def _query(command, arg=""):
    """Invoke lw_mcp_query.py inside Layout via CommandInput, then poll
    the response file it writes for a fresh answer."""
    before_mtime = os.path.getmtime(RESPONSE_PATH) if os.path.exists(RESPONSE_PATH) else None

    cmd_string = ("LW_MCP_Query %s %s" % (command, arg)).strip()
    _layout().CommandInput(cmd_string)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if os.path.exists(RESPONSE_PATH):
            mtime = os.path.getmtime(RESPONSE_PATH)
            if before_mtime is None or mtime > before_mtime:
                try:
                    with open(RESPONSE_PATH) as f:
                        return json.load(f)
                except (ValueError, OSError):
                    pass  # file mid-write; retry
        time.sleep(0.1)

    return {"error": "timed out waiting for LightWave's response file"}


@mcp.tool()
def lw_ping() -> str:
    """Check that LightWave's Command Port + query plug-in are reachable.
    Use this first, before trying anything else."""
    resp = _query("ping")
    return resp.get("result") or resp.get("error", "no response")


@mcp.tool()
def lw_get_scene_info() -> str:
    """Get basic info about the current LightWave scene (name, filename,
    and a list of object/light/camera item names)."""
    return json.dumps(_query("get_scene_info"))


@mcp.tool()
def lw_create_null(name: str = "MCP_Null") -> str:
    """Create a Null item in the current LightWave scene. This goes
    straight through LightWave's built-in AddNull command over the
    Command Port - no custom plug-in involved."""
    try:
        _layout().AddNull(name)
        return json.dumps({"result": "sent AddNull %s" % name})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    mcp.run()
