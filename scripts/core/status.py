#!/usr/bin/env python3
"""v3 compatibility shim -> aa status. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['status'] + sys.argv[1:]))
