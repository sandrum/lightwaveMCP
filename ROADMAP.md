# Roadmap: what to build next

Context: the core connector is done and verified live - Layout writes
(`lw_create_null`, `lw_run_command`) and Layout reads (`lw_ping`,
`lw_get_scene_info`, via the `LWComRing`-based `lw_mcp_ring.py`) all work
end to end. See `PLAN.md` for how that was proven and `README.md` for
setup. This doc lists the realistic next increments, in the order I'd
tackle them, with why.

## 1. More Layout read queries - DONE

Shipped and confirmed live: `lw_get_selection`, `lw_get_camera_info`,
`lw_get_light_info`. Found via three rounds of live introspection
(temporary `lw_mcp_diag.py`/`diag2`/`diag3` probe plugins, since the
static SDK docs don't cover exact method signatures and have already
been shown to be out of sync with this build):

- `LWItemInfo().selected(item)` is the reliable per-item selection
  signal - `flags() & LWITEMF_SELECTED` was tested and does **not**
  reflect actual selection state despite the name (returned the same
  value for every item regardless of what was actually selected).
- `LWCameraInfo`/`LWLightInfo`'s animatable properties (focal length,
  f-stop, fov, zoom, color, intensity, range) need a second `time`
  argument beyond the item ID - confirmed working with `time=0.0`.
  Non-animated properties (`resolution`, `falloff`, `type`) take just
  the item ID.
- `LWLightInfo().color()` returns a `PCore::Vector` SWIG object, not
  directly JSON-serializable - converted via `.x`/`.y`/`.z`.

**Known limitation, carried forward:** these tools evaluate animatable
values at `time=0.0` (scene start), not the live playhead position.
Querying LightWave's actual current time from Python is still an open
question - fine for non-animated cameras/lights, wrong for animated
ones. Worth solving before building on top of this further.

**Descoped this round** (see items below): item transform
(position/rotation/scale) and surface/material info. Transform needs
`LWChannelInfo` group/channel traversal with unclear sentinel values and
the same time-query problem; surface needs `SURF_*` constants that
weren't found in the introspection pass. Promoted to their own roadmap
items below rather than guessed at.

## 1b. Item transform query (position/rotation/scale) - DONE

Turned out not to need `lwsdk.LWChannelInfo()`/`nextGroup` at all - that
path is confirmed to crash Layout (see `PLAN.md`), but tracking down
NewTek's real SDK docs (etwright.org/lwsdk, since none ship with this
install) found that `LWItemInfo` already has a direct `param(item,
param_type, time)` call for exactly this. Real-world third-party Python
plugin code confirmed the Python calling convention. Shipped as
`lw_get_transform`, confirmed live against a real item including after
moving it (not just reading defaults) - see `PLAN.md`.

## 1c. Surface/material info query - DONE

Shipped as `lw_get_surface_info`, using `lwsdk.LWSurfaceFuncs()`
(`byName`, `getFlt`) plus the `SURF_*` channel constants. Calling
conventions confirmed via the same real-world Python plugin code used
for 1b. Confirmed live end to end against a real object with a real
surface (built a unit box in Modeler, loaded it into Layout, queried
its "Default" surface) - see `PLAN.md` for the full values returned.
One minor open question: the `smoothing` value's sign/scale under the
newer Principled BSDF shading model isn't fully decoded yet, but the
mechanism itself is proven safe.

## 2. Modeler write path - DONE

Shipped and confirmed live: `modeler_run_command`, mirroring
`lw_run_command` using the previously-unused `Modeler` class in
`lwcommandport/modeler/__init__.py` (booleans, extrude tools, mesh
cleanup, skinning, cloning/arrays, file ops). Sent `command="new"`,
Modeler's title bar changed from "Unnamed" to "Unnamed 1", confirming a
real new object layer was created.

Two things that didn't go as expected, both documented in `PLAN.md`:

- Enabling Modeler's Command Port really is a different mechanism from
  Layout's, as predicted - `lwsdk.ModCommand()` + executing
  `"ENABLECOMMANDPORT"` (see `lw_enable_modeler_command_port.py`, using
  port 9736). But loading the script via Add Plugins only *registers*
  it as a "Modeling Command" - it doesn't auto-run like Layout's Generic
  single-shot scripts do. It has to be separately invoked via Utilities
  > Additional afterward.
