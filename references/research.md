# 6. Browsing & Riset Airdrop

## Sumber (urut kepercayaan)
1. Docs/blog/X **resmi** project (cek link dari website resmi, bukan dari reply).
2. DefiLlama (airdrops list, raises, TVL), CryptoRank (funding, investor, drop hunting).
3. Airdrops.io, DropsTab, Galxe/Layer3 space resmi.
4. CT (X) — hanya sebagai sinyal; verifikasi ulang ke sumber resmi.

Gunakan tool `web`/`browser` Hermes untuk membaca. Cek otomatis:
- `scripts/web/scam_check.py <url> --project <id>` → verdict ok/warn/block (lookalike Levenshtein vs brand,
  punycode, IP, TLD berisiko, path phishing, domain resmi dari `projects.yaml`). `--text "..."` untuk pesan,
  `--add-block` / `--add-trusted` untuk daftar lokal. (digabung dari airdrop-hunter)
- `scripts/web/research_score.py --url ... --official ... --facts facts.yaml` → skor 0–100 + umur domain (RDAP).

## Checklist skor (isi `facts.yaml`, lalu jalankan script)
- Funding & investor (≥ $5–20M, tier-1) · token belum TGE · ada points/XP program
- Tim publik / track record · docs jelas · testnet/mainnet aktif
- Biaya garap (gas, deposit minimal) vs potensi · butuh KYC? · syarat anti-sybil
Verdict: ≥70 GO, 50–69 low-effort, <50 atau ada CRITICAL → skip.

## Red flag scam / drainer
- Domain mirip (`kinetlq`, `rnonad`), punycode, umur domain < 30 hari
- "Claim now", "connect wallet to check eligibility" sebelum ada pengumuman resmi
- Minta seed/private key, "validate/rectify wallet", approve/permit tak jelas, setApprovalForAll
- Link dari reply X, DM Telegram/Discord, iklan Google
- Kontrak tidak terverifikasi, token "airdrop" muncul sendiri di wallet (jangan di-swap/approve)

## Output ke user
Shortlist maks 5: nama · kategori · skor · biaya · link resmi (X + web) · langkah pertama.
Jangan menambahkan project ke `projects.yaml` tanpa persetujuan user.
