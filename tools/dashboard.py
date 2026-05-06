"""Live status dashboard for the New World private-server test loop.

Surfaces only the meaningful signals from three noisy terminals
(auth_mock, rep_responder, frida_capture) into a single curses TUI.

Usage
-----
    python tools/dashboard.py

Prerequisites
-------------
- Python 3.11+ (uses ``X | None`` annotations).
- Windows users: ``pip install windows-curses`` (stdlib ``curses`` is
  POSIX-only). On macOS/Linux the stdlib ``curses`` works as-is.

What each pane shows
--------------------
- **rep_responder**  -- discovers the newest ``capture/responder_*.log``.
  Reports V3 received/sent counts, substitution-context armed flag,
  replay queue progress, heartbeat count, and any ``[ch=3 sysmsg=3]``
  disconnect lines or warnings/errors.

- **frida**  -- discovers the newest ``capture/<timestamp>_*/session.log``.
  Reports rep.ready value with the last 5 transitions, last ``[gm-destroy]``
  reason + offset, the last 3 unique wrapper-state values, the last
  ``[gameconn-vt 0x2d0] SetProperty`` and ``[gameconn-vt 0x110]
  SetVersionString`` payloads, and the v3-resp-receive fire count.

- **auth_mock**  -- discovers the newest
  ``capture/auth_mock_logs/YYYYMMDD.log``. Reports total request count,
  the last 5 endpoints hit, and any 4xx/5xx responses seen.

Bottom status bar
-----------------
- Session age (time since the first log line we observed).
- Most-recent timestamp seen across the three logs.
- A single-line "biggest concern right now" derived from the parsed
  signals (e.g. ``"V3 not yet received (waiting on client)"``).

Keys
----
- ``q``  quit.
- ``r``  re-discover the latest log files (use after launching a fresh run).

Implementation notes
--------------------
- Read-only on logs; never launches/kills any of the three programs.
- Resilient to log rotation: if the discovered file's path or inode
  changes between refreshes, we re-discover and seek to start.
- Refreshes at ~5 Hz (200 ms tick), tailing each file from its last
  saved offset rather than re-reading from the top.
"""

from __future__ import annotations

import curses
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Deque

PROJECT_DIR = Path(__file__).resolve().parents[1]
CAPTURE_DIR = PROJECT_DIR / "capture"
AUTH_LOGS_DIR = CAPTURE_DIR / "auth_mock_logs"

REFRESH_HZ = 5.0
TICK_S = 1.0 / REFRESH_HZ

# ---------------------------------------------------------------------------
#  Tail abstraction (resilient to log rotation)
# ---------------------------------------------------------------------------


class Tailer:
    """Tails a file by absolute path, surviving rotation.

    On each ``read_new_lines()`` call we yield any lines appended since
    the last call. If the path changes (because ``re_discover()`` swaps
    in a fresh log) or the inode changes (file replaced underneath us),
    we transparently re-open and start from offset 0.
    """

    def __init__(self) -> None:
        self.path: Path | None = None
        self._fh = None
        self._inode: int | None = None
        self._pos: int = 0

    def set_path(self, path: Path | None) -> None:
        if path == self.path:
            return
        self.close()
        self.path = path
        self._pos = 0
        self._inode = None

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
        self._fh = None

    def _ensure_open(self) -> bool:
        if self.path is None or not self.path.is_file():
            return False
        try:
            st = self.path.stat()
        except OSError:
            return False
        # If a previously-opened file got truncated/replaced, restart
        # from the top so we don't miss the new run's banner.
        if self._fh is not None and self._inode is not None:
            if st.st_ino != self._inode or st.st_size < self._pos:
                self.close()
                self._pos = 0
                self._inode = None
        if self._fh is None:
            try:
                self._fh = open(
                    self.path, "r", encoding="utf-8", errors="replace"
                )
            except OSError:
                return False
            self._inode = st.st_ino
            self._fh.seek(self._pos)
        return True

    def read_new_lines(self) -> list[str]:
        if not self._ensure_open():
            return []
        out: list[str] = []
        try:
            while True:
                line = self._fh.readline()
                if not line:
                    break
                # Defer partial trailing lines (no newline yet) until next tick
                if not line.endswith("\n"):
                    # Rewind so we re-read this line in full next time
                    self._fh.seek(self._pos)
                    break
                self._pos = self._fh.tell()
                out.append(line.rstrip("\r\n"))
        except OSError:
            self.close()
        return out


