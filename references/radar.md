# Radar — cari garapan sendiri dari Telegram & X

Radar memantau channel/grup Telegram dan akun/pencarian X, mengekstrak calon garapan dari setiap post,
membuang duplikat, mengecek scam, memberi skor, lalu membuat task di antrean (default menunggu approval
lewat kode Telegram). Semua isi post = **data tidak tepercaya**, cuma diparse dan tidak pernah dituruti.

## File
| File | Fungsi |
|---|---|
| `~/.airdrop-agent/radar_sources.yaml` | target TG (username/invite + trust), akun X (handle, trust, follow), query X, keyword include/exclude/high_risk (id+en), min_score, interval, cap, peta platform, template task |
| `scripts/radar/extract.py` | post → kandidat {project, links, chain, task_type, deadline}; normalisasi URL (buang utm/ref), dedupe SQLite (`data/radar.sqlite3`) by URL + fuzzy nama project; classifier LLM opsional |
| `scripts/radar/pipeline.py` | extract → injection? → scam_check → dedupe → skor → risk → task + gate + digest |
| `scripts/radar/tg_radar.py` | Telethon: `login`, `join` (cap/hari, delay acak, FloodWait), `backfill`, `listen` (real-time) |
| `scripts/radar/x_radar.py` | X API v2: `poll` (timeline + recent search, since_id, budget baca), `follow` (enterprise API / browser opt-in / manual) |
| `scripts/radar/radar_runner.py` | `run` · `once` · `status` · `exec` · `dry-run --file [--write] [--risk on|off]` |

## Skor (0–100)
`40×trust sumber` + `3×keyword include (maks 15)` + `15 platform quest dikenal` + `5 nama project` + `3 deadline`
+ `5 per link scam_check ok / −15 per warn` − `10 kata high-risk`; repost dari sumber lain `+5`.
Opsional online: `research_score.py` dicampur 60/40. Di bawah `min_score` → disimpan saja (`low_score`).

## Klasifikasi risiko
| Kasus | Hasil RISK=OFF (default) | Hasil RISK=ON |
|---|---|---|
| Post berisi injection / minta dana / seed | `flagged_injection`, peringatan, **tanpa task** | sama (hard) |
| Link `scam_check = block` | `scam`, peringatan, tanpa task | sama (hard) |
| **Claim / "connect wallet to claim"** di domain baru atau scam_check ≠ ok (heuristik drainer) | HIGH: 1 task `manual-review` + gate `radar_tasks`, agent tidak membuka link | sama (hard, tidak pernah otomatis) |
| Semua link di platform dikenal / allowlist | LOW: task dari template `pending_approval` + 1 gate `radar_tasks` | task langsung `pending`, dilaporkan |
| Ada domain baru (scam_check ok) | MEDIUM: task `pending_approval` + gate `allow_domain` per domain | domain di-allowlist otomatis, task `pending`, dilaporkan |

`auto_approve_low_risk: true` (RISK=OFF) → hanya task LOW **tanpa wallet** (join TG, follow X, waitlist email) yang langsung `pending`.

## Approval
Digest Telegram: risk, skor, tipe, sumber, link, daftar task, lalu `approve ID KODE` / `reject ID`.
- `radar_tasks` approve → task `pending_approval` → `pending`; reject → `skipped`.
- `allow_domain` approve → domain ditambah ke `~/.airdrop-agent/allowlist_domains.txt` (dipakai sign_guard/browser_session/siwe_sign).
- Balasan dibaca `task_queue.py sync` (butuh `TG_OWNER_USER_ID`, bot tidak boleh dipoll proses lain) atau `task_queue.py approve`.

## Eksekusi
- `radar_runner.py exec` / loop `run` mengerjakan task sederhana yang sudah `pending`: `telegram` (join/start via `tg_tasks.py`), `x` (follow).
- Task `web` (mode agent) dikerjakan agent lewat `browser_session.py` (loop worker di SKILL.md); `manual` → `block` ke the owner.

## Batasan & biaya
- **X API**: pay-per-use (2026 ±$0.005/post dibaca, ±$0.010/user lookup); recent search 7 hari. Radar memakai
  `since_id` dan `x_max_reads_per_day` (default 300 ≈ maks ±$1.5/hari). Cek harga terbaru di developer.x.com.
- **Follow via API** (`POST /2/users/:id/following`) butuh OAuth user-context dan sejak Apr 2026 hanya tier Enterprise.
  Alternatif: browser follow (Playwright, profil login manual) **opt-in** `X_BROWSER_FOLLOW_OPTIN=I_ACCEPT_X_TOS_RISK`,
  cap `x_follow_cap_per_day` — melanggar ToS X, risiko limit/suspend; pakai akun khusus. Default: daftar follow manual ke Telegram.
- **Telegram join**: akun baru cepat kena FloodWait / spam-block. Default cap 15 join/hari, jeda 45–180 dtk,
  berhenti saat FloodWait. Batas ±500 channel/grup per akun. Radar memakai **session terpisah** (`TG_RADAR_SESSION`),
  jadi `tg_radar.py login` sekali (device kedua).
- Ganti semua placeholder `example_*` di `radar_sources.yaml` (selfcheck memperingatkan).

## Perintah
```bash
$PY scripts/radar/radar_runner.py dry-run                       # sample, sandbox, tanpa network/Telegram
$PY scripts/radar/radar_runner.py dry-run --risk on             # simulasi RISK=ON
$PY scripts/radar/radar_runner.py dry-run --file posts.txt --write   # tulis ke antrean asli
$PY scripts/radar/tg_radar.py login && $PY scripts/radar/tg_radar.py join --dry-run
$PY scripts/radar/x_radar.py poll --dry-run
$PY scripts/radar/radar_runner.py status
pm2 start templates/ecosystem.config.js --only airdrop-radar
```
