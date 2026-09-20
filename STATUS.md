# Status: what's done, what's left, how to proceed

A quick-glance summary. For the full build log and evidence behind
every claim below, see `PLAN.md`; for the increment-by-increment
history and rationale, see `ROADMAP.md`; for setup and the current
tool list, see `README.md`.

## Where this stands

The connector is feature-complete against its original plan. All 9
roadmap items are done except one confirmed dead end (Modeler reads).
Everything below has been verified live against a real running
LightWave 2019.1.5 session, not just reasoned about from SDK docs -
this project's docs are demonstrably out of sync with this build in
places, so nothing here is trusted until it's been tested against the
real thing.

**Working today** (see `README.md` for the full tool-by-tool list):
- Layout writes: create items, run any of the ~800 native commands,
  keyframe animation.
- Layout reads: scene info, selection, camera/light info, transform,
  surface/material info, item hierarchy, live playhead time.
- Item relationships: parent, target, IK goal/pole - all four confirmed
  live, including a fix for two non-obvious LightWave argument quirks
  (numeric IDs vs. names; `SelectItem` not resolving names reliably for
  Camera/Light).
- Render/camera automation, including real completion signaling (not
  guessed timing).
- Modeler writes (a separate Command Port mechanism from Layout's).

## What's remaining

Three items, roughly in order of how likely they are to be worth doing:

### 1. Multi-frame `RenderScene` progress tracking - untested

`lw_get_render_status` is proven for single-frame renders (`lw_render_frame`).
Whether `frame_count` correctly increments across a multi-frame
`RenderScene` render has never actually been tried.

**To proceed:** trigger `lw_render_scene()` with a frame range that
renders more than one frame, poll `lw_get_render_status()` during it,
and confirm `frame_count` increments per frame rather than jumping
straight to done or stalling. Low risk, low effort - this is just
verification, not new code, unless something unexpected turns up.

### 2. Bone chain traversal for `lw_get_hierarchy` - needs a rigged object

`lw_get_hierarchy` currently reports item-level parent/target/goal/pole
for every Object/Light/Camera, but does not walk bone chains *within*
an object (`LWItemInfo.first(LWI_BONE, object)` / `next()` is the
likely mechanism, unconfirmed). No boned object has been available in
any session so far to test against.

**To proceed:** get (or build in Modeler) an object with a real bone
setup, load it into Layout, then extend `_get_hierarchy()` in
`lw_mcp_ring.py` to also traverse `LWI_BONE` for each object. **Treat
this with real caution, not routine extension** - this project has a
documented case (`LWChannelInfo`/`nextGroup`, see `PLAN.md`) of an SDK
traversal call reproducibly crashing Layout entirely, with no Python
exception and no warning. Test incrementally against a real boned
object, and be ready to stub it back out (as `_probe_channels` was)
rather than push through a suspicious result.

### 3. Modeler reads - confirmed dead end, not recommended

Thoroughly investigated (three independent methods, including against
NewTek's own bundled sample plug-in) and confirmed blocked: Modeler has
no `LWComRing`-equivalent, and its network Command Port only reaches
native/compiled commands, not Python-registered ones. See `PLAN.md`
"Modeler read path" for the full writeup.

**To proceed, if ever:** only worth retrying given new information -
a NewTek support answer, or a newer LightWave version's SDK adding a
Modeler equivalent of `LWComRing`/Master plugins. A real but limited
substitute already exists: reading saved `.lwo` files directly from
disk (bypasses Modeler's Python API, only reflects saved state).

## Working method, if picking this back up

This project's real workflow, proven out over many rounds: guessing
from static SDK docs or plausible-sounding method signatures has
repeatedly been wrong (see `PLAN.md` for several confirmed dead ends).
What has reliably worked:

1. **Live-test everything** against a real running Layout/Modeler
   session - a fresh, untouched test item, not one a human has also
   touched manually in the meantime (a false "success" from that mix-up
   cost real time during the reparenting investigation).
2. **When a command's behavior is ambiguous**, reach for Utilities >
   Commands > Cmd History early - it logs the literal native command
   any UI action runs, and comparing a known-working manual action
   against a failed automated attempt has twice given a one-shot
   ground-truth answer where guessing the argument format would have
   taken many more rounds.
3. **When Layout stops responding as expected**, check in this order:
   a stale `server.py` process from an incomplete Claude Desktop
   restart (`Get-CimInstance Win32_Process -Filter "Name='python.exe'"`),
   then the documented Master Plugin activation flakiness (remove and
   re-add `lw_mcp_ring.py`, usually 1-3 tries), then - if that doesn't
   resolve it within 2-3 tries - whether Layout itself was restarted
   and setup step 1 (Command Port enable) needs redoing (check the
   title bar for `(CP: 9735)`).
