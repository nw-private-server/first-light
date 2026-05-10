"""Decode a wire-type message body and pretty-print the result.

Surfaces `server.javelin.dispatch` as a developer CLI. Useful for
hand-checking a captured body, sanity-checking a generator's output,
or eyeballing what the codec library makes of an unknown blob.

Usage:

  # Hex on the command line
  tools/decode_message.py --type 0x15d --direction R --hex '00019d050003af9100000001'

  # Body in a file (raw bytes)
  tools/decode_message.py --type 0x65c --direction R --file /tmp/body.bin

  # Body on stdin (raw bytes)
  cat body.bin | tools/decode_message.py --type 0x18a6 --direction W --stdin

  # Pluck the Nth body of a type from the captured replay
  tools/decode_message.py --type 0x15d --direction R --replay-index 0

The default direction is R; pass `--direction W` for client-side bodies.
The output is the codec dataclass formatted with `pprint`.
"""

from __future__ import annotations

import argparse
import sys
import pprint
from pathlib import Path

# Make `server.*` importable when running from the repo root.
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server.javelin import dispatch  # noqa: E402


def _parse_type_id(raw: str) -> int:
    """Accept '0x15d', '15d', '349' (decimal)."""
    if raw.lower().startswith("0x"):
        return int(raw, 16)
    # Allow bare hex if non-decimal chars present
    if any(c in raw.lower() for c in "abcdef"):
        return int(raw, 16)
    return int(raw, 10)


def _read_body(args: argparse.Namespace) -> bytes:
    sources_set = sum(
        1 for x in (args.hex, args.file, args.stdin, args.replay_index is not None) if x
    )
    if sources_set != 1:
        raise SystemExit(
            "exactly one of --hex / --file / --stdin / --replay-index required"
        )
    if args.hex:
        return bytes.fromhex(args.hex.replace(" ", ""))
    if args.file:
        return Path(args.file).read_bytes()
    if args.stdin:
        return sys.stdin.buffer.read()
    if args.replay_index is not None:
        from server.javelin.replay_store import ReplayStore
        replay_path = REPO / "info" / "nw-login-safe-20260502-153840" / "messages-redacted.txt"
        if not replay_path.exists():
            raise SystemExit(f"replay file not found at {replay_path}")
        store = ReplayStore(replay_path)
        matching = [
            m for m in store.messages
            if m.type_id == args.type_id and m.direction == args.direction
        ]
        if not matching:
            raise SystemExit(
                f"no captured messages for type=0x{args.type_id:x} dir={args.direction}"
            )
        if args.replay_index >= len(matching):
            raise SystemExit(
                f"--replay-index {args.replay_index} out of range "
                f"(0..{len(matching) - 1})"
            )
        return matching[args.replay_index].body
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="decode_message",
        description="Decode a wire-type message via server.javelin.dispatch",
    )
    parser.add_argument(
        "-t", "--type", required=True,
        help="Wire type-id (0x15d, 15d, or 349)",
    )
    parser.add_argument(
        "-d", "--direction", default="R", choices=["R", "W"],
        help="R = server→client (default), W = client→server",
    )
    src = parser.add_argument_group("body source (pick one)")
    src.add_argument("--hex", help="Body as hex string (whitespace ignored)")
    src.add_argument("--file", help="Path to a file containing raw body bytes")
    src.add_argument("--stdin", action="store_true", help="Read body bytes from stdin")
    src.add_argument(
        "--replay-index", type=int, default=None, metavar="N",
        help="Pick the Nth captured message of this type+direction "
             "from the bundled replay (0-indexed)",
    )
    parser.add_argument(
        "--width", type=int, default=120,
        help="pprint output width (default 120)",
    )
    args = parser.parse_args(argv)
    args.type_id = _parse_type_id(args.type)

    body = _read_body(args)

    print(f"# type=0x{args.type_id:x}  direction={args.direction}  len={len(body)} B")
    decoded = dispatch.decode_replay_message(args.type_id, args.direction, body)
    if decoded is None:
        print(
            f"# no decoder registered for type 0x{args.type_id:x} "
            f"(intentionally skipped: 0x03 V3 response is server-emit-only, "
            f"or this type isn't in the dispatcher map)",
            file=sys.stderr,
        )
        return 1
    pprint.pp(decoded, width=args.width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
