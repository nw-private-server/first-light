# Redacted New World Login Message Capture

This package is a text-only export for sharing wire shapes.
Sensitive spans are masked in both the hex and ASCII columns.

- source capture dir: `resources\captures\nw-3-26\messages\20260502-153840`
- sequence range: `0x0` through `0xb0`
- messages exported: `177`
- `W` means client to server; `R` means server to client.

Files:
- `messages-redacted.txt`: byte dumps with redacted spans shown as `XX` or `--`.
- `capture-index.tsv`: compact ordered index of the exported message files.
- `cap-list.txt`: output from the local `cap list` tool for the same range.
- `state-bundles-0x80-0xb0.txt`: `cap state-bundles` summary of the spawn-gate range.
- `redaction-report.txt`: pattern hit counts and masked byte count.
- `handoff-notes.md`: short sequence map and `isMasterPlayer` comparison notes.

The redacted dump is not intended to be parsed as binary. It is meant for protocol comparison.
