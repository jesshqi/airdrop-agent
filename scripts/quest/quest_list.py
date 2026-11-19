#!/usr/bin/env python3
"""v3 compatibility shim -> aa quest list. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['quest', 'list'] + sys.argv[1:]))
