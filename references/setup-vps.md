# Setup VPS (Ubuntu 22.04/24.04) langkah demi langkah

1. **User terpisah** (jangan root, jangan user yang pegang bot Cupang/wallet utama):
   ```bash
   sudo adduser --disabled-password airdrop
   sudo apt update && sudo apt install -y python3-venv python3-pip git xvfb x11vnc fluxbox unzip
   sudo -iu airdrop
   ```
2. **Hermes Agent** (kalau belum): ikuti docs resmi `hermes-agent.nousresearch.com` (installer
   `hermes`), set model/provider, lalu `hermes tools` → aktifkan `terminal`, `file`, `skills`,
   `browser` (opsional), `cronjob`.
3. **Pasang skill**:
   ```bash
   mkdir -p ~/.hermes/skills/crypto
   unzip airdrop-agent-v2.zip -d ~/.hermes/skills/crypto/      # -> ~/.hermes/skills/crypto/airdrop-agent/
   bash ~/.hermes/skills/crypto/airdrop-agent/install.sh        # tambah --with-selfbot untuk chat_grinder (opt-in)
   exit; sudo /home/airdrop/.hermes/skills/crypto/airdrop-agent/.venv/bin/python -m playwright install-deps chromium; sudo -iu airdrop
   ```
4. **Isi `.env`** sendiri lewat `nano ~/.airdrop-agent/.env` (bukan lewat chat agent).
   Buat bot laporan di @BotFather, tambahkan ke grup forum sebagai admin, ambil `chat_id`
   (format `-100…`) dan `message_thread_id` topik.
5. **Burner wallet**: `.venv/bin/python scripts/wallet/wallet_create.py --label main-burner`.
   Kirim saldo testnet/sedikit mainnet ke alamat itu. Backup folder `vault/` + passphrase offline.
6. **Telegram user session** (nomor khusus): `.venv/bin/python scripts/telegram/tg_tasks.py login`.
7. **Browser login manual** (Discord, X, Galxe, dsb.) via VNC:
   ```bash
   Xvfb :99 -screen 0 1366x900x24 & export DISPLAY=:99; fluxbox &
   x11vnc -display :99 -localhost -rfbauth ~/.vnc/passwd -forever &   # set password: x11vnc -storepasswd
   # dari laptop: ssh -L 5900:localhost:5900 airdrop@VPS  lalu buka VNC viewer ke localhost:5900
   .venv/bin/python scripts/web/web_quest.py login --url https://discord.com/login
   ```
   VNC **hanya** lewat SSH tunnel (`-localhost`), jangan buka port 5900 ke publik.
8. **Extension wallet (opsional)**: download Rabby/MetaMask dari sumber resmi (Chrome Web Store
   → CRX extractor tepercaya atau release GitHub resmi), unzip ke `~/ext/rabby`, set
   `BROWSER_EXTENSION_DIRS`. Import **burner** saja ke extension.
9. `policy.yaml`: isi RPC, cap, allowlist kontrak dari docs resmi. `projects.yaml`: garapan.
10. `task_queue.py import ~/.airdrop-agent/projects.yaml` lalu `selfcheck.py`.
11. Jadwal: pilih **satu**: Hermes cron (`templates/hermes-cron-jobs.md`), crontab, pm2, atau systemd.
12. Hardening: SSH key-only, `ufw allow OpenSSH && ufw enable`, unattended-upgrades, jangan
    jalankan repo/tool viral tak dikenal di user ini.
