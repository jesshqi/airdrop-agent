# 5. Akses Discord

## Akun
- Akun Discord **khusus garapan** (email agent, 2FA aktif, nomor HP sendiri). Bukan akun utama.
- Join server, verifikasi (Collab.Land, Guild.xyz, captcha bot, reaction role) dilakukan di
  browser profil Playwright yang sudah login — oleh manusia atau `web_quest.py` dengan step
  `human` untuk bagian captcha.

## Membaca pengumuman (disarankan, sesuai ToS)
1. Buat server pribadi + bot (Developer Portal), aktifkan **Message Content Intent**, invite bot
   ke server pribadimu.
2. Di server project, channel #announcements → **Follow** → arahkan ke channel di server
   pribadimu (fitur resmi Discord, hanya untuk Announcement Channel).
3. `DISCORD_WATCH_CHANNEL_IDS` = ID channel di server pribadi. Jalankan
   `discord_watch.py bot` (pm2: `airdrop-discord-watch`). Pesan berkata kunci diteruskan ke
   Telegram dengan peringatan pola scam.

## Mode user-token (OPT-IN, berisiko)
- Automasi akun user ("selfbot") **melanggar ToS Discord** → akun bisa di-ban permanen.
- Hanya aktif kalau `DISCORD_USER_TOKEN_OPTIN=I_ACCEPT_BAN_RISK`. Paket ini membatasinya
  **read-only** (polling pesan tiap 10–15 menit), tidak posting, tidak join, tidak klik.
- Token user = akses penuh akun. Simpan di `.env` saja; jangan pernah tampil di log/chat.

## Grind role lewat chat (level MEE6/Arcane)
Lihat `discord-role-grind.md` — `scripts/discord/chat_grinder.py`, opt-in, risiko ban tinggi.

## Role verification
- Wallet-based (Collab.Land / Guild): sign message verifikasi — cek domain resmi
  (`collab.land`, `guild.xyz`) dan isi message = SIWE/verification, bukan Permit. Kalau ragu → gate.
- Jangan pernah percaya DM "support"/"mod" — Discord adalah sumber utama drainer link.
