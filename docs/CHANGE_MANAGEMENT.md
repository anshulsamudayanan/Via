# Change management, comparison and export (Stage 2, Milestone 6)

VIA turns explicit design changes into a new revision by **editing the user's original file in
place**. It never regenerates a board from its normalized model, which deliberately leaves things out.
The exported file is the original upload with only the changed objects' text edited.

## Flow

1. **Change set.** `POST /designs/{id}/change-sets` collects:
   - the changes of *accepted* optimization candidates made for the current revision, and/or
   - changes entered by the user.

   Each change names its target by the stable model id. VIA reads the `before` value from the parsed
   design; it is never taken from the client. VIA rejects:
   - unknown targets (422);
   - invalid values (422);
   - kinds that can't be exported (422, `not_exportable`);
   - two changes to the same object (409, `conflicting_changes`);
   - unaccepted or outdated candidates (409).
2. **Preview.** `GET /change-sets/{id}/preview` gives the metrics before and after, computed by
   applying the changes to VIA's model (`source: "simulated"`). This is not the exported file.
3. **Undo.** While a set is a draft (or failed), any change can be removed, or the set discarded.
4. **Apply.** `POST /change-sets/{id}/apply` queues a `pcb_export` job. It shares the worker
   lifecycle: heartbeat, reaper, retries, `worker_lost`. The job:
   - patches the original upload in the credential-free parser sandbox (`python -I -m via_opt.cli`);
   - verifies the patch (below);
   - stores the result as a new revision with `parent_revision_id = base`;
   - imports it through the normal pipeline.

   A change set applies as a whole or not at all. If any change is refused, the set fails and each
   refused change records why. Applying needs the base to still be the design's current revision
   (409, `base_not_current`).
5. **Follow-up analysis.** If the base revision had a successful analysis, the same analysis
   configuration (checks, options and profile snapshot, including KiCad DRC when it ran) is queued on
   the new revision.
6. **Compare.** `GET /designs/{id}/compare?base=&head=` compares two revisions:
   - object counts;
   - findings from each revision's latest analysis, matched by fingerprint: introduced, resolved,
     persisting.

   The response notes when the two analyses ran different checks.
7. **Download.** `GET /change-sets/{id}/download` returns the exported file, named
   `<original>-via-r<N>.<ext>`.
8. **Rollback.** `POST /change-sets/{id}/rollback` makes the base revision current again. Nothing is
   deleted: the exported revision, its findings and the change set stay in the history. Only the
   current revision's change set can be rolled back. Re-importing an already parsed revision (for
   example after a parser upgrade) never changes which revision is current.
9. **History.** `GET /designs/{id}/change-sets` lists change sets newest first.
   `GET /designs/{id}/lineage` lists every revision with its parent and the change set that produced it.

## What can be exported

The patcher is `services/pcb-engine/src/via_pcb/patch.py`.

| Change | Edit made in the file |
|---|---|
| `move_component` | Footprint/module `(at x y [angle])`. The angle is kept; pads and graphics are relative, so they follow |
| `rotate_component` | Footprint angle, plus every pad, `fp_text` and `property` angle. KiCad stores these as absolute angles |
| `set_track_width` | `(width w)` of the segment or arc |
| `move_via` | `(at x y)` of the via |
| `set_via_size` | `(size d)` and `(drill h)`. KiCad 5 vias without a drill get an explicit one |
| `set_outline_rect` | All top-level Edge.Cuts graphics are replaced by a rectangle in the file's own style: a copy of its first `gr_rect`, or four copies of its first `gr_line` (layer, width, stroke kept, fresh UUIDs or KiCad 5 tstamps). Refused when the outline includes footprint edges |
| `set_copper_layer_count` | **Not exportable**: needs re-routing in the EDA tool |

Targets are found by mapping VIA's stable ids to source nodes in file order, the same order the
adapter assigns ids in. If the object counts don't line up with VIA's parse, the patch is refused.
Numbers are written with up to 6 decimals, trailing zeros trimmed.

For project archives, only the board member is replaced. Every other member keeps its bytes and order.

## Verification

`via_opt.export.export_changes` parses the patched board again and compares it with
`apply(original, changes)`:

- every component position, rotation and pad position/rotation;
- every track (width, ends, layer, net);
- every via (position, diameter, drill, net);
- outline bounding box and closure;
- object counts.

Tolerance is 0.1 µm, and 0.001° for angles. Any mismatch fails the export
(`export_verification_failed`). VIA never hands out a file it hasn't verified.

The tests:

- An empty change set reproduces every test board byte for byte. These are the fixtures plus the real
  KiCad 5.1, 6, 7, 8 and 9 demo boards, up to 8.5 MB.
- Move, rotate, width, via size and via move are applied to every real board and verified.
- The line diff stays within the edited objects.

## Data

Migration `0008` adds:

- `change_sets` (base/result revision, export run, status `draft|applying|applied|failed|rolled_back`,
  result, error, who/when for apply and rollback);
- `design_changes.change_set_id`, `origin_candidate_id`, `status` (`proposed|applied|refused`) and
  `status_reason`, with a CHECK that a change belongs to exactly one candidate or change set;
- `design_revisions.parent_revision_id`;
- `pcb_export` as an `analysis_runs.kind`.

## Not done

- Exporting to formats other than KiCad.
- Moving tracks attached to a moved part (moves of connected parts show up as DRC findings after the
  follow-up analysis).
- Zone refill (KiCad refills zones when the file is opened; VIA's DRC runs without refilling).
