# Status: what's done, what's left, how to proceed

A quick-glance summary. For the full build log and evidence behind
every claim below, see `PLAN.md`; for the increment-by-increment
history and rationale, see `ROADMAP.md`; for setup and the current
tool list, see `README.md`.

## Where this stands

The connector is feature-complete against its original plan. All 10
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
  guessed timing) confirmed for both single-frame and multi-frame
  renders, and a scriptable `SetRenderDisplay` (a wrapped-method bug
  had made this look like a manual-only step).
- Modeler writes (a separate Command Port mechanism from Layout's).

## What's remaining

Two items left, roughly in order of how likely they are to be worth doing:

### 1. Bone chain traversal for `lw_get_hierarchy` - needs a rigged object

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

### 2. Modeler reads - confirmed dead end, not recommended

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
   restart (`Get-CimInstance Win32_Process -Filter "Name='python.exe'"`
   - check the `CreationDate` too, more than one `server.py` process
   isn't automatically a problem if their timestamps are days apart),
   then the documented Master Plugin activation flakiness (remove and
   re-add `lw_mcp_ring.py`, usually 1-3 tries), then - if that doesn't
   resolve it within 2-3 tries - whether Layout itself was restarted
   and setup step 1 (Command Port enable) needs redoing (check the
   title bar for `(CP: 9735)`, and whether the scene still has previous
   test items in it).
4. **A plug-in's UI selection can outlive its actual registration.**
   The Render Display dropdown (and, less obviously, the Master Plugins
   list) can keep showing a plug-in as selected/checked across a fresh
   Layout session even though the underlying class was never reloaded
   this session - it looks like it worked but silently doesn't. If a
   plug-in's effects aren't showing up despite the UI looking right,
   switch the selection away and back (or toggle off/on) rather than
   trusting the display. Relatedly: Add Plugins can report a file
   "could not be added" if that plug-in is currently active somewhere
   (e.g. the current Render Display) - switch away from it first, then
   reload, then switch back.
