# Contributing

## Dev setup

```bash
./install.sh --no-browser
.venv/bin/pip install -e ".[dev]" pyflakes
.venv/bin/pytest -q
.venv/bin/pyflakes aa tests scripts
```

Browser tests need `./install.sh` once (downloads Chromium). The offline suite must stay green
without a browser; anything that needs one belongs behind an explicit skip.

## Ground rules

- Every command returns the `jsonio` envelope and a meaningful `next`. No `print` for results.
- Policy is checked in the library, not only by the caller. A host must not be able to skip a cap.
- New steps in the quest DSL get: a validator entry, a runner branch, and a docs row in
  [docs/QUESTS.md](docs/QUESTS.md).
- New quests: `aa quest probe`, YAML, `aa quest validate`, `--dry`, then a live run. Record what
  stops where in [docs/TARGETS.md](docs/TARGETS.md).
- Never commit `~/.airdrop-agent`, `.env`, proofs, or a vault export.

## Style

Python 3.10+, stdlib typing, no lazy imports at module top that pull heavy deps (Playwright is lazy
by design). Keep functions small and name the failure mode in the message.

English for code and docs. No marketing adjectives in help text.

## Pull requests

Describe the failure, the fix, and the command that proves it. A change to policy, gates, or the
wire format gets a CHANGELOG entry. One topic per PR.
