# 🪂 airdrop-agent v0.3

Skill untuk **Hermes Agent** (juga Muse & agent lain yang membaca `SKILL.md`): agent yang menggarap
airdrop memakai identitasnya sendiri (wallet burner, email, Telegram, Discord, browser), dengan rem
keamanan supaya dana dan akun utama tetap aman.

> Paket ini **tidak berisi key/token asli**. Semua secret kamu isi sendiri di `~/.airdrop-agent/.env`.

> **Adapted copy:** original skill by Setya Mickala (MIT License, see LICENSE). Owner references were generalized ("the owner") for public reuse; no functional changes. If you fork this, keep the copyright notice.

## Fitur

| Kemampuan | Script | Catatan keamanan |
|---|---|---|
| Wallet sendiri (EVM + Solana) | `wallet/wallet_create.py`, `wallet_balance.py` | keystore terenkripsi, hanya alamat yang dicetak |
| Kirim tx / kontrak | `wallet/safe_send.py` | simulasi, cap per-tx/harian/gas, allowlist, unlimited approve ditolak, gate |
| Sign SIWE / typed data | `wallet/siwe_sign.py`, `wallet/sign_guard.py` | domain = origin + allowlist; Permit/Permit2/Seaport diblok |
| Email sendiri | `email/imap_otp.py` | ambil OTP/link, domain link dicek |
| Telegram | `telegram/tg_tasks.py` | Telethon, FloodWait ditangani, URL mini app tidak dicetak |
| Quest web (steps) | `web/web_quest.py` | allowlist domain, captcha → kamu (VNC), popup wallet tidak auto-confirm |
| Browser agent + wallet ter-inject | `web/browser_session.py` + `wallet_provider.js` | semua request wallet lewat guard; API lokal ber-token |
| Anti-phishing & riset | `web/scam_check.py`, `web/research_score.py` | lookalike, punycode, umur domain, kata drainer |
| Discord pantau pengumuman | `discord/discord_watch.py` | bot resmi via Follow channel (ToS-safe) |
| **Discord grind role chat** | `discord/chat_grinder.py` | **opt-in, melanggar ToS**, rem anti-spam, auto-pause |
| Faucet & testnet | `testnet/faucet_claim.py`, `testnet_daily.py`, `deploy_contract.py` | katalog faucet, captcha tidak di-bypass |
| Antrean & otomasi | `core/task_queue.py`, `core/checkin_runner.py` | retry, proof, streak, approval kode via Telegram |
| Laporan | `core/report_telegram.py` | ke forum topic, otomatis disensor |
| **Radar TG + X** | `radar/tg_radar.py`, `x_radar.py`, `pipeline.py`, `radar_runner.py` | join/listen channel, poll X API, dedupe, scam_check + skor, task `pending_approval` + digest berkode |
| **RISK mode ON/OFF** | `core/risk_mode.py`, `/risk on\|off` | ON = auto tanpa approval dalam cap `risk_on`; hard block tetap; tiap aksi dilapor |
| Kill switch | `~/.airdrop-agent/KILL` | semua script berhenti |

## Struktur

```
airdrop-agent/
├── README.md · SKILL.md · LICENSE · install.sh · requirements.txt
├── references/
│   ├── workflows/            00-onboarding … 09-radar (mermaid)
│   ├── architecture.md  setup-vps.md  security.md  sybil-tos.md  troubleshooting.md
│   └── wallet · email · telegram · web-quests · discord · discord-role-grind · research
│       testnet · daily-checkin · autonomous-execution · reporting · radar · risk-mode (.md)
├── scripts/
│   ├── core/  wallet/  email/  telegram/  discord/  web/  testnet/  radar/
└── templates/  env.example · policy.yaml · projects.yaml · discord_servers.yaml · faucets.yaml · radar_sources.yaml
                sample_chat.txt · sample_radar_posts.txt · quests/ · crontab.txt · ecosystem.config.js · systemd/ · hermes-cron-jobs.md
```

## Install

