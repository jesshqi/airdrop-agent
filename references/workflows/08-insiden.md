# 08 · Insiden

```mermaid
flowchart LR
  A[anomali: saldo turun, approval asing, login asing, pause aneh] --> B[touch ~/.airdrop-agent/KILL]
  B --> C[pindahkan sisa dana burner manual] --> D[revoke approval revoke.cash]
  D --> E[terminate sesi Telegram, ganti password/2FA Discord & Gmail]
  E --> F[rotasi token bot, API key, VAULT_PASSWORD, burner baru] --> G[audit logs/agent.log]
  G --> H[rm KILL hanya setelah yakin]
```
