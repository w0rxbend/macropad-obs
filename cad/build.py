# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Case build entry. Task 1.4b retired the old wedge; task 6.2a brings the v2 body."""

import sys

NO_BODY_EXIT = 2


def main() -> int:
    print("no case body until 6.2a", file=sys.stderr)
    return NO_BODY_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
