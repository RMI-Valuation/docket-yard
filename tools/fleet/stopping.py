#!/usr/bin/env python3
"""How a reader is told to stop, and what it owes when it is (ADR 0025 addendum, proposal 1).

There are two ways to be told and they mean the same thing — *yield before the next page,
releasing what is unspent* — so one object answers both:

    stop = Stop(args.stop_file).install()
    ...
    if stop():
        q.release(name, ids[i:])
        log(stop.why(f"{len(ids) - i} pages released"))
        stop.checkpoint_complete()
        return 0

THE STOP FILE is a LATCH. An operator or a gate writes it and a person clears it; a reader
that starts while it exists reads nothing, which is the point — it is how the fleet is held
down deliberately.

THE SIGNAL IS NOT A LATCH, and must never be implemented as one. `SIGTERM` is how a broker
preempts (jobd signals the whole scope cgroup, then SIGKILLs after a grace). It says "not
now, on this machine", never "not until someone notices". So it sets a flag inside this
process and nothing on disk: the flag dies with the process, and the next placement reads
normally. Writing a stop file here would take the whole pass down until a human removed it,
which is the opposite of what a preempt means.

WHY A FLAG AND NOT A RELEASE IN THE HANDLER. A signal handler runs between bytecodes, in the
main thread, anywhere — including inside the queue's HTTP call or a model's generate. Doing
queue work there would re-enter code that is halfway through something. So the handler only
records, and the loop acts at the one place it already checks the stop file: between pages,
where a release is safe and nothing is half-done.

WHAT THE GRACE IS FOR. `JOBD_CHECKPOINT_GRACE_S` is the broker's budget between the signal
and SIGKILL; do not assume 60. A page takes about 9 s and the yield happens before the next
one, so the budget is comfortable — but it is read and logged, because the one thing that
would make it uncomfortable is a page that runs long, and then the operator should be able to
see what the budget was.

`jobd-checkpoint-complete` on stdout after the release is how the fleet learns the yield was
clean. It only raises an event on the broker — the job is `preempted` either way — but it is
the difference between "it stopped" and "it stopped tidily", and it costs one line.
"""

import os
import signal
import sys

CHECKPOINT_COMPLETE = "jobd-checkpoint-complete"
DEFAULT_GRACE_S = 60.0


def grace_seconds() -> float:
    """The broker's budget before SIGKILL. Absent, unreadable or nonsense means the default —
    a bad value must not stop a reader from yielding, only from knowing how long it had."""
    raw = os.environ.get("JOBD_CHECKPOINT_GRACE_S", "").strip()
    if not raw:
        return DEFAULT_GRACE_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_GRACE_S
    return value if value > 0 else DEFAULT_GRACE_S


class Stop:
    """Call it to ask whether to yield. True once the stop file exists or a signal arrived."""

    def __init__(self, stop_file=None):
        self.stop_file = stop_file
        self.signal_name: str | None = None
        self.grace = grace_seconds()

    def install(self) -> "Stop":
        """Catch the signals a broker or an operator stops a reader with. SIGINT is here so a
        hand-run worker in a terminal yields its pages instead of dying with them leased."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._catch)
            except (ValueError, OSError):  # not the main thread, or no such signal here
                pass
        return self

    def _catch(self, signum, frame) -> None:
        if self.signal_name is None:  # the first one wins, and names who stopped us
            self.signal_name = signal.Signals(signum).name
        elif signum == getattr(signal, "SIGINT", None):
            # The first Ctrl-C asked for a clean yield, which happens between pages and can
            # take a page's time. The SECOND is the operator's escape hatch from a page that
            # will not end, and swallowing it would take that away. Restoring the default is
            # not enough on its own — THIS press has already been consumed by this handler, so
            # without re-raising it the operator needs a third. A broker's SIGTERM needs no
            # equivalent: its escape hatch is the SIGKILL after the grace.
            # `default_int_handler`, NOT `SIG_DFL`: SIG_DFL is the C-level default and
            # terminates the process outright, unwinding nothing. Python's own default raises
            # KeyboardInterrupt, which is what Ctrl-C did here before this module existed.
            # It is CALLED rather than re-raised through the signal machinery, so the
            # KeyboardInterrupt comes out of this press synchronously instead of landing at
            # some later bytecode — otherwise the operator needs a third press.
            signal.signal(signal.SIGINT, signal.default_int_handler)
            signal.default_int_handler(signum, frame)

    def __call__(self) -> bool:
        if self.signal_name is not None:
            return True
        return bool(self.stop_file and self.stop_file.exists())

    def why(self, what: str) -> str:
        """One line naming who stopped it, for the log."""
        if self.signal_name:
            return f"{self.signal_name} (grace {self.grace:.0f}s); {what}; exit 0"
        return f"stop file present; {what}; exit 0"

    def checkpoint_complete(self) -> None:
        """Tell the broker the yield was clean. Only after the pages are actually released."""
        if self.signal_name:
            print(CHECKPOINT_COMPLETE, flush=True)
            sys.stdout.flush()


def yield_now(q, name: str, ids: list[int], i: int, stop: Stop, log, what: str = "") -> int:
    """Give back what is unspent, say who stopped us, tell the broker, and exit 0.

    THE ONE PLACE A READER YIELDS. Both lease loops are duplicated on purpose, and every
    branch that can be interrupted has to yield the same way — between pages, releasing the
    rest unspent — so the yield itself is here rather than written out five times. The bug
    that makes this worth centralising: `dots_worker`'s `PageFailed` branch had no stop check,
    and a broker tearing down the vLLM server inside the same scope makes an in-flight request
    return `finish_reason: abort`, which that branch failed FINALLY as the page's own. The
    document then reads `whole` for ever and the page is gone from the pass — a silent,
    permanent loss caused by a preempt, which is the 2026-09-06 shape in miniature.

    `release` is scoped to `lease_owner = ? AND state = 'leased'`, so calling this where
    nothing is held is a no-op, and a page released here has its attempt refunded: a stop is
    nobody's fault and must cost the page nothing.
    """
    q.release(name, ids[i:])
    # "up to", because a caller yielding from an outer handler passes the whole batch and some
    # of it may already be `done`. Release is scoped to what this worker still holds, so the
    # call is right either way — only the count would be a guess, and a log should not guess.
    log(stop.why(f"{what}up to {len(ids) - i} pages released unspent"))
    stop.checkpoint_complete()
    return 0
