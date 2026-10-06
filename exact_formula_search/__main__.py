from __future__ import annotations

import sys
import traceback

from .models import FormalizationError
from .orchestrator import run


def _read_complete_input() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:])
    return sys.stdin.read()


def main() -> int:
    raw_text = _read_complete_input()
    try:
        result = run(raw_text)
    except FormalizationError as exception:
        sys.stderr.write("formalization error: " + str(exception) + "\n")
        sys.stderr.flush()
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception:
        sys.stderr.write("unexpected failure during search\n")
        traceback.print_exc()
        sys.stderr.flush()
        return 1
    if result:
        sys.stdout.write(result + "\n")
        sys.stdout.flush()
        return 0
    sys.stderr.write("search produced no result\n")
    sys.stderr.flush()
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
