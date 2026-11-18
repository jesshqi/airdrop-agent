# 03 · Telegram: channel, bot referral, mini app

```mermaid
flowchart LR
  A[task telegram] --> B{action}
  B -- join --> C[tg_tasks join @channel]
  B -- start --> D[tg_tasks start @Bot --ref KODE]
  B -- klik --> E[tg_tasks read → click 'Claim']
  B -- mini app --> F[tg_tasks webapp @Bot → file URL] --> G[web_quest open --url-file / steps]
  E -- tombol URL --> H[scam_check domain dulu]
  C & D & E & G --> I[jeda 4-8 dtk, FloodWait ditunggu] --> J[done + proof]
```
- Bot yang minta seed / private key / kirim token dulu → scam → `block` + lapor.
- "Connect wallet TON/EVM" di mini app → gate, jangan pakai wallet utama.
- Batas wajar: ≤20 join/hari.
