#!/usr/bin/env python3
from __future__ import annotations

import sys

from validate_plugin_package import main as validate_plugin_main


def main() -> int:
    print(
        "deprecated: use scripts/validate_plugin_package.py instead",
        file=sys.stderr,
    )
    return validate_plugin_main()


if __name__ == "__main__":
    sys.exit(main())
