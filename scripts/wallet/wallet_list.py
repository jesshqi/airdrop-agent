#!/usr/bin/env python3
"""v3 compatibility shim -> aa wallet list. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['wallet', 'list'] + sys.argv[1:]))
