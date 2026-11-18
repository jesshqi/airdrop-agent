# 10. Laporan ke Telegram

Pakai setup yang sudah ada: bot → grup forum → topic tertentu.

```
TG_REPORT_BOT_TOKEN=...      # bot dari BotFather (boleh bot laporan yang sudah ada)
TG_REPORT_CHAT_ID=-100...    # ID grup
TG_REPORT_TOPIC_ID=123       # message_thread_id topic (kosongkan untuk grup biasa)
```
Cara cari topic id: buka topic di Telegram Web → URL `.../c/<chat>/<topic_id>`; atau
`getUpdates` setelah kirim pesan di topic → field `message_thread_id`.

```bash
python scripts/core/report_telegram.py "<b>Garapan</b> selesai: 3 task"
python scripts/core/report_telegram.py --photo ~/.airdrop-agent/proofs/final_x.png "proof Galxe"
python scripts/wallet/wallet_balance.py --all | python scripts/core/report_telegram.py - --plain
```
- Semua teks di-redact otomatis, dipecah per 4000 karakter, retry `retry_after`.
- Kode approval gate dikirim **hanya** lewat sini.
- Format ringkasan: ✅/❌ per project · streak · tx hash (link explorer) · task yang butuh manusia.
- Kalau bot yang sama dipakai bot lain (mis. bot Cupang), aman — hanya `sendMessage`;
  jangan jalankan `getUpdates` polling dari dua proses untuk bot yang sama.
