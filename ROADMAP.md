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

## 1b. Item transform query (position/rotation/scale)

Needs `lwsdk.LWChannelInfo()`, which exposes `nextGroup`/`groupName`/
`nextChannel`/`channelName`/`channelParent`/`channelEvaluate` - channels
are grouped (one group per item, matched via `channelParent(chan) ==
item_id`) rather than queried directly by item. Two things need live
probing before implementing: what sentinel value `nextGroup`/
`nextChannel` return at the end of iteration (None? 0? a NULL id?), and
resolving the same current-time question as above for
`channelEvaluate(chan, time)`. Same probe-plugin technique as roadmap
item 1 should resolve this quickly.

## 1c. Surface/material info query

Needs `lwsdk.LWSurfaceFuncs()` (`byName`, `getFlt`, `getInt`,
`getColorVMap`, etc.) plus the `SURF_*` channel constants (e.g. color,
luminosity, reflection) that identify which property `getFlt`/`getInt`
are reading - not yet found via introspection (they likely don't match
a "Surface" substring search the way class names do). Needs a
targeted `dir(lwsdk)` grep for `SURF_` specifically, then live
`byName()`/`getFlt()` probing the same way camera/light info was
confirmed.

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

## 3. Animation helpers built on what already works

`Position`/`Rotation`/`Scale`, `AddPosition`/`AddRotation`,
`CreateKey`/`DeleteKey`, `GoToFrame`, `AutoKey` are all proven-reachable
native commands (we already had to fight `AutoKey` once, so it's a known
quantity). Rather than making Claude chain raw `lw_run_command` calls,
wrap the common pattern - move to a position/rotation, create a key,
advance the frame - into one or two higher-level MCP tools.

Effort: small, mostly API design. Value: medium - a real quality-of-life
step once basic scene building and Modeler are solid, so I'd sequence it
after both.

## 5. Modeler read path (open research question, now unblocked)

Unlike Layout, I haven't found NewTek's equivalent of the `LWComRing`
sample for getting data back out of *Modeler* - its plugin architecture
is `CommandSequence`-based rather than the Master-plugin model Layout
uses, so the same trick may not directly apply. This needs the same kind
of live-tested investigation that solved Layout's read path (which took
two ruled-out dead ends before finding the real mechanism). Now that the
Modeler write path (item 2) is done, this is the natural next research
item - worth checking whether `LWComRing`/`LW_PORT_COMMAND_PORT` is
actually Layout-specific or works from Modeler's Master-equivalent too,
before assuming a from-scratch mechanism is needed.

Effort: unknown until investigated - could be quick if there's a
similarly-documented sample, could be another multi-attempt dead-end
hunt like Layout's was. Value: high now that modeling automation exists.

## 6. Render / camera automation with completion signaling

Camera setup and render-kickoff commands exist natively. The missing
piece is a way for Claude to know a render finished (or failed) rather
than firing a one-way command and guessing - which means extending the
read path (step 1's mechanism) with a render-status query, possibly
polling, once that plumbing is proven out further.

Effort: medium-high (needs the read path extended and a polling/status
convention). Value: high but more speculative - lowest priority until
1 and 2 are solid.

## Recommended order

1. ~~Layout read queries (selection, camera/light)~~ - done
2. ~~Modeler write path~~ - done
3. Item transform query (1b) and surface/material query (1c) - the two
   read queries descoped from step 1, now their own well-scoped items
4. Animation helper tools
5. Modeler read path research - now unblocked
6. Render/camera automation

Rationale: started with the cheapest, lowest-risk extensions of what's
already proven (1, done), then opened the next major surface using a
pattern already validated once (2, done). Next up: close out the
remaining read queries now that the probing technique is proven (3),
then build convenience on top of a now-broader foundation (4), before
taking on the two genuinely open-ended research items (5, 6).
