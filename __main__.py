from __future__ import annotations

import sys
import warnings

from .orchestrator import run


def _read_complete_input() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:])
    return sys.stdin.read()


def main() -> int:
    raw_text = _read_complete_input()
    while True:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = run(raw_text)
            if result:
                sys.stdout.write(result + "\n")
                sys.stdout.flush()
                return 0
        except KeyboardInterrupt:
            return 130
        except Exception:
            continue


if __name__ == "__main__":
    raise SystemExit(main())
