#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""KAR ingest manifest driver — thin wrapper for `llive.kar.manifests.main`."""

from __future__ import annotations

from llive.kar.manifests import main

if __name__ == "__main__":
    raise SystemExit(main())