# ---------------------------------------------------------------------------
#  Discovery
# ---------------------------------------------------------------------------


def newest(paths: list[Path]) -> Path | None:
    paths = [p for p in paths if p.is_file()]
    if not paths:
        return None
    return max(paths, key=lambda p: p.stat().st_mtime)


def discover_responder() -> Path | None:
    return newest(list(CAPTURE_DIR.glob("responder_*.log")))


def discover_frida_session() -> Path | None:
    return newest(list(CAPTURE_DIR.glob("*/session.log")))


def discover_auth_mock() -> Path | None:
    if not AUTH_LOGS_DIR.is_dir():
        return None
    return newest(list(AUTH_LOGS_DIR.glob("*.log")))


# ---------------------------------------------------------------------------
#  Parsed-state dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ResponderState:
    path: Path | None = None
    first_ts: str = ""
    last_ts: str = ""
    v3_received: int = 0
    v3_sent: int = 0
    substitution_armed: bool = False
    replay_total: int = 0
    replay_remaining: int | None = None
    heartbeat_count: int = 0
    disconnect_seen: bool = False
    last_warning: str = ""
    last_error: str = ""
    handshake_complete: bool = False


@dataclass
class FridaState:
    path: Path | None = None
    first_ts: str = ""
    last_ts: str = ""
    rep_ready: int | None = None
    ready_transitions: Deque[str] = field(default_factory=lambda: deque(maxlen=5))
    last_gm_destroy: str = ""
    wrapper_states: Deque[int] = field(default_factory=lambda: deque(maxlen=3))
    last_set_property: str = ""
    last_version_string: str = ""
    v3_resp_receive_count: int = 0
    last_log_line: str = ""


@dataclass
class AuthMockState:
    path: Path | None = None
    first_ts: str = ""
    last_ts: str = ""
    request_count: int = 0
    last_endpoints: Deque[str] = field(default_factory=lambda: deque(maxlen=5))
    error_responses: Deque[str] = field(default_factory=lambda: deque(maxlen=5))
    last_status: str = ""


# ---------------------------------------------------------------------------
#  Line parsers (one per pane)
# ---------------------------------------------------------------------------

# rep_responder format:  "HH:MM:SS [LEVEL] message..."
_RX_RESP_TS = re.compile(r"^(\d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)$")
_RX_REPLAY_ARMED = re.compile(r"replay queue armed: (\d+) R-msgs")
_RX_REPLAY_REMAINING = re.compile(r"remaining=(\d+)")
_RX_HEARTBEAT_ALIVE = re.compile(r"heartbeat alive: count=(\d+)")
_RX_DISCONNECT = re.compile(r"\bch=3 sysmsg=3\b")


def update_responder(state: ResponderState, line: str) -> None:
    m = _RX_RESP_TS.match(line)
    if not m:
        return
    ts, level, msg = m.group(1), m.group(2), m.group(3)
    if not state.first_ts:
        state.first_ts = ts
    state.last_ts = ts

    if "handshake complete" in msg:
        state.handshake_complete = True
    if "V3 RegistrationRequest #" in msg and "received" in msg:
        state.v3_received += 1
    if msg.startswith(">> V3RegistrationResponse"):
        state.v3_sent += 1
    if "substitution_ctx armed" in msg:
        state.substitution_armed = True

    m2 = _RX_REPLAY_ARMED.search(msg)
    if m2:
        state.replay_total = int(m2.group(1))
        state.replay_remaining = state.replay_total

    if msg.startswith(">> replay seq="):
        m3 = _RX_REPLAY_REMAINING.search(msg)
        if m3:
            state.replay_remaining = int(m3.group(1))

    m4 = _RX_HEARTBEAT_ALIVE.search(msg)
    if m4:
        state.heartbeat_count = int(m4.group(1))
    elif "[HEARTBEAT START]" in msg:
        state.heartbeat_count = max(state.heartbeat_count, 1)

    if _RX_DISCONNECT.search(msg):
        state.disconnect_seen = True

    if level == "WARNING":
        state.last_warning = msg[:200]
    elif level == "ERROR":
        state.last_error = msg[:200]


