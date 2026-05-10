# Two project arcs — how the loop converges on a milestone

A meta-doc on how the autonomous wake loop handles multi-step
deliverables. Two recent examples — the decompile cross-link
arc and the codec-audit gap arc — show the pattern of:

1. **Build the scaffold** in one wake (the framework that
   measures the gap).
2. **Bite off a wedge** in the next wake (close part of the
   gap with a single concrete artifact).
3. **Close the rest** in a final wake (cover the long tail).

Each wake produces a commit that's reviewable on its own; the
"big" milestone is the sum.

## Arc 1: decompile cross-link density 0% → 100%

**Premise**: 39 decompile files under `analysis/decomp_*.txt`,
but no surfacing on the dashboard of which analysis writeups
discussed each one. Visitors clicking a decomp had no way to
find the deeper context.

| Wake | Commit | Action | Density |
|---|---|---|---:|
| 129 | `015a59d` | Built `load_decompile_annotations()` in `build_site.py`: scans `analysis/*.md` for stem references; emits `related[]` per decomp into `data.json`. Site renders 📄 badges. | **12/39 (32%)** — only 16 decomps had any non-noise analysis doc referencing them at this point. |
| 130 | `3fc71ce` | `analysis/connection_lifecycle_decompiles.md`: a single overview doc mentioning 7 unreferenced decomps in their natural functional grouping (connection success/fail, V3 builder, CMS-fetch path). | **24/39 (62%)** |
| 131 | `7196886` | `analysis/wrapper_setter_decompiles.md`: covers the remaining 15 in their grouping (wrapper substate writers, state-13 writers, dispatchers, response handlers, FUN_* cluster). | **39/39 (100%)** |

**Pattern**:

- Wake 129's commit was *infrastructure* — `load_decompile_annotations()` + site rendering — but couldn't get to >32% on its own because the analysis docs to scan didn't exist yet.
- Wakes 130 and 131 were *content* — writeup files that existed primarily so the wake-129 annotation pass would surface them.
- The arc resolved in 3 wakes because the work split into "build the watcher" + "feed the watcher twice".

## Arc 2: codec audit gap counts 8+7 → 0+0

**Premise**: the codec library has 27 modules with `decode()`
and `encode()` functions, but no systematic check that every
codec has both structural-rejection tests (decode side) and
populated round-trip tests (encode side).

| Wake | Commit | Audit side | Gap count |
|---|---|---|---:|
| 125 | `158bc83` | Decode: built `codec_test_audit.md` (heuristic-bucketed scan). Added 6 rejection tests for 3 lowest-effort gaps. | **decode: 8 → 5** |
| 126 | `4e76657` | Decode: 9 rejection tests for the remaining 5 codecs. | **decode: 5 → 0** |
| 135 | `756428b` | Encode: built `codec_encoder_audit.md`. Added 3 populated round-trip tests for 3 lowest-effort gaps. | **encode: 7 → 4** |
| 136 | `08c7607` | Encode: 5 populated round-trip tests for the remaining 4 codecs (one had multi-variant encoders). | **encode: 4 → 0** |

**Pattern**:

- Wakes 125 and 135 were the *scaffold-and-wedge* — the audit
  doc identified the full gap list AND fixed the cheapest
  subset.
- Wakes 126 and 136 were the *close-the-tail* — fix the harder
  remaining gaps using the audit's per-codec analysis.
- Tests grew 320 → 325 → 334 → 341 → 346 (+26 in total).

The decoder and encoder arcs happened 10 wakes apart but used
the exact same shape: build → bite-off → close. After both
arcs, every codec module has both structural-rejection
coverage on `decode()` and populated-round-trip coverage on
`encode()`.

## Why the pattern works under wake constraints

Each wake has a ~30-minute time cap and produces one commit.
A direct attempt at "audit all codecs in one wake" would either
fail the cap or produce a brittle giant commit. Splitting into
scaffold-wedge-close gives:

- **Reviewability**: each commit ships one bounded thing
  (heuristic, lowest-effort fixes, hardest-effort fixes).
- **Failure tolerance**: a wake that gets stuck on the close
  step still leaves the scaffold and partial fixes shipped.
- **Incremental visibility**: the audit doc shows the gap
  count dropping wake-by-wake; visitors see velocity rather
  than a single big drop.

## Replicating the pattern

If a future wake faces a similar gap-fill task, the playbook is:

1. **Wake N**: write the audit/scaffold. Land 2-3 of the
   easiest fixes for visible momentum.
2. **Wake N+1**: tackle the harder remaining items.
3. **Wake N+2 (optional)**: surface the milestone on the
   dashboard (a stat card, a chart annotation, a README badge).

The wake-139 "0/0 audit gaps" stat card and the wake-137
shields.io badges both came out of the wake-136 close — they
were the dashboard surfacing step.

## Related files

- `analysis/codec_test_audit.md` (decoder audit)
- `analysis/codec_encoder_audit.md` (encoder audit)
- `analysis/connection_lifecycle_decompiles.md` (wake 130)
- `analysis/wrapper_setter_decompiles.md` (wake 131)
- `tools/build_site.py::load_decompile_annotations` (cross-link
  rendering)
