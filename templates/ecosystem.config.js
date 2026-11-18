// pm2 start templates/ecosystem.config.js   (run as user "airdrop")
// Long-running: discord watcher + radar (TG listener + X poll + simple task exec). Scheduled: check-in + faucet via cron_restart (autorestart off).
const SKILL = process.env.SKILL_DIR || `${process.env.HOME}/.hermes/skills/crypto/airdrop-agent`;
const PY = `${SKILL}/.venv/bin/python`;

module.exports = {
  apps: [
    {
      name: "airdrop-discord-watch",
      cwd: SKILL,
      script: PY,
      args: "scripts/discord/discord_watch.py bot",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 30000,
    },
    {
      name: "airdrop-radar",
      cwd: SKILL,
      script: PY,
      args: "scripts/radar/radar_runner.py run",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 60000,
      // env: { RADAR_TG_SYNC: "0" },  // "1" only if no other process polls the report bot (getUpdates conflict)
    },
    {
      name: "airdrop-checkin",
      cwd: SKILL,
      script: PY,
      args: "scripts/core/checkin_runner.py",
      cron_restart: "10 7 * * *",
      autorestart: false,
    },
    {
      name: "airdrop-faucet",
      cwd: SKILL,
      script: PY,
      args: "scripts/testnet/faucet_claim.py --project example-testnet",
      cron_restart: "20 */12 * * *",
      autorestart: false,
    },
  ],
};
