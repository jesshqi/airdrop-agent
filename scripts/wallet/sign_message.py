#!/usr/bin/env python3
"""v3 compatibility shim -> aa sign message. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['sign', 'message'] + sys.argv[1:]))
