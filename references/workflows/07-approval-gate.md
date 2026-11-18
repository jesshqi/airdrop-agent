# 07 · Approval gate

```mermaid
sequenceDiagram
  participant S as Script (safe_send / browser_session / task_queue)
  participant DB as SQLite gates
  participant T as Telegram topic
  participant U as the owner
  participant A as Agent
  S->>DB: gate pending (hash payload, hash kode)
  S->>T: 🔐 APPROVAL #12 ringkasan + "approve 12 A1B2C3"
  U->>A: approve 12 A1B2C3   (atau balas ke bot → task_queue sync)
  A->>DB: task_queue approve 12 A1B2C3 → approved
  A->>S: ulangi aksi yang SAMA (payload identik)
  S->>DB: consume gate → used
  S-->>A: dijalankan sekali
```
- Kode hanya muncul di Telegram. Agent tidak boleh mengambil kode dari tempat lain.
- Payload berubah (nilai, tujuan, data) = gate tidak berlaku.
- Selalu gate: mainnet, > cap, kontrak baru, approve/permit, connect ke domain baru, sign non-allowlist.
- Selalu ditolak: unlimited approval, eth_sign, Permit/Permit2/Seaport di mainnet, apa pun soal seed/key.
- **RISK=ON** (`references/risk-mode.md`): gate di atas di-auto-approve dalam cap `risk_on` + label burner, kecuali
  baris "Selalu ditolak", `setApprovalForAll(true)`, dan situs claim yang gagal heuristik drainer — itu tetap gate/tolak.
  Setiap auto-approve langsung dilaporkan ke Telegram.
