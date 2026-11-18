# Hermes cron jobs (alternatif dari crontab/pm2)

Cron Hermes jalan di sesi agent baru tanpa chat; toolset `cronjob`, `messaging`, `clarify`
dimatikan di cron. Jadi laporan dikirim oleh script (`report_telegram.py`), bukan tool messaging.
Aktifkan `terminal` (+ `browser` kalau perlu) untuk platform cron:

```yaml
# ~/.hermes/config.yaml
platform_toolsets:
  cron:
    - terminal
    - file
    - skills
```

Buat job dari chat Hermes (atau `hermes cron`), contoh:

```text
cronjob(action="create", name="airdrop-daily-checkin", schedule="10 7 * * *",
        enabled_toolsets=["terminal", "file", "skills"],
        prompt="Load skill airdrop-agent. cd ~/.hermes/skills/crypto/airdrop-agent && .venv/bin/python scripts/core/selfcheck.py; if ok, run .venv/bin/python scripts/core/checkin_runner.py. Do not do anything else. Never print .env or vault files.")

cronjob(action="create", name="airdrop-queue-worker", schedule="every 2h",
        enabled_toolsets=["terminal", "file", "skills"],
        prompt="Load skill airdrop-agent. Process up to 5 tasks: task_queue.py next -> execute per references/autonomous-execution.md -> done/fail/block/gate. Stop at any gate. Report summary with report_telegram.py.")

cronjob(action="create", name="airdrop-research", schedule="0 19 * * *",
        enabled_toolsets=["terminal", "file", "skills", "web"],
        prompt="Load skill airdrop-agent. Follow references/research.md: find max 5 new testnet/points campaigns from official sources, score each with research_score.py, send shortlist via report_telegram.py. Do not add projects automatically.")
```

Catatan: kalau pakai MCP di cron, sebut nama toolset `mcp-<nama>` secara eksplisit di `enabled_toolsets`.
