# 1. Wallet sendiri (burner)

**Tujuan:** agent punya wallet sendiri yang terpisah total dari wallet utama the owner.

## Aturan
- Wallet utama / seed utama **tidak pernah** masuk VPS, `.env`, extension, atau chat.
- Burner dibuat oleh `wallet_create.py` → keystore V3 (scrypt) di `vault/evm/<label>.json`,
  password `VAULT_PASSWORD` dari env. Solana: scrypt + AES-GCM di `vault/sol/`.
- Output hanya alamat publik. Script menolak menimpa key lama (O_EXCL).
- Maks 5 wallet sekali buat (anti-sybil). Disarankan 1 burner per identitas.
- Isi saldo kecil saja. Kalau dapat hasil airdrop bernilai → user sendiri yang sweep ke
  wallet utama (manual, di luar agent), atau gate `tx` mainnet.

## Perintah
```bash
python scripts/wallet/wallet_create.py --label main-burner --solana
python scripts/wallet/wallet_balance.py --chain sepolia --label main-burner
python scripts/wallet/wallet_balance.py --all
python scripts/wallet/safe_send.py --chain sepolia --label main-burner --to 0xADDR --value-eth 0.001          # dry-run
python scripts/wallet/safe_send.py --chain sepolia --label main-burner --to 0xADDR --value-eth 0.001 --broadcast
python scripts/wallet/safe_send.py --chain sepolia --label main-burner --to 0xERC20 --sig "approve(address,uint256)" --args 0xSPENDER 1000000 --broadcast   # selalu gate
```

## Pipeline `safe_send.py`
1. KILL check → chain ada di `policy.yaml` dan RPC chain_id cocok (anti RPC palsu).
2. Decode calldata: `approve/increaseAllowance` ≥ 2^255 → **DITOLAK keras**. Approve biasa,
   `setApprovalForAll(true)` → gate.
3. Kontrak belum di `contracts_allowlist` → gate. Alamat di `blocklist` → tolak.
4. Cap per-tx, cap harian (ledger SQLite), cap gas.
5. `eth_call` + `estimateGas`. Revert → stop, tidak broadcast, tidak retry otomatis.
6. Mainnet → gate (default). Gate kirim kode ke Telegram; jalankan ulang dengan `--gate-id`.
7. Sign lokal → broadcast → tunggu receipt → simpan proof `proofs/tx_*.json`.

Setelah gate di-approve, `safe_send` otomatis memakai gate approved yang payload-nya identik
(tanpa `--gate-id` juga bisa) — dipakai oleh wallet ter-inject di `browser_session.py`.

Exit code: 0 ok · 2 ditolak policy · 3 simulasi gagal · 10 menunggu manusia · 99 KILL.

## Sign message
- Kebijakan sign terpusat di `scripts/wallet/sign_guard.py` (digabung dari airdrop-hunter, diperketat):
  SIWE hanya kalau domain pesan = origin halaman **dan** ada di allowlist; teks biasa hanya di origin allowlist;
  hash 32-byte / data biner → blok; typed data Permit/Permit2/Seaport → blok di mainnet, gate di testnet;
  typed data yang punya field aset (spender, amount, token…) → gate.
- SIWE (EIP-4361) murni dari CLI: `siwe_sign.py` (cek domain allowlist, alamat, expiry, kata berbahaya).
- **EIP-712 typed data (Permit, Permit2, Seaport order) tidak pernah di-sign otomatis.** Itu
  cara utama drainer. Selalu gate + user baca isinya.

## Solana
Disediakan penyimpanan key + alamat. Untuk tx Solana, tambahkan script dengan pola sama
(simulateTransaction dulu, cap, gate) sebelum dipakai — belum ada sender Solana di paket ini.
