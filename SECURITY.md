# Security policy

## Key handling

- Private keys and seeds never leave `~/.airdrop-agent`, and only there in the vault.
- The vault is AES-256-GCM with scrypt and AAD; moving a blob breaks decryption.
- `VAULT_PASSWORD` lives in `.env` (mode 0600). Lose it and the keys are gone — `aa vault export`
  with its own passphrase is the surviving backup.
- Logs and envelopes print addresses only. `.env` is git-ignored; never commit a real one.

## Scope of trust

The agent signs locally and talks to public RPCs plus whatever you configure. It has no telemetry,
no phone-home, and no hosted component. Third parties you may opt into: RPC providers, captcha
providers (2captcha/anticaptcha), FlareSolverr, and the sites you farm.

## Reporting

Open a private advisory on GitHub (Security → Report a vulnerability) or an issue with the envelope
`error` and matching `aa events` rows. Never paste a private key or `.env`; a public address and tx
hash are fine.

Include: version (`aa --version`), OS, command, and whether policy mode was `safe`, `balanced`, or
`turbo`.

## Out of scope for a report

- A site changing its DOM and a shipped quest missing a selector (`aa quest probe` then a PR).
- Turnstile failing in plain headless without a provider — documented behaviour, use `cf assist` or
  FlareSolverr.
- Points not converting to tokens.
