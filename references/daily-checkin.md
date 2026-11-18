# 8. Daily Check-in

## Konfigurasi
Tambahkan blok `checkin:` per project di `projects.yaml` (tipe `web`, `telegram`, `tx`,
`faucet`, `command`). Contoh di `templates/projects.yaml`.

## Runner
`checkin_runner.py`: acak urutan project, jitter awal 0–`CHECKIN_JITTER_MIN` menit + 30–180 dtk
antar project, skip yang sudah ok hari ini, catat streak, kirim ringkasan:
```
🗓️ Daily check-in 2026-11-19
✅ Example Testnet — streak 12 hari
❌ Example TG Mini App — streak 0 hari
   ↳ button 'Daily' not found
```
Uji: `checkin_runner.py --dry-run` / `--project example-testnet --no-jitter`.

## Penjadwalan (pilih satu)
- **Hermes cron**: `templates/hermes-cron-jobs.md` (cron Hermes tanpa toolset messaging → laporan via script).
- **crontab**: `templates/crontab.txt`.
- **pm2**: `templates/ecosystem.config.js` (`cron_restart`, `autorestart:false`).
- **systemd timer**: `templates/systemd/` (`RandomizedDelaySec` untuk jitter).

Kalau streak putus karena site berubah: update selector di `quests/<p>_checkin.yaml`, jalankan
`web_quest.py run --steps ... --headed` lewat VNC untuk debug.
