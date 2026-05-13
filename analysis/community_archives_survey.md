# Community archives — survey (wake 99)

The maintainer added five community-sourced archives to `info/` after
wake 87. None had been investigated. This survey is the verdict on
their relevance to the open RE blockers (state-10→11 gate, 35
unclaimed captured wire-types).

## What's in each

| Archive | Size | Format | Contents |
|---|---|---|---|
| `info/Gems.pak` | 69 KB | Zip (deflate) | 77 files: per-gem `gem.json` manifests + preview thumbnails |
| `info/server.pak` | 7.0 MB | Zip (deflate) | 669 `.datasheet` files under `server/sharedassets/springboardentitites/datatables/` |
| `info/datatables.7z` | 3.4 MB | 7-Zip (LZMA) | Same 669 `.datasheet` files as `server.pak`, just LZMA-compressed |
| `info/gems.7z` | 23 KB | 7-Zip (LZMA) | Likely the same `Gems.pak` content recompressed (not extracted) |
| `info/nw-data-browser.7z` | 13 MB | 7-Zip (LZMA) | Two community Python tools: `nw-pak-tool/` (CLI, ~20 KB source) and `nw-datasheet-explorer/` (Qt UI, ~30 KB source); plus a bundled copy of `server.pak` and pre-extracted samples |

## File-format learnings

### `.datasheet` binary layout (from community parser)

```
0x44  i32   column_count
0x48  i32   row_count
0x5C        column headers (12 bytes each):
              i32 hash, i32 name_str_offset, i32 column_type
            cell area (8 bytes per cell: i32 hash, i32 value)
            string heap (null-terminated UTF-8)
```

Column types: `1`=string, `2`=float, `3`=bool. Values are 4 bytes
in-band (or 4-byte offset into the string heap for strings).

### `.pak` format

PKZIP central-directory layout. Compression methods seen: `8`
(Deflate), `15` (Oodle — needs `oo2core_*_win64.dll`). Methods
`13`/`21` are XMEM (rare). Tooling for Oodle requires the
proprietary DLL from a separate source.

### Lumberyard gem context

Two gem manifests of note:

- `AmazonGamesSDK` (UUID `e281569de52849d99cc6ebfa214fa17b`,
  codename **Sonic**) — Amazon Desktop Application interface
- `JavelinCollisionFilters` (UUID `1A627930D86648A6A186002759F2D0B3`)
  — collision filtering, NOT network. **Important context: the
  `Javelin*` prefix is broader than the protocol library; it's
  also used for game-systems gems.** Class names alone don't
  imply network protocol involvement.

## Protocol-RE relevance

**Targeted strings sweep**: ran `strings -n 12` against
`info/server.pak`, `info/Gems.pak`, and `info/nw-data-browser.7z`
for: `REPClient`, `ClientConnectionMsg`, `RegistrationRequest`,
`TimeSynch`, `PingMsg`, `TypeIndex`, `SerializeContext`,
`InstallRegistrationHook`. **Zero matches** in any archive.

The community archives cover **content-server data** (monster
stats, damage tables, area definitions) and **content tooling**
(pak/datasheet parsers). They do not contain protocol/network
material.

### Specifically:

- ❌ Does NOT help with **state-10→11 gate** (predicate is in
  binary code, not in datatables)
- ❌ Does NOT help with **35 unclaimed captured wire-types**
  (need runtime registration data, not content tables)
- ❌ Does NOT contain a `MessageId`/`TypeIndex` lookup table

### Where they DO help, indirectly:

- ✅ The `.datasheet` parser is small (~70 LOC) and re-portable
  if we ever need to emulate world/asset queries that include
  baked content data (some captured wire-types ship binary
  blobs that *might* originate from datasheets, but no codec
  in the library currently parses them as datasheets).
- ✅ The Lumberyard gem-naming convention clarifies that
  "Javelin" alone is not a network namespace.

## Action

No code changes follow from this survey. Conclusion file lives
at this path so future wakes can skip re-investigating these
archives. If a captured-replay codec ever needs to decode
embedded datasheet blobs, port the parser at
`/tmp/nw_browser/datasheet.py` (~70 LOC, MIT-style community
clean-room) into `tools/datasheet.py`.
