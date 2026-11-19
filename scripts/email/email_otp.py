#!/usr/bin/env python3
"""v3 compatibility shim -> aa email otp. Prefer the new command."""
import sys

from aa.cli import main

if __name__ == "__main__":
    sys.exit(main(['email', 'otp'] + sys.argv[1:]))
