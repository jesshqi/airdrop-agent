# Agent adapters

Same brain, four ways in. Nothing is host-specific except the transport.

| host | transport | file |
|---|---|---|
| Hermes | shell (H1–H10 routes) | `hermes.md` |
| Muse | shell / task runner | `muse.md` |
| OpenClaw | skill directory + AGENTS.md | `openclaw.md` |
| Claude Desktop / Cursor / any MCP client | stdio MCP | `claude.md`, `mcp-claude.json` |
| cron / systemd / launchd | `aa autopilot tick|daemon` | `../templates/` |

## Common contract

- Binary: `<repo>/.venv/bin/aa` (or `python -m aa`).
- Home: `AIRDROP_HOME=~/.airdrop-agent` — one home, all hosts, shared gates and state.
- Output: JSON envelope, exit codes 0/2/3/10/99.
- Never wrap the binary in a script that swallows exit codes; gate handling depends on them.

## Install a host

```bash
./install.sh                     # venv, config, doctor
```

Then follow the host file. All hosts read [../SKILL.md](../SKILL.md) for behaviour and
[../AGENTS.md](../AGENTS.md) for routing.
