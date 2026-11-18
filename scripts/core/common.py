"""Shared helpers: paths, env, config, kill switch, redacting logger.

Every script imports this first. Nothing here ever prints secrets.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import json
import logging
import os
import re
import sys
from pathlib import Path

HOME = Path(os.environ.get("AIRDROP_HOME", Path.home() / ".airdrop-agent")).expanduser()
VAULT_DIR = HOME / "vault"
DATA_DIR = HOME / "data"
PROOF_DIR = HOME / "proofs"
LOG_DIR = HOME / "logs"
KILL_FILE = HOME / "KILL"
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = SCRIPTS_DIR.parent
DB_PATH = DATA_DIR / "queue.sqlite3"

for _d in (HOME, VAULT_DIR, DATA_DIR, PROOF_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
try:
    os.chmod(HOME, 0o700)
    os.chmod(VAULT_DIR, 0o700)
except OSError:
    pass


def load_env() -> None:
    """Load ~/.airdrop-agent/.env into os.environ (no external dependency)."""
    env_file = HOME / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

from redact import RedactingFilter, redact  # noqa: E402  (after env so secrets are known)


def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for h in (logging.StreamHandler(sys.stderr), logging.FileHandler(LOG_DIR / "agent.log")):
        h.setFormatter(fmt)
        h.addFilter(RedactingFilter())
        log.addHandler(h)
    return log


def check_kill() -> None:
    if KILL_FILE.exists():
        print("KILL switch active (%s). Aborting." % KILL_FILE, file=sys.stderr)
        sys.exit(99)


def load_yaml(path: Path | str) -> dict:
    import yaml  # pyyaml

    p = Path(path).expanduser()
    if not p.exists():
        raise SystemExit(f"config not found: {p}")
    return yaml.safe_load(p.read_text()) or {}


def load_policy() -> dict:
    return load_yaml(os.environ.get("POLICY_FILE", HOME / "policy.yaml"))


def load_projects() -> dict:
    return load_yaml(os.environ.get("PROJECTS_FILE", HOME / "projects.yaml"))


def env_required(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"missing env {name} (set it in {HOME/'.env'})")
    return v


def out(obj) -> None:
    """Print JSON result for the agent, always redacted."""
    print(redact(json.dumps(obj, ensure_ascii=False, default=str, indent=2)))


ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def script(name: str) -> str:
    """Absolute path of a script by file name, searched in scripts/<group>/."""
    hits = sorted(SCRIPTS_DIR.glob(f"*/{name}"))
    if not hits:
        raise SystemExit(f"script not found: {name}")
    return str(hits[0])
