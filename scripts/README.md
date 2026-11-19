# v3 compatibility shims

These forward to the v4 CLI. They exist so old cron lines keep working; new work should call `aa`
directly. Some v3 flags are translated (`--label`, `--target`, `--file`), the rest pass through.

| shim | new command |
|---|---|
| core/init.py | `aa init` |
| core/doctor.py | `aa doctor` |
| core/status.py | `aa status` |
| wallet/wallet_create.py | `aa identity new` / `aa wallet new` |
| wallet/send_tx.py | `aa wallet send` |
| wallet/sign_message.py | `aa sign message` |
| social/telegram_join.py | `aa tg join` |
| social/discord_chat.py | `aa dc grind` |
| quest/quest_run.py | `aa quest import` + `aa quest run` |
| testnet/faucet_claim.py | `aa testnet claim` |
| radar/radar_scan.py | `aa radar scan` |

Shims assume the package is importable (`pip install -e .` or `PYTHONPATH=<repo>`).
