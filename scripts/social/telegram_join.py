#!/usr/bin/env python3
"""v3 shim: --target @x -> aa tg join @x."""
import sys

from aa.cli import main

args = sys.argv[1:]
if "--target" in args:
    i = args.index("--target")
    args[i:i + 2] = [args[i + 1]]
sys.exit(main(["tg", "join"] + args))
