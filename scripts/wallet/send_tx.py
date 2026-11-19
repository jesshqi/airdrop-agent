#!/usr/bin/env python3
"""v3 compatibility shim -> aa wallet send. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['wallet', 'send'] + sys.argv[1:]))
