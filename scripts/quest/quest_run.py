#!/usr/bin/env python3
"""v3 shim: --file q.yaml -> aa quest import + aa quest run."""
import sys

from aa.cli import main
from aa.quest import dsl

args = sys.argv[1:]
if "--file" not in args:
    sys.exit(main(["quest", "run"] + args))
i = args.index("--file")
path = args[i + 1]
rest = args[:i] + args[i + 2:]
rc = main(["quest", "import", path])
if rc != 0:
    sys.exit(rc)
q = dsl.import_file(path) if False else None
qid = __import__("yaml").safe_load(open(path).read())["id"]
sys.exit(main(["quest", "run", qid] + rest))
