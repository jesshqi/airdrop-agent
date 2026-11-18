# RISK mode (ON/OFF)

| | RISK=OFF (default) | RISK=ON |
|---|---|---|
| Temuan radar LOW/MEDIUM | task `pending_approval` + kode Telegram | langsung `pending` dan dikerjakan |
| Domain baru | gate `allow_domain` | otomatis di-allowlist **hanya jika scam_check = ok** |
| Connect wallet / SIWE / typed data "ask" | gate berkode | otomatis jika scam_check(origin) = ok |
| Tx testnet & mainnet | gate untuk mainnet, kontrak baru, > cap | otomatis dalam cap `risk_on` di policy.yaml |
| Laporan | digest + kode | setiap aksi otomatis langsung ke Telegram (apa, di mana, tx hash) + `logs/risk_auto.jsonl` |

## Menyalakan / mematikan
```bash
$PY scripts/core/risk_mode.py on --hours 6     # atau Telegram (owner): /risk on 6
$PY scripts/core/risk_mode.py off              # atau /risk off
$PY scripts/core/risk_mode.py status           # atau /risk status
```
- State di `~/.airdrop-agent/risk_mode.json` (menang atas env `RISK_MODE`). Auto kembali OFF setelah
  `risk_on.max_hours` (default 24). Env `RISK_MODE=on` **tidak** punya expiry, jadi lebih baik pakai toggle.
- `/risk` dari Telegram hanya dari `TG_OWNER_USER_ID`, dibaca oleh `task_queue.py sync` (atau `radar_runner run`
  dengan `RADAR_TG_SYNC=1`) — jadi ada jeda sesuai jadwal sync. Untuk berhenti seketika: `touch ~/.airdrop-agent/KILL`.
- RISK=ON diabaikan (dianggap OFF) kalau bot laporan Telegram belum dikonfigurasi, karena setiap aksi wajib dilaporkan.

## Cap terpisah (`policy.yaml → risk_on`)
```yaml
risk_on:
  max_hours: 24
  wallet_labels: [main-burner]       # hanya burner; label seperti main/cold/treasury selalu ditolak
  auto_allowlist_domains: true
  chains:
    sepolia: {max_tx_native: 0.05, max_daily_native: 0.5, max_gas_native: 0.01}
    base:    {max_tx_native: 0.0005, max_daily_native: 0.002, max_gas_native: 0.0003}
```
Chain tanpa entri `risk_on.chains` = tidak ada tx otomatis (kembali ke gate). Lewat cap = gate biasa (butuh kode).

## Hard block — TIDAK PERNAH dilewati, juga saat RISK=ON
1. KILL file (semua script exit 99; RISK dianggap OFF).
2. `eth_sign`, blind 32-byte hash, payload non-UTF8.
3. Unlimited approval (`approve`/`increaseAllowance` ≥ 2^255) dan typed data dengan jumlah ≥ 2^160−1; `setApprovalForAll(true)` tetap gate.
4. Permit / Permit2 / Seaport / meta-tx / delegation typed data di mainnet.
5. Situs pola claim / "connect wallet to claim" yang gagal heuristik drainer (scam_check ≠ ok atau domain baru) dan link `scam_check = block`.
6. SIWE domain ≠ origin halaman, alamat di blocklist, post injection.
7. Cap per-tx / harian / gas `risk_on`.
8. Main wallet tidak pernah di vault; hanya label di `wallet_labels`.
9. Key/seed/session tidak pernah dicetak atau dikirim.

## Risiko yang tetap ada
RISK=ON berarti agent bisa kehilangan seluruh saldo burner dalam batas cap harian setiap hari
(misal dApp jahat yang lolos scam_check). Isi burner secukupnya, cap mainnet kecil, nyalakan per sesi (`--hours`).
