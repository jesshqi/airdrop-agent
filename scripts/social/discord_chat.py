#!/usr/bin/env python3
"""v3 compatibility shim -> aa dc grind. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['dc', 'grind'] + sys.argv[1:]))