# frida session.log format:  "[HH:MM:SS.mmm] message..."
_RX_FRIDA_TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2}\.\d+)\] (.*)$")
_RX_READY_AFTER = re.compile(r"readyAfter=(\d+)")
_RX_GM_DESTROY = re.compile(r"\[gm-destroy\] enter .*reason=0x([0-9a-f]+)")
_RX_GM_DESTROY_OFFSET = re.compile(r"\bobj=(0x[0-9a-fA-F]+)")
_RX_WRAPPER_STATE = re.compile(r"\[rep-wrapper\].*\bstate=(\d+)")
_RX_SET_PROPERTY = re.compile(r"\[gameconn-vt 0x2d0\] SetProperty\((.*)\)")
_RX_SET_VERSION = re.compile(r"\[gameconn-vt 0x110\] SetVersionString\((.*)\)")


def update_frida(state: FridaState, line: str) -> None:
    m = _RX_FRIDA_TS.match(line)
    if m:
        ts, msg = m.group(1), m.group(2)
        if not state.first_ts:
            state.first_ts = ts
        state.last_ts = ts
    else:
        msg = line
    state.last_log_line = msg[:160]

    m2 = _RX_READY_AFTER.search(msg)
    if m2:
        try:
            new_ready = int(m2.group(1))
        except ValueError:
            new_ready = None
        if new_ready is not None and new_ready != state.rep_ready:
            ts_short = (state.last_ts or "")[:8]
            state.ready_transitions.append(
                f"{ts_short} {state.rep_ready}->{new_ready}"
            )
            state.rep_ready = new_ready

    m3 = _RX_GM_DESTROY.search(msg)
    if m3:
        reason = m3.group(1)
        m_off = _RX_GM_DESTROY_OFFSET.search(msg)
        offset = m_off.group(1) if m_off else "?"
        state.last_gm_destroy = f"reason=0x{reason} obj={offset}"

    m4 = _RX_WRAPPER_STATE.search(msg)
    if m4:
        try:
            st = int(m4.group(1))
        except ValueError:
            st = None
        if st is not None and (
            not state.wrapper_states or state.wrapper_states[-1] != st
        ):
            state.wrapper_states.append(st)

    m5 = _RX_SET_PROPERTY.search(msg)
    if m5:
        state.last_set_property = m5.group(1)[:160]

    m6 = _RX_SET_VERSION.search(msg)
    if m6:
        state.last_version_string = m6.group(1)[:160]

    if "[v3-resp-receive]" in msg and "HANDLER FIRED" in msg:
        state.v3_resp_receive_count += 1


# auth_mock format:  "[YYYY-MM-DD HH:MM:SS.mmm] message..."  (or similar)
_RX_AUTH_TS = re.compile(r"^\[([^\]]+)\] (.*)$")
_RX_AUTH_REQ = re.compile(r"^REQ (\w+) (https?://[^ ]+)")
_RX_AUTH_RESP = re.compile(r"^\s*> (\d{3}) ")


