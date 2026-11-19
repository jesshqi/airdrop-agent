"""JSON envelope + event emission.

Every CLI command returns `{"ok": bool, "data": ..., "error": ..., "next": [...]}` so
an LLM caller can branch without parsing prose. Human output is the same JSON.
"""
from __future__ import annotations

import json
import sys
import time

from .log import redact

EXIT_OK = 0
EXIT_DENIED = 2
EXIT_FAIL = 3
EXIT_GATE = 10
EXIT_KILL = 99


class Denied(Exception):
    """Policy said no (exit 2)."""


class Gate(Exception):
    """Needs human approval (exit 10)."""


class Kill(Exception):
    """KILL switch is set (exit 99)."""


def emit(ok: bool, data=None, error: str | None = None, next_steps: list[str] | None = None, code: int | None = None) -> int:
    payload = {"ok": ok, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "data": data}
    if error:
        payload["error"] = redact(error)
    if next_steps:
        payload["next"] = next_steps
    print(redact(json.dumps(payload, ensure_ascii=False, default=str, indent=2)))
    if code is not None:
        return code
    return EXIT_OK if ok else EXIT_FAIL


def _bind(fn, ns):
    import inspect

    sig = inspect.signature(fn)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name == "args":
            kwargs[name] = ns
        elif hasattr(ns, name):
            kwargs[name] = getattr(ns, name)
        elif param.default is not inspect.Parameter.empty:
            continue
        else:
            raise SystemExit(f"missing argument --{name.replace('_', '-')}")
    return fn(**kwargs)


def run(fn, ns) -> int:
    """Execute a command function bound to the parsed namespace."""
    try:
        out = _bind(fn, ns)
        data, next_steps = (out if isinstance(out, tuple) else (out, None))
        return emit(True, data, next_steps=next_steps)
    except Denied as e:
        return emit(False, None, str(e), ["aa gate list"], EXIT_DENIED)
    except Gate as e:
        return emit(False, None, str(e), ["aa gate list", "aa gate approve <id> <code>"], EXIT_GATE)
    except Kill as e:
        return emit(False, None, str(e), ["aa unkill"], EXIT_KILL)
    except KeyboardInterrupt:
        return emit(False, None, "interrupted", None, 130)
    except SystemExit as e:
        if isinstance(e.code, int):
            return e.code
        return emit(False, None, str(e.code)) if e.code else EXIT_OK
    except Exception as e:  # noqa: BLE001 — CLI boundary
        import traceback

        if "--debug" in sys.argv:
            traceback.print_exc()
        return emit(False, None, f"{type(e).__name__}: {e}")
