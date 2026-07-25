"""
server.py

MCP bridge server between Claude and LightWave. Run this as a standalone
process (Claude Desktop launches it via stdio, per claude_desktop_config.json
- see README.md). It has no direct dependency on LightWave: it just opens a
plain TCP connection to the socket server that lw_socket_master.py runs
inside LightWave Layout, and exposes that as MCP tools.

Requires: pip install "mcp[cli]"
"""

import json
import socket

from mcp.server.fastmcp import FastMCP

LW_HOST = "127.0.0.1"
LW_PORT = 9799

mcp = FastMCP("lightwave")


def _send(command: str, **params) -> dict:
    """Open a short-lived TCP connection to the LightWave plugin, send one
    JSON command, and read back one JSON response line."""
    try:
        with socket.create_connection((LW_HOST, LW_PORT), timeout=15) as sock:
            payload = json.dumps({"command": command, "params": params}) + "\n"
            sock.sendall(payload.encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            line, _, _ = buf.partition(b"\n")
            if not line:
                return {"error": "no response from LightWave (empty read)"}
            return json.loads(line.decode("utf-8"))
    except ConnectionRefusedError:
        return {
            "error": (
                "Could not connect to LightWave on "
                f"{LW_HOST}:{LW_PORT}. Is Layout running with the "
                "MCP_Socket_Master plugin loaded and enabled?"
            )
        }


@mcp.tool()
def lw_ping() -> str:
    """Check that LightWave's socket server is reachable. Use this first to
    confirm the connection is working before trying anything else."""
    resp = _send("ping")
    return resp.get("result") or resp.get("error", "no response")


@mcp.tool()
def lw_get_scene_info() -> str:
    """Get basic info about the current LightWave scene (items, layers)."""
    resp = _send("get_scene_info")
    return json.dumps(resp)


@mcp.tool()
def lw_create_null(name: str = "MCP_Null") -> str:
    """Create a Null item in the current LightWave scene."""
    resp = _send("create_null", name=name)
    return json.dumps(resp)


if __name__ == "__main__":
    mcp.run()
