#!/usr/bin/env python3
"""v3 compatibility shim -> aa radar scan. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['radar', 'scan'] + sys.argv[1:]))