def update_auth_mock(state: AuthMockState, line: str) -> None:
    m = _RX_AUTH_TS.match(line)
    if not m:
        return
    ts_full, msg = m.group(1), m.group(2)
    ts = ts_full[-12:] if len(ts_full) >= 12 else ts_full
    if not state.first_ts:
        state.first_ts = ts
    state.last_ts = ts

    rm = _RX_AUTH_REQ.match(msg)
    if rm:
        method, url = rm.group(1), rm.group(2)
        # Strip the scheme://host so the pane stays compact and avoids
        # leaking host-specific values into the display.
        path_only = re.sub(r"^https?://[^/]+", "", url)
        endpoint = f"{method} {path_only}"
        if len(endpoint) > 60:
            endpoint = endpoint[:57] + "..."
        state.last_endpoints.append(endpoint)
        state.request_count += 1

    rr = _RX_AUTH_RESP.match(msg)
    if rr:
        status = rr.group(1)
        state.last_status = status
        if status[0] in ("4", "5"):
            ep_tail = state.last_endpoints[-1] if state.last_endpoints else "?"
            state.error_responses.append(f"{status} {ep_tail}")


# ---------------------------------------------------------------------------
#  "Biggest concern" derivation
# ---------------------------------------------------------------------------


def biggest_concern(
    resp: ResponderState, frida: FridaState, auth: AuthMockState
) -> str:
    if resp.disconnect_seen:
        return "DISCONNECT detected (sysmsg=3 on ch=3)"
    if frida.last_gm_destroy:
        return f"gridmate destroy fired: {frida.last_gm_destroy}"
    if resp.last_error:
        return f"responder ERROR: {resp.last_error[:80]}"
    if resp.path is None:
        return "no responder log discovered yet"
    if not resp.handshake_complete:
        return "waiting for DTLS handshake from client"
    if resp.v3_received == 0:
        return "V3 not yet received (waiting on client)"
    if resp.v3_received > 0 and resp.v3_sent == 0:
        return "V3 received but response not yet sent"
    if not resp.substitution_armed and resp.v3_sent > 0:
        return "V3 sent, substitution context not armed"
    if resp.replay_total and resp.replay_remaining:
        sent = resp.replay_total - resp.replay_remaining
        return f"replay shipping ({sent}/{resp.replay_total} messages)"
    if resp.replay_total and resp.replay_remaining == 0 and resp.heartbeat_count:
        return (
            f"connection idle, heartbeat firing (count={resp.heartbeat_count})"
        )
    if frida.rep_ready == 1:
        return "rep.ready=1 (V3 accepted, watching for next blocker)"
    if resp.last_warning:
        return f"responder warning: {resp.last_warning[:80]}"
    return "all green so far"


# ---------------------------------------------------------------------------
#  Rendering
# ---------------------------------------------------------------------------


def _safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    """Add a string to a curses window, clipping to the window's width.

    curses raises on out-of-bounds writes; we just truncate silently so
    a small terminal doesn't crash the dashboard.
    """
    try:
        h, w = win.getmaxyx()
    except curses.error:
        return
    if y >= h or x >= w:
        return
    text = text.replace("\t", "    ")
    max_len = w - x - 1
    if max_len <= 0:
        return
    if len(text) > max_len:
        text = text[:max_len]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def _draw_pane(
    stdscr,
    y: int,
    x: int,
    height: int,
    width: int,
    title: str,
    body: list[tuple[str, str]],
) -> None:
    """Draw a bordered pane at (y, x) with the given title and rows.

    ``body`` is a list of (label, value) pairs rendered one per row.
    """
    if height < 3 or width < 10:
        return
    # Top border + title
    _safe_addstr(stdscr, y, x, "+" + "-" * (width - 2) + "+")
    title_str = f" {title} "
    _safe_addstr(stdscr, y, x + 2, title_str, curses.A_BOLD)
    # Side borders
    for row in range(1, height - 1):
        _safe_addstr(stdscr, y + row, x, "|")
        _safe_addstr(stdscr, y + row, x + width - 1, "|")
    # Bottom border
    _safe_addstr(stdscr, y + height - 1, x, "+" + "-" * (width - 2) + "+")
    # Body rows
    inner_w = width - 4
    for i, (label, value) in enumerate(body):
        if i + 1 >= height - 1:
            break
        if label and value:
            row_text = f"{label}: {value}"
        elif label:
            row_text = label
        else:
            row_text = value
        if len(row_text) > inner_w:
            row_text = row_text[: inner_w - 1] + "~"
        _safe_addstr(stdscr, y + 1 + i, x + 2, row_text)


