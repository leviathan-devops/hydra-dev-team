# OpenFang Repository — Restoration Notice

## Status: KERNEL RESTORED

On 2026-03-01, the OpenFang Rust kernel (202,096 lines, 14 crates) was accidentally deleted
from this repository and replaced with a Python stub during a nuke-reload operation.

## What Happened
- Commit `af56502` deleted ALL Rust source files
- The entire kernel was replaced with ~359 lines of Python Flask code
- This affected all downstream services (Railway, Discord bots, all 5 agents)

## Recovery
- The Rust kernel was recovered from git history on 2026-03-02
- A dedicated recovery repo exists at: `leviathan-devops/openfang-kernel-recovered`
- This branch (`restore/kernel-v1`) marks the official restoration point

## Version History
- The original Rust kernel exists in this repo's git history (pre `af56502`)
- The contaminated Python stub exists on `main` (post `af56502`)
- The restoration branch preserves both histories
- The dedicated recovery repo has the clean Rust code with 5-layer protection

## Guardrails Installed
1. Branch protection on openfang-kernel-recovered (requires PR + review)
2. CODEOWNERS file (owner review required)
3. CI/CD integrity checks (Rust line count, crate count)
4. Pre-commit hook (blocks mass .rs deletion)
5. Standing Order #18: OPENFANG KERNEL IS SACRED

## Contact
Owner: cryptoforex36963@gmail.com
