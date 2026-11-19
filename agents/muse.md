# Muse adapter

Muse runs long tasks and prefers compact, parseable output.

## Setup

```bash
./install.sh --full
export AIRDROP_HOME="$HOME/.airdrop-agent"
export PATH="$PWD/.venv/bin:$PATH"
aa init --random-vault-password
```

## Task shape

Give Muse one objective per run and let it use `next` from the envelope:

```bash
aa identity new runner --wallets 2
aa testnet faucets --chain sepolia
aa testnet claim --chain sepolia --identity runner
aa daily plan --identity runner
aa daily run --identity runner
```

## Structured consumption

- Parse stdout as JSON. `data` is the only source of truth.
- On exit `10`, pause the task with `gate_id` + `summary`; resume after `aa gate approve`.
- On exit `2`, store the cap message, adjust one variable, retry once only.
- Use `aa autopilot tick` for the unattended pulse; never loop `daemon` inside a task that has a timeout.

## Artifacts

Proofs: `~/.airdrop-agent/proofs/*.png`. Runs: `aa events`. Report both paths, not prose summaries.
