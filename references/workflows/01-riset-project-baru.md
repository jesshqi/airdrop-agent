# 01 · Riset project baru

```mermaid
flowchart TD
  A[Sinyal: X, DefiLlama, CryptoRank, Airdrops.io] --> B[Buka website & X RESMI]
  B --> C[scam_check url --project]
  C -- block --> X[Buang + catat blocklist]
  C -- ok/warn --> D[isi facts.yaml dari sumber resmi]
  D --> E[research_score --facts]
  E -- <50 / critical --> X
  E -- >=50 --> F[Shortlist ke Telegram]
  F --> G{the owner setuju?}
  G -- ya --> H[tambah ke projects.yaml + import]
  G -- tidak --> X
```
- `$PY scripts/web/scam_check.py https://app.project.xyz --project project-x`
- `$PY scripts/web/research_score.py --url https://project.xyz --official project.xyz --facts facts.yaml`
- Agent **tidak** menambah project sendiri tanpa persetujuan.
