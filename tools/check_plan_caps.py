"""Fail the commit when a planning file exceeds its line cap.

TODO.md and ROADMAP.md only stay useful while they stay short. The cap converts "keep it
lean" from an intention into something that cannot be violated silently. When it fires,
prune or graduate items — do not raise the cap without deciding to, out loud.
"""

import sys
from pathlib import Path

CAPS = {"TODO.md": 60, "ROADMAP.md": 80}


def main(argv: list[str]) -> int:
    failed = False
    for name in argv or list(CAPS):
        path = Path(name)
        cap = CAPS.get(path.name)
        if cap is None or not path.exists():
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > cap:
            print(f"{path.name}: {lines} lines exceeds the cap of {cap}. Prune it.")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
