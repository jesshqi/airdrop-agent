#!/usr/bin/env python3
"""v3 shim: handles as positional -> aa x follow."""
import sys

from aa.cli import main

sys.exit(main(["x", "follow"] + sys.argv[1:]))
