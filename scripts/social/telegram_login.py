#!/usr/bin/env python3
"""v3 compatibility shim -> aa tg login. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['tg', 'login'] + sys.argv[1:]))
