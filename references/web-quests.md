# 4. Airdrop Web & Quest Platform

## Mesin
`web_quest.py` = Playwright Chromium dengan **profil persisten** (`~/.airdrop-agent/browser/<profile>`).
Login X/Discord/Galxe sekali secara manual via VNC → cookie tersimpan → dipakai ulang.

Alternatif: tool `browser` bawaan Hermes boleh dipakai untuk riset/baca halaman, tapi
untuk aksi garapan pakai `web_quest.py` supaya allowlist domain, deteksi captcha, popup wallet
dan proof berjalan konsisten.

## Wallet di browser
| Mode | Cara | Aturan |
|---|---|---|
| Extension (Rabby/MetaMask unpacked) | `BROWSER_EXTENSION_DIRS`, headed di Xvfb | Import **burner** saja. Popup extension **tidak** di-klik agent; runner berhenti dan minta konfirmasi manusia via VNC. |
| SIWE via `siwe_sign.py` | Untuk platform yang menyediakan login dengan message (copy pesan SIWE → file → sign) | Hanya domain di `siwe_domain_allowlist`. |
| **Wallet ter-inject (`browser_session.py`)** — digabung dari airdrop-hunter | Provider EIP-1193 (`wallet_provider.js`) disuntik ke halaman; tiap request diteruskan ke Python | connect hanya ke origin allowlist + scam_check ok; `personal_sign`/typed data lewat `sign_guard`; tx lewat `safe_send` (simulasi, cap, allowlist, gate). Bisa headless, tanpa VNC. |

Aturan sign: SIWE murni boleh setelah cek; `eth_signTypedData` (Permit/Permit2/order), `eth_sign`
blind hash, `personal_sign` berisi hex tak terbaca → **tolak / gate**.

## Format steps
Lihat docstring `scripts/web/web_quest.py` dan contoh `templates/quests/*.yaml`.
Aksi: `goto, click, fill, press, select, wait, wait_for, screenshot, extract_text, wallet, human`.
Variabel: `${ENV:NAMA}`, `${OTP:pengirim}`.

## Pola per platform
- **Galxe**: login (email OTP / wallet SIWE galxe.com) → quest page → task social (Follow X,
  Retweet, Join Discord) → `Verify` per task → `Claim` (sering OAT/NFT di chain murah → bisa
  minta gas → gate kalau mainnet). Passport = KYC → **jangan otomatis**.
- **Zealy**: login Discord/X/email → community → quest board → submit (link tweet, screenshot,
  jawaban quiz). Quiz: jawaban dari docs resmi. Submission manual-review → hindari spam.
- **Layer3**: connect wallet (SIWE) → quests on-chain (bridge/swap/mint) → tiap tx onchain
  lewat `safe_send` + allowlist kontrak resmi → klaim CUBE (mint = tx).
- **QuestN / Intract**: mirip Galxe; Intract sering "streak harian" → masukkan ke `checkin`.
- **Points dashboard project**: check-in harian, connect X, referral → steps sederhana.

## Captcha
Terdeteksi (hCaptcha/reCAPTCHA/Turnstile) → screenshot + ping Telegram → tunggu manusia
(VNC) maks `HUMAN_WAIT_SEC`. Setelah selesai, captcha hilang dan runner lanjut, atau
`touch ~/.airdrop-agent/HUMAN_DONE`. Tidak ada bypass ilegal.

## Anti-phishing
- `allowed_domains` per steps file; redirect ke domain lain → abort.
- Punycode (`xn--`) selalu ditolak.
- Teks halaman dikembalikan dengan label UNTRUSTED dan sudah di-redact.

## Mode agent-driven: `browser_session.py`
Untuk agent yang mau "melihat" halaman dan memutuskan sendiri klik apa (bukan steps YAML):
```bash
python scripts/web/browser_session.py serve --label main-burner --chain sepolia &     # 127.0.0.1:8765 + token
python scripts/web/browser_session.py cmd goto '{"url":"https://app.galxe.com/quest/XYZ","project":"example-testnet"}'
python scripts/web/browser_session.py cmd snapshot            # teks + elemen bernomor (UNTRUSTED)
python scripts/web/browser_session.py cmd click '{"index":12}'
python scripts/web/browser_session.py cmd wallet_events       # log connect/sign/tx + alasan reject
python scripts/web/browser_session.py cmd stop
```
- `goto` otomatis `scam_check` (verdict block → ditolak).
- API kontrol hanya 127.0.0.1 + header token acak (`data/browser_token`). CDP mati kecuali `--cdp 9222`.
- Kalau page minta sign/tx yang butuh gate → page dapat error "waiting for owner approval #N"; setelah
  di-approve, ulangi aksi yang sama di halaman → lolos sekali.