def _build_resp_body(s: ResponderState) -> list[tuple[str, str]]:
    log_name = s.path.name if s.path else "<not found>"
    rows = [
        ("log", log_name),
        (
            "handshake",
            "complete" if s.handshake_complete else "(waiting)",
        ),
        ("V3 received", str(s.v3_received)),
        ("V3 sent", str(s.v3_sent)),
        (
            "subst ctx",
            "armed" if s.substitution_armed else "(not armed)",
        ),
    ]
    if s.replay_total:
        if s.replay_remaining is None:
            replay = f"{s.replay_total} queued"
        else:
            sent = s.replay_total - s.replay_remaining
            replay = f"{sent}/{s.replay_total} sent"
    else:
        replay = "(replay not started)"
    rows.append(("replay", replay))
    rows.append(("heartbeat", str(s.heartbeat_count)))
    rows.append(
        ("disconnect", "YES (sysmsg=3)" if s.disconnect_seen else "no")
    )
    if s.last_warning:
        rows.append(("WARN", s.last_warning))
    if s.last_error:
        rows.append(("ERROR", s.last_error))
    return rows


def _build_frida_body(s: FridaState) -> list[tuple[str, str]]:
    log_name = s.path.name if s.path else "<not found>"
    if s.path:
        log_name = f"{s.path.parent.name}/{s.path.name}"
    rows = [
        ("log", log_name),
        ("rep.ready", str(s.rep_ready) if s.rep_ready is not None else "(unset)"),
        (
            "transitions",
            ", ".join(s.ready_transitions) if s.ready_transitions else "(none)",
        ),
        (
            "wrapper-state",
            ", ".join(str(v) for v in s.wrapper_states) or "(none)",
        ),
        ("gm-destroy", s.last_gm_destroy or "(none)"),
        ("v3-resp-recv", str(s.v3_resp_receive_count)),
    ]
    if s.last_set_property:
        rows.append(("SetProperty", s.last_set_property))
    if s.last_version_string:
        rows.append(("SetVersion", s.last_version_string))
    return rows


def _build_auth_body(s: AuthMockState) -> list[tuple[str, str]]:
    log_name = s.path.name if s.path else "<not found>"
    rows = [
        ("log", log_name),
        ("requests", str(s.request_count)),
        ("last status", s.last_status or "-"),
    ]
    rows.append(("recent endpoints", ""))
    if s.last_endpoints:
        for ep in list(s.last_endpoints)[-5:]:
            rows.append(("", ep))
    else:
        rows.append(("", "(none yet)"))
    if s.error_responses:
        rows.append(("4xx/5xx", ""))
        for er in list(s.error_responses):
            rows.append(("", er))
    return rows


# ---------------------------------------------------------------------------
#  Main loop
# ---------------------------------------------------------------------------


