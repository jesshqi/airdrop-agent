# 04 · Testnet & faucet

```mermaid
flowchart TD
  A[faucet_claim --project] --> B{tipe faucet}
  B -- http --> C[POST alamat burner] --> R
  B -- web --> D[web_quest steps] --> E{captcha?}
  E -- ya --> F[✋ Telegram, kamu solve via VNC] --> R
  E -- tidak --> R
  B -- telegram --> G[kirim /faucet alamat ke bot] --> R
  B -- manual --> H[kirim link + syarat ke Telegram]
  R[catat cooldown] --> I[testnet_daily: self-transfer kecil]
  I --> J[interaksi bermakna: swap / bridge / mint via safe_send + allowlist]
  J --> K[deploy_contract Foundry] --> L[proof tx → task_queue]
```
- Katalog faucet: `templates/faucets.yaml`. Deklarasi per project: `projects.yaml > faucets`.
- Semua tx: `scripts/wallet/safe_send.py` (simulasi, cap, allowlist; kontrak baru = gate).
- `$PY scripts/testnet/testnet_daily.py --chain sepolia --label main-burner --txs 2`
- `$PY scripts/testnet/deploy_contract.py --project-dir ~/contracts/counter --contract Counter --chain sepolia --label main-burner --broadcast`