- `ModCommand.execute()`'s reported result code is unreliable - it said
  "failure" both for a genuinely free port and for one already
  successfully bound. Confirmed via a UDP bind-conflict test that it
  actually worked regardless. Third confirmed SDK/binding bug found this
  project, after `LWMessageFuncs.info()` and `IMaster.__init__`'s
  argument counts.

## 4. Animation helpers built on what already works - DONE

Shipped `lw_set_keyframe(name, frame, position, rotation, scale)`,
wrapping `SelectItem`/`GoToFrame`/`Position`/`Rotation`/`Scale`/
`CreateKey` into one call. Confirmed live on a fresh Null: keyed frame 0
at (0,0,0) and frame 30 at (5,5,5), then scrubbed to frame 15 and saw an
interpolated (3.104, 3.104, 3.104) - real proof the item animates between
keys, not just that two writes succeeded. See `PLAN.md` for the full
writeup, including a documented rotation-units mismatch (degrees on
write vs. radians on read).

## 5. Modeler read path - RESEARCHED, confirmed blocked (no known workaround)

Investigated thoroughly and live-tested; see `PLAN.md` for the full
writeup. Summary: Modeler has no Master-plugin/`LWComRing` equivalent at
all (confirmed via the local install's file layout and NewTek's SDK
docs - Modeler's Python plugin architecture is `CommandSequence`-only).
The natural workaround - invoke a custom `CommandSequence` plug-in by
name over the network Command Port, the same way built-in commands like
"new" already work via `modeler_run_command` - does not work. Confirmed
three independent ways, including against NewTek's own bundled sample
plug-in (not just this project's code), that the network Command Port
only reaches native/compiled commands, not Python-registered ones. This
is the same failure mode that ruled out Layout's first read-path attempt,
except Modeler has no `LWComRing`-style escape hatch.

**Status: blocked with no known path forward**, short of NewTek adding a
Modeler equivalent of `LWComRing`/Master plugins, or documentation
surfacing a mechanism this investigation didn't find. A real but limited
substitute exists: reading saved `.lwo` files directly from disk (bypasses
Modeler's Python API, only reflects saved state).

Effort already spent: thorough (SDK docs research + live testing with
three independent methods). Not recommending further time here without
new information (e.g. a NewTek support answer or a newer LightWave
version's SDK).

## 6. Render / camera automation with completion signaling - DONE

Shipped `lw_render_frame`, `lw_render_scene`, `lw_abort_render`,
`lw_set_camera_resolution`, and `lw_get_render_status`. The last one is
the real deliverable here: a genuine completion signal instead of
guessing after firing a one-way render command, built on
`lwsdk.IFrameBuffer` (NewTek's "Render Display" plug-in architecture -
found via NewTek's official docs, not live probing), which gets real
open()/close() callbacks from the render engine itself. Requires a
one-time manual step to select the plug-in as the active Render Display
(no networked way to do this - confirmed via the local command list).
Live-verified twice: once by hand via lw_run_command before the tools
were loaded, once fully through the new tools (set resolution to
640x360, triggered a render, watched rendering go true -> false with
matching resolution/frame_count). See PLAN.md for the full writeup.
Not yet tested: multi-frame RenderScene progress tracking.

## Recommended order

1. ~~Layout read queries (selection, camera/light)~~ - done
2. ~~Modeler write path~~ - done
3. ~~Item transform query (1b) and surface/material query (1c)~~ - done
4. ~~Animation helper tools~~ - done
5. ~~Modeler read path research~~ - researched, confirmed blocked
6. ~~Render/camera automation~~ - done

Rationale: started with the cheapest, lowest-risk extensions of what's
already proven (1, done), then opened the next major surface using a
pattern already validated once (2, done). Item 3 turned out to need a
real docs lookup rather than more live probing - once that was done
(see PLAN.md), both sub-items shipped quickly and safely. Item 5 was
investigated thoroughly and turned out to be a genuine dead end, not
just an unexplored option - documented rather than left open. Item 4
built convenience on top of proven native commands and was the fastest
item yet, confirming the project's core mechanisms are now solid. Item
6 needed one more real docs lookup (the Frame Buffer/Render Display
plug-in architecture) rather than guessing at a polling scheme, closing
out every item originally on this list.
