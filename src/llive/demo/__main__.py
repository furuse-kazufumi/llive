# SPDX-License-Identifier: Apache-2.0
"""``python -m llive.demo`` entry point."""

from __future__ import annotations

import sys

from llive.demo.runner import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
