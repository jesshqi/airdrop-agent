#!/usr/bin/env bash
# Install airdrop-agent on Ubuntu 22.04/24.04 as the dedicated user "airdrop". Safe to re-run.
#   bash install.sh                 core (wallet, email, telegram, web, testnet, discord bot watcher)
#   bash install.sh --with-selfbot  + separate venv .venv-selfbot for discord chat_grinder (opt-in, ToS risk)
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
AHOME="${AIRDROP_HOME:-$HOME/.airdrop-agent}"

python3 -m venv "$SKILL_DIR/.venv"
"$SKILL_DIR/.venv/bin/pip" install -q -U pip
"$SKILL_DIR/.venv/bin/pip" install -q -r "$SKILL_DIR/requirements.txt"
"$SKILL_DIR/.venv/bin/python" -m playwright install chromium || echo "!! playwright browser install failed; retry later"
echo ">> once, with sudo: sudo $SKILL_DIR/.venv/bin/python -m playwright install-deps chromium"

if [[ "${1:-}" == "--with-selfbot" ]]; then
  # discord.py-self and discord.py both install the 'discord' package -> must live in a separate venv
  python3 -m venv "$SKILL_DIR/.venv-selfbot"
  "$SKILL_DIR/.venv-selfbot/bin/pip" install -q -U pip
  "$SKILL_DIR/.venv-selfbot/bin/pip" install -q pyyaml requests eth-account "discord.py-self>=2.0"
  echo ">> selfbot venv ready: $SKILL_DIR/.venv-selfbot/bin/python scripts/discord/chat_grinder.py"
fi

mkdir -p "$AHOME"/{vault,data,proofs,logs,quests,browser}
chmod 700 "$AHOME" "$AHOME/vault"
[ -f "$AHOME/.env" ] || { cp "$SKILL_DIR/templates/env.example" "$AHOME/.env"; chmod 600 "$AHOME/.env"; }
for f in policy.yaml projects.yaml discord_servers.yaml faucets.yaml radar_sources.yaml; do
  [ -f "$AHOME/$f" ] || cp "$SKILL_DIR/templates/$f" "$AHOME/"
done
cp -n "$SKILL_DIR"/templates/quests/*.yaml "$AHOME/quests/" 2>/dev/null || true
"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/core/task_queue.py" init
echo ">> Edit $AHOME/.env yourself (nano), then: $SKILL_DIR/.venv/bin/python $SKILL_DIR/scripts/core/selfcheck.py"
