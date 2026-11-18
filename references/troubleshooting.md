# Troubleshooting

| Gejala | Penyebab | Solusi |
|---|---|---|
| `missing env X` | `.env` belum diisi / user beda | isi `~/.airdrop-agent/.env` milik user yang menjalankan |
| `RPC chain_id ... != policy` | RPC salah/palsu | ganti RPC di `.env`, cek chain_id |
| `simulation FAILED` exit 3 | revert (saldo, syarat, kontrak) | baca error, jangan retry broadcast otomatis |
| exit 10 | menunggu gate | cek Telegram, `approve ID CODE`, rerun `--gate-id` |
| `KILL switch active` | file KILL ada | the owner cek, lalu `rm ~/.airdrop-agent/KILL` |
| Telegram `session not authorized` | session kedaluwarsa/di-terminate | `tg_tasks.py login` ulang (manusia) |
| `FloodWait > limit` | terlalu banyak aksi | tunggu, turunkan frekuensi, naikkan `TG_MIN_DELAY` |
| Laporan tidak masuk topic | chat_id/topic salah, bot bukan member | cek `-100…`, `message_thread_id`, jadikan bot admin |
| Playwright `Executable doesn't exist` | browser belum terpasang | `.venv/bin/python -m playwright install chromium` + `install-deps` |
| `Missing X server` | extension butuh headed | jalankan Xvfb `:99`, `export DISPLAY=:99` |
| Selector tidak ketemu | UI site berubah | `--headed` via VNC, update quests YAML |
| Captcha terus muncul | IP datacenter / fingerprint | selesaikan manual; jangan ganti IP tiap run (pola sybil) |
| IMAP login gagal | belum App Password / IMAP off | aktifkan 2FA → App Password; Gmail IMAP on |
| OTP tidak ketemu | filter terlalu ketat / spam folder | `--folder "[Gmail]/Spam"`, perbesar `--since-min` |
| Discord bot tidak baca isi | Message Content Intent off | aktifkan di Developer Portal |
| Hermes tidak melihat skill | path / frontmatter | `~/.hermes/skills/<kategori>/airdrop-agent/SKILL.md`, `name` = nama folder, cek `hermes skills list` |
| Cron Hermes tanpa tool | toolset cron | set `platform_toolsets.cron` / `enabled_toolsets` |
| `solders` gagal install | wheel arsitektur | abaikan (opsional), jangan pakai `--solana` |
| `chat_grinder is opt-in` | belum opt-in | `I_ACCEPT_BAN_RISK=true` + `DISCORD_USER_TOKEN` akun khusus |
| `ModuleNotFoundError: discord` / bentrok discord.py | discord.py-self & discord.py sama-sama paket `discord` | jalankan grinder dengan `.venv-selfbot/bin/python` (`install.sh --with-selfbot`) |
| Grinder ter-pause terus | ada mod/peringatan/timeout | baca alasan di Telegram, cek manual di Discord, `chat_grinder.py resume ID` |
| `browser_session cmd` → bad token | sesi `serve` lain / token lama | restart `serve`, token baru ditulis ke `data/browser_token` |
| Page bilang "waiting for owner approval #N" | sign/tx butuh gate | approve di Telegram, ulangi aksi di halaman |
| Radar: `database is locked` Telethon | session dipakai 2 proses | radar pakai `TG_RADAR_SESSION` terpisah; jangan jalankan `tg_radar listen` dua kali |
| Radar: FloodWait saat join | akun baru / terlalu cepat | turunkan `tg_join_cap_per_day`, naikkan `tg_join_delay_s`; join lanjut besok |
| X API 402/403 | kredit habis / endpoint tidak di plan | top-up, kecilkan `x_max_reads_per_day`; follow API = Enterprise only |
| RISK ON tapi tetap minta kode | Telegram laporan belum di-set, label bukan `wallet_labels`, chain tanpa `risk_on` cap, atau lewat cap | `risk_mode.py status`, `selfcheck.py` |
