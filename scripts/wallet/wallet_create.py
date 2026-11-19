#!/usr/bin/env python3
"""v3 shim: --label X [--count N] -> aa identity new X --wallets N, or wallet new if the identity exists."""
import sys

from aa import db
from aa.cli import main

args = sys.argv[1:]
label = "main"
count = "3"
if "--label" in args:
    label = args[args.index("--label") + 1]
if "--count" in args:
    count = args[args.index("--count") + 1]
if db.one("SELECT 1 FROM identities WHERE label=?", (label,)):
    sys.exit(main(["wallet", "new", "--identity", label, "--count", count]))
sys.exit(main(["identity", "new", label, "--wallets", count]))
