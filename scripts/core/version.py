#!/usr/bin/env python3
"""v3 compatibility shim -> aa version. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['version'] + sys.argv[1:]))
