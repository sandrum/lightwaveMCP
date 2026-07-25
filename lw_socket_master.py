"""
lw_socket_master.py - SUPERSEDED, do not use.

This was an early design that hand-rolled a TCP socket server inside a
LightWave Master-class plug-in, relying on a periodic "tick" event to
drain commands on the main thread. After reading LightWave 2019's actual
locally-installed Python SDK docs and source (sdk/lwpython2019.1.5.zip
and bin/lwsdk/pris/ in the LightWave install), it turned out:

1. No such tick/idle event is exposed to Python Master plug-ins (I could
   not find LWMASTER_TICK or any equivalent anywhere in the docs or
   shipped source - my original code guessed at a name that doesn't
   exist).
2. LightWave already ships an official mechanism for exactly this use
   case: the Command Port (lwsdk.LWCommandPort, and a bundled Python
   client at support/python/lwcommandport in the LightWave install).

The connector now uses that instead. See:
- lw_enable_command_port.py  (run once inside Layout to turn on the port)
- lw_mcp_query.py            (registered plug-in that answers read queries)
- server.py                  (external MCP bridge)
- PLAN.md / README.md        (current architecture and status)

This file is kept only so the history of how we got here isn't lost; it
is not loaded by anything and should not be added as a plug-in in
Layout.
"""
