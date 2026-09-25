# Roadmap 2: controlling more of Layout

Context: `ROADMAP.md`'s original plan is fully done except Modeler
reads (a confirmed, documented dead end - see `PLAN.md`/`STATUS.md`).
The connector can create items, run any of the ~800 native Layout
commands, read back scene/selection/camera/light/transform/surface/
hierarchy state (including bone chains), animate via keyframes, manage
item relationships (parent/target/goal/pole), and drive render
automation with real completion signaling. This doc picks up from
there: the goal now is breadth - controlling as many real facets of
Layout as possible, not just the increments that happened to come up
along the way.

Grounded in a real survey of `lwcommandport/layout/__init__.py`'s
command list (not guessed at) - see the notes under each item for what
was actually found there. Same working method as before applies: live
verification only test-fresh items, Cmd History for anything ambiguous,
and real caution around any SDK traversal call given this project's one
documented crash (`LWChannelInfo`/`nextGroup`).

## Priority order

1. **Item visibility / render-inclusion - DONE.** `IncludeObject`,
   `ExcludeObject`, `IncludeLight`, `ExcludeLight` share the same
   `(itemid)` signature quirk as the `ParentItem`/`TargetItem` family -
   wrapped with the same `_set_reference_item` helper (resolve both
   arguments to numeric IDs) rather than assuming it would just work.
   Confirmed live end to end, via the actual UI panels, not just Cmd
   History: `lw_include_light`/`lw_exclude_light`/
   `lw_include_object_light`/`lw_exclude_object_light` all shipped as
   `server.py` tools. This turns out to control which objects a light
   illuminates (Light Properties > Objects tab, or equivalently an
   object's own Item Properties > Lights tab - the same underlying
   data either way). Confirmed the relationship is genuinely
   bidirectional and stays in sync: setting it from the light's side
   (`IncludeObject`) and later toggling it from the object's side
   (`ExcludeLight`) both correctly updated the same shared list entry,
   visible identically on both panels, not two separate lists that
   happened to agree once. See `PLAN.md` "Light/object visibility
   linking" for the full writeup.

2. **Load real geometry into Layout - DONE.** Shipped `lw_load_object`,
   wrapping the previously-unused `LoadObject(filename)` command.
   Confirmed live end to end: loaded a small rig-part `.lwo`
   (`connector_01.lwo`, from LightWave's own bundled Genoma content) -
   `lw_get_scene_info` showed the new item by name, `lw_get_transform`
   returned a valid position, and a screenshot confirmed real triangle
   geometry visible in the viewport, not just a placeholder entry.
   `filename` must be an absolute path readable by the LightWave
   process - no relative-path or content-directory resolution was
   tested. This was the single biggest capability gap in "control as
   many facets of Layout as possible" up to this point - previously
   only Nulls could be created directly, and real geometry needed a
   separate Modeler round-trip. See `PLAN.md` "Load real geometry into
   Layout" for the full writeup.

3. **Scene file I/O** - `SaveScene`, `LoadScene`, `ClearScene`,
   `SaveObject`, `SaveAllObjects` all exist and are unused. Natural
   pairing with item 2: once real content can be loaded, persistence
   matters. Everything built so far lives only in Layout's in-memory
   state until a human manually saves.

4. **Camera property writes** - `ZoomFactor`, `LensFStop`,
   `ApertureHeight`, `ShutterOpen`, `ShutterEfficiency`, `RollingShutter`
   all exist. `lw_get_camera_info` already reads all of this; there's no
   way to write it. Uses the same numeric-ID `SelectItem` pattern
   already proven for `lw_set_target`/`lw_set_parent` (see PLAN.md
   "ParentItem argument format" and "Second finding" for why resolving
   both the item and the value being set to numeric IDs matters, not
   just relying on `SelectItem(name)`). Camera before light since
   composition typically comes first in a real workflow.

5. **Light property writes** - `LightIntensity`, `LightColor`,
   `LightFalloffType`, `LightConeAngle`, `LightVisibleToCamera`,
   `LightCastsShadows` all exist. Same technique and effort tier as
   item 4, sequenced after it. Together, items 4 and 5 close the
   biggest remaining "reads but can't write" gap in the connector.

6. **Multi-item / bulk selection investigation** - `AddToSelection`
   was tested during earlier work (see PLAN.md) and appeared to do
   nothing observable - `lw_get_selection` showed no change after
   calling it. Worth a dedicated investigation before committing
   further: if it's fixable, it makes every write tool above more
   efficient (batch operations instead of one item at a time). If it's
   a genuine dead end like Modeler reads, better to document that now
   than assume multi-select works later. Placed after the core
   scene-building tools (2-5) since those are higher-value on their
   own regardless of how this turns out.

7. **IK chain configuration writes** - enable/disable "Full-Time IK"
   and related chain-level flags (visible in Motion Options > IK and
   Modifiers, e.g. "Unaffected by IK of Descendants" - the exact
   command names for these weren't confirmed in the item-1 survey and
   need their own look). Niche (rigging-specific) - `lw_set_goal`/
   `lw_set_pole` already cover the per-item goal/pole assignment; this
   is about the chain-level behavior around them.

8. **Surface/material writes** - genuinely new territory. No simple
   native command exists for this (`SurfaceEditor` in the command list
   just opens the UI panel, it doesn't take settable arguments). The
   real path is `LWSurfaceFuncs().setFlt()`/`setColorVMap()`/`setImg()`/
   `setMaterial()` etc - the same SDK class this connector already uses
   to *read* surfaces (`lw_get_surface_info`, via `lw_mcp_ring.py`).
   Writing through it would be a first for this project: every existing
   write goes through the one-way Command Port (`lw_run_command` and
   its wrappers), but this would go through the read-path's Master
   plugin instead, since that's where `lwsdk`'s surface API is actually
   accessible. Real architectural interest, real uncertainty about
   whether writes through that path behave as cleanly as reads have -
   deserves a dedicated session, not something to rush alongside the
   easier wins above.

9. **Keyframe/envelope reading** - `lw_get_transform` only reports the
   evaluated value at one point in time (now via the live playhead, see
   ROADMAP.md item 9); there's no way to see the actual keyframe
   structure of an item's channels - which frames have keys, what
   interpolation type each uses. Real value for inspecting existing
   animation rather than just sampling it. Last on purpose: this is
   `LWChannelInfo`-adjacent territory, the exact SDK area that has
   already crashed Layout outright once with no Python exception (see
   PLAN.md "LWChannelInfo crash"). Do this only with the same staged,
   cautious probing bone traversal got (ROADMAP.md item 11) - confirm
   the mechanism exists and a single call is safe before writing any
   real loop - once the rest of this list is solid.