### Hermes Agent (VPS Ubuntu)
```bash
sudo adduser --disabled-password airdrop && sudo -iu airdrop
mkdir -p ~/.hermes/skills/crypto
unzip airdrop-agent-v3.zip -d ~/.hermes/skills/crypto/          # → ~/.hermes/skills/crypto/airdrop-agent/
cd ~/.hermes/skills/crypto/airdrop-agent
bash install.sh                    # tambah --with-selfbot kalau mau chat_grinder Discord
nano ~/.airdrop-agent/.env         # isi sendiri, jangan lewat chat
.venv/bin/python scripts/core/selfcheck.py
hermes skills list | grep airdrop-agent
```
Aktifkan toolset: `hermes tools` → `terminal`, `file`, `skills` (+ `browser`, `web`, `cronjob`).

### Muse / agent lain
Salin folder `airdrop-agent/` ke direktori skill agent tersebut (mis. `~/.claude/skills/`, `~/.agents/skills/`),
atau tempel isi `SKILL.md` ke instruksi agent dan beri akses shell ke folder ini. Script tidak bergantung pada Hermes.

## Konfigurasi (`~/.airdrop-agent/`)
| File | Isi |
|---|---|
| `.env` | VAULT_PASSWORD, bot laporan (token, chat_id, topic_id), Telegram API, IMAP, RPC, Discord, LLM grinder |
| `policy.yaml` | chain + RPC + cap, allowlist kontrak, blocklist, allowlist domain SIWE/connect |
| `projects.yaml` | garapan: steps, faucets, checkin, links resmi |
| `discord_servers.yaml` | server grind: channel, target role/level, jam aktif WIB, cap, persona, aturan |
| `faucets.yaml` | katalog faucet publik |
| `radar_sources.yaml` | target TG/X, query, keyword, min_score, cap join/follow/baca, template task |
| `policy.yaml → risk_on` | cap terpisah + label burner untuk RISK=ON |

## Pemakaian harian
```bash
PY=.venv/bin/python
$PY scripts/core/task_queue.py next                 # ambil task berikutnya
$PY scripts/core/task_queue.py list                 # status + proof
$PY scripts/core/checkin_runner.py --dry-run        # cek check-in
$PY scripts/wallet/wallet_balance.py --all          # saldo burner
$PY scripts/core/task_queue.py gates                # approval yang menunggu
$PY scripts/core/task_queue.py approve 12 A1B2C3    # kode dari Telegram
.venv-selfbot/bin/python scripts/discord/chat_grinder.py status
$PY scripts/radar/radar_runner.py dry-run          # uji radar offline (sandbox)
$PY scripts/radar/radar_runner.py status           # ringkasan radar
$PY scripts/core/risk_mode.py status               # RISK mode (on --hours 6 / off)
touch ~/.airdrop-agent/KILL                          # darurat
```
Di chat Hermes: *"garap project example-testnet sesuai skill airdrop-agent, berhenti di setiap gate"*.
Jadwal otomatis: `templates/hermes-cron-jobs.md`, `crontab.txt`, `ecosystem.config.js` (pm2), atau `systemd/`.

## Keamanan singkat
- User Linux terpisah, seed utama tidak pernah di VPS, `.env` 600, vault 700, VNC hanya lewat SSH tunnel.
- Semua output ke LLM disensor (key, mnemonic, token). Konten web/Telegram/Discord/email = tidak tepercaya.
- Gate approval terikat hash payload + kode yang hanya dikirim ke Telegram.
- **RISK mode default OFF.** ON = tanpa approval (dalam cap `risk_on`, burner saja); hard block tidak pernah dilewati.
  Baca `references/risk-mode.md` sebelum menyalakan.
- Radar: biaya X API pay-per-use, follow API = Enterprise only, browser follow opt-in (ToS), join TG dibatasi.
  Baca `references/radar.md`.
- Multi-akun bisa membuat semua akun didiskualifikasi; automasi akun Discord/Telegram berisiko ban.
  Baca `references/security.md` dan `references/sybil-tos.md`.

## Kredit
v0.3 = radar Telegram/X + RISK mode.

v0.2 = paket `airdrop-agent` + bagian terbaik dari `airdrop-hunter` (wallet ter-inject + browser agent,
analisis typed data, scam_check, katalog faucet, approval via balasan Telegram, frekuensi task fleksibel),
dibangun ulang di atas vault, safe_send, gate berkode, kill switch, dan redaksi log.