def _format_age(start_mono: float | None) -> str:
    if start_mono is None:
        return "--:--:--"
    delta = max(0, int(time.monotonic() - start_mono))
    h, rem = divmod(delta, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _newest_ts(*states) -> str:
    candidates = [getattr(s, "last_ts", "") for s in states]
    candidates = [c for c in candidates if c]
    return max(candidates) if candidates else "-"


def _rediscover(
    resp_t: Tailer, frida_t: Tailer, auth_t: Tailer
) -> tuple[Path | None, Path | None, Path | None]:
    rp = discover_responder()
    fp = discover_frida_session()
    ap = discover_auth_mock()
    resp_t.set_path(rp)
    frida_t.set_path(fp)
    auth_t.set_path(ap)
    return rp, fp, ap


def run(stdscr) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(int(TICK_S * 1000))

    resp_state = ResponderState()
    frida_state = FridaState()
    auth_state = AuthMockState()

    resp_tail = Tailer()
    frida_tail = Tailer()
    auth_tail = Tailer()

    # Initial discovery + state-path bookkeeping
    rp, fp, ap = _rediscover(resp_tail, frida_tail, auth_tail)
    resp_state.path = rp
    frida_state.path = fp
    auth_state.path = ap

    session_start_mono: float | None = None
    last_discovery = time.monotonic()
    DISCOVERY_INTERVAL_S = 10.0

    while True:
        # Periodic auto-rediscovery so a fresh run is picked up even
        # without the user pressing 'r'.
        now_mono = time.monotonic()
        if now_mono - last_discovery > DISCOVERY_INTERVAL_S:
            last_discovery = now_mono
            new_rp = discover_responder()
            new_fp = discover_frida_session()
            new_ap = discover_auth_mock()
            if new_rp != resp_state.path:
                resp_state = ResponderState(path=new_rp)
                resp_tail.set_path(new_rp)
            if new_fp != frida_state.path:
                frida_state = FridaState(path=new_fp)
                frida_tail.set_path(new_fp)
            if new_ap != auth_state.path:
                auth_state = AuthMockState(path=new_ap)
                auth_tail.set_path(new_ap)

        # Tail each file
        for line in resp_tail.read_new_lines():
            update_responder(resp_state, line)
            if session_start_mono is None:
                session_start_mono = now_mono
        for line in frida_tail.read_new_lines():
            update_frida(frida_state, line)
            if session_start_mono is None:
                session_start_mono = now_mono
        for line in auth_tail.read_new_lines():
            update_auth_mock(auth_state, line)
            if session_start_mono is None:
                session_start_mono = now_mono

        # Render
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        if h < 12 or w < 60:
            _safe_addstr(stdscr, 0, 0, "Terminal too small (need >= 60x12)")
            stdscr.refresh()
        else:
            header = (
                "  NW First Light Dashboard   "
                "(q quit, r re-discover)   "
                f"refresh ~{int(REFRESH_HZ)}Hz"
            )
            _safe_addstr(stdscr, 0, 0, header, curses.A_REVERSE)

            # Three stacked panes (terminal width is usually unknown,
            # stacking is more readable than three skinny columns).
            pane_h = (h - 3) // 3
            pane_y = 1
            pane_x = 0
            pane_w = w

            _draw_pane(
                stdscr, pane_y, pane_x, pane_h, pane_w,
                "rep_responder", _build_resp_body(resp_state),
            )
            _draw_pane(
                stdscr, pane_y + pane_h, pane_x, pane_h, pane_w,
                "frida_capture", _build_frida_body(frida_state),
            )
            _draw_pane(
                stdscr, pane_y + 2 * pane_h, pane_x, pane_h, pane_w,
                "auth_mock", _build_auth_body(auth_state),
            )

            # Status bar at the bottom
            age = _format_age(session_start_mono)
            latest = _newest_ts(resp_state, frida_state, auth_state)
            concern = biggest_concern(resp_state, frida_state, auth_state)
            status = (
                f" age={age}  latest={latest}  | {concern}"
            )
            _safe_addstr(stdscr, h - 1, 0, status.ljust(w - 1), curses.A_REVERSE)

        stdscr.refresh()

        # Input
        try:
            ch = stdscr.getch()
        except curses.error:
            ch = -1
        if ch in (ord("q"), ord("Q")):
            break
        if ch in (ord("r"), ord("R")):
            rp, fp, ap = _rediscover(resp_tail, frida_tail, auth_tail)
            resp_state = ResponderState(path=rp)
            frida_state = FridaState(path=fp)
            auth_state = AuthMockState(path=ap)
            last_discovery = time.monotonic()


def main() -> None:
    # ``curses.wrapper`` handles initscr/teardown + restores the terminal
    # cleanly even if we crash inside the loop.
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
