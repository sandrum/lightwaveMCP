"""
lw_diag_items.py (v2 - defensive)

One-shot diagnostic Generic plug-in. Writes to a HARDCODED absolute path
(not derived from __file__, in case that's not set reliably when Layout
loads a script plug-in) at every stage, so we can tell exactly how far
execution gets even if something later throws.
"""
OUT_PATH = r"C:\Users\sandr\IdeaProjects\LightwaveMCP\_diag_items.txt"

with open(OUT_PATH, "w") as f:
    f.write("stage 0: script started\n")

import time
with open(OUT_PATH, "a") as f:
    f.write("stage 1: time imported, now=%s\n" % time.ctime())

try:
    import lwsdk
    with open(OUT_PATH, "a") as f:
        f.write("stage 2: lwsdk imported ok\n")
except Exception as exc:
    with open(OUT_PATH, "a") as f:
        f.write("stage 2 FAILED: %r\n" % (exc,))
    raise

try:
    ii = lwsdk.LWItemInfo()
    with open(OUT_PATH, "a") as f:
        f.write("stage 3: LWItemInfo() ok: %r\n" % (ii,))
except Exception as exc:
    with open(OUT_PATH, "a") as f:
        f.write("stage 3 FAILED: %r\n" % (exc,))
    raise

lines = []
for label, item_type in (
    ("OBJECT", lwsdk.LWI_OBJECT),
    ("LIGHT", lwsdk.LWI_LIGHT),
    ("CAMERA", lwsdk.LWI_CAMERA),
):
    try:
        it = ii.first(item_type, lwsdk.LWITEM_NULL)
        while it != lwsdk.LWITEM_NULL:
            lines.append("%s: %s" % (label, ii.name(it)))
            it = ii.next(it)
    except Exception as exc:
        lines.append("%s: ERROR %r" % (label, exc))

with open(OUT_PATH, "a") as f:
    f.write("stage 4: enumeration done\n")
    f.write("\n".join(lines) + "\n")
    f.write("DONE\n")
