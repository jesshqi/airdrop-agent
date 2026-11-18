# 02 · Quest web (Galxe / Zealy / Layer3 / QuestN / Intract)

Dua mode:
- **Steps YAML (`web_quest.py`)**: quest yang langkahnya sudah jelas dan berulang.
- **Agent-driven (`browser_session.py`)**: agent membaca snapshot halaman lalu memilih klik; wallet ter-inject lewat guard.

```mermaid
sequenceDiagram
  participant A as Agent
  participant B as browser_session
  participant G as sign_guard / safe_send
  participant T as Telegram (the owner)
  A->>B: goto quest URL (scam_check)
  A->>B: snapshot → pilih elemen → click/fill
  B->>G: page minta connect / sign / tx
  alt aman (SIWE allowlist, tx sesuai policy)
    G-->>B: signature / tx hash
  else butuh persetujuan
    G->>T: 🔐 APPROVAL #N + kode
    T-->>A: the owner: approve N KODE
    A->>B: ulangi aksi → lolos sekali
  else berbahaya (Permit, unlimited, eth_sign)
    G-->>B: ditolak
  end
  A->>B: screenshot → proof
  A->>A: task_queue done --proof
```
Langkah:
1. `task_queue.py next --type web` → ambil task.
2. Steps: `$PY scripts/web/web_quest.py run --steps ~/.airdrop-agent/quests/<p>.yaml --task-id N`
   atau agent-driven: `serve --label main-burner --chain <c>` lalu `cmd goto/snapshot/click`.
3. Task sosial (follow/retweet) memakai profil browser yang sudah login X.
4. Captcha / KYC / Passport → `task_queue.py block N --reason captcha` → kamu selesaikan via VNC.
5. `done N --proof '{"shot":"..."}'`.
