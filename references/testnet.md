# 9. Testnet: faucet, bridge, swap, deploy, mint, node

## Faucet
- Deklarasi di `projects.yaml > faucets` (http / web / telegram / manual), cooldown dicatat SQLite.
- Syarat umum & cara menangani:
  | Syarat | Penanganan |
  |---|---|
  | Akun GitHub/X/Discord umur tertentu | login manual di profil browser; jangan beli akun |
  | Saldo mainnet minimal (mis. 0.001 ETH) | isi burner sedikit di mainnet; tetap cap ketat |
  | Captcha | hand-off manusia via VNC. Solver pihak ketiga = opt-in, cek ToS faucet dulu |
  | Faucet PoW (mining di browser) | jalankan headed, biarkan, batasi CPU |
- Katalog faucet publik per chain (Sepolia, Hoodi, Base/OP/Arb Sepolia, BSC testnet, Amoy) ada di
  `templates/faucets.yaml` (dari airdrop-hunter; syarat `needs: login|captcha|mainnet_balance|github`).
  URL sering berubah — verifikasi ke docs resmi chain sebelum dipakai.

## Bridge testnet & swap
- Bridge resmi (mis. bridge Sepolia → L2 testnet) / DEX testnet resmi. Masukkan alamat kontrak
  router/bridge dari docs resmi ke `contracts_allowlist`, baru `safe_send --sig ...`.
- Swap butuh approve token → selalu exact amount (unlimited ditolak) dan melewati gate.
- Lebih mudah lewat UI: `web_quest.py` + popup wallet dikonfirmasi manusia.

## Deploy kontrak (Foundry)
```bash
curl -L https://foundry.paradigm.xyz | bash && foundryup
forge init ~/contracts/counter && cd ~/contracts/counter && forge build
python scripts/testnet/deploy_contract.py --project-dir ~/contracts/counter --contract Counter --chain sepolia --label main-burner --broadcast
```
Deploy di testnet tanpa gate kalau `allow_deploy_on_testnet: true`; mainnet selalu gate.
Verifikasi kontrak (opsional) `forge verify-contract` dengan API key explorer (simpan di `.env`).

## Mint NFT testnet
`safe_send.py --to <NFT> --sig "mint(uint256)" --args 1 --value-eth 0 --broadcast` — kontrak baru → gate.

## Aktivitas harian
`testnet_daily.py --chain sepolia --label main-burner --txs 2` (self-transfer jumlah acak kecil,
jeda 20–90 dtk). Tambah interaksi bermakna (swap, bridge, deploy) — aktivitas kosong berulang
sering dianggap sybil/bot.

## Node
- Cek spesifikasi resmi (CPU/RAM/disk), apakah insentif node resmi, dan port yang dibuka.
- Jalankan di user/container terpisah (Docker), jangan di user yang menyimpan vault.
- Key node (validator/operator) **bukan** burner wallet; simpan terpisah, backup offline.
- Monitor via pm2/systemd + laporan Telegram; jangan pakai script install `curl | bash` dari
  sumber tidak resmi.
