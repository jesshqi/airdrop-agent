# OpenClaw adapter

OpenClaw loads skills from a directory and injects `AGENTS.md` every session.

## Install

```bash
./install.sh
mkdir -p ~/.openclaw/skills/airdrop-agent
cp SKILL.md AGENTS.md ~/.openclaw/skills/airdrop-agent/
ln -sf "$PWD/.venv/bin/aa" ~/.local/bin/aa
```

Point `AGENTS.md` at this repo, or copy the router block into your global `AGENTS.md` under a section
named `## airdrop-agent` so the router can dispatch.

## Trigger table for the router

```markdown
| keyword | skill | command |
|---|---|---|
| airdrop, testnet, quest, points, whitelist, mint | airdrop-agent | aa radar scan / aa quest run |
| wallet massal, identitas | airdrop-agent | aa identity new, aa wallet new |
| grinding role, discord | airdrop-agent | aa dc grind |
| faucet, deploy | airdrop-agent | aa testnet claim/deploy |
```

## Guard mapping

OpenClaw's own approval prompt is *not* the guard. Do not double-ask: if `aa` returns exit `10`, the
operator approves with the Telegram code, not an OpenClaw y/n. If it returns `2`, that's a policy denial,
not a bug.

## Cron pulse

```cron
*/15 * * * * cd /path/to/airdrop-agent && AIRDROP_HOME=$HOME/.airdrop-agent .venv/bin/aa autopilot tick >> $HOME/.airdrop-agent/logs/cron.log 2>&1
```

Keep the tick under the 8-minute quest budget; long flows belong in `autopilot run --minutes 60`.
