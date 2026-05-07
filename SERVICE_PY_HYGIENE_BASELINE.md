# SERVICE.PY HYGIENE BASELINE

## Purpose
This document defines the authoritative hygiene baseline for:

- `backend/api/service.py`

It exists because `service.py` is a legacy, high-debt backend file that remains operationally critical to production behavior. Future work in this file must follow a stricter, evidence-first standard to avoid silent scope expansion and unintended regressions.

---

## Current Authoritative Status

### Runtime status
`backend/api/service.py` is actively used in production and contains critical API, health, auth-adjacent, and worker-observability logic.

### Structural status
`backend/api/service.py` contains broad, pre-existing whole-file lint debt. This debt is known and documented. It must not be confused with newly introduced defects in future micro-diff phases.

### Repository policy status
The repository's primary lint/format tool configuration is defined in:

- `pyproject.toml`

Configured tool surfaces currently include:

- Black
- Ruff
- MyPy
- Pytest

There is no approved repository-wide decision in this baseline to mute or hide `service.py` lint debt using `per-file-ignores`.

---

## Proven Baseline Reality

A read-only audit established that `backend/api/service.py` contains broad, multi-cluster whole-file lint findings, including but not limited to:

- imports not at top of file
- unused imports
- blank-line spacing issues
- whitespace issues
- long lines
- f-strings without placeholders
- hanging-indent alignment issues

This debt is legacy debt, not evidence that every future small change in the file is unsafe.

---

## Authoritative Rule for Future Micro-Diffs in service.py

Unless a dedicated full-file cleanup/refactor phase is explicitly authorized, future small scoped changes inside `backend/api/service.py` must follow this rule set:

1. **Evidence first**
   - read-only audit before edits when risk or behavior sensitivity justifies it

2. **Smallest robust change only**
   - no opportunistic cleanup outside the exact task scope

3. **Changed-line cleanliness is authoritative**
   - whole-file debt may remain
   - changed lines must not introduce new lint findings

4. **Syntax must remain valid**
   - Python syntax validation is mandatory

5. **Encoding must remain clean**
   - UTF-8 without BOM
   - no mojibake introduced

6. **Protected-file discipline remains active**
   - unrelated protected files must remain untouched

7. **Behavior changes require explicit review**
   - no silent logic changes while performing hygiene work

---

## What This Baseline Explicitly Rejects

The following are not acceptable unless explicitly authorized in a dedicated phase:

### 1. Whole-file cleanup disguised as a small task
No broad formatting, import reordering, or lint sweeping of `service.py` may be bundled into unrelated functional work.

### 2. Silent lint-policy weakening
Do not introduce broad ignores or per-file muting for `service.py` without a separately reviewed policy decision.

### 3. Hygiene mixed with runtime behavior changes
If behavior changes are needed, they must be reviewed and validated as behavior changes, not hidden inside cleanup.

---

## When a Dedicated service.py Refactor Phase Is Justified

A separate full-file or multi-cluster cleanup phase may be justified only when all of the following are true:

- the scope is explicitly authorized
- the phase is treated as refactor/hygiene, not incidental cleanup
- review and rollback risk are acceptable
- runtime-sensitive areas are protected by explicit validation
- the expected long-term value is greater than the regression risk

Until then, the authoritative operational rule remains:

> `backend/api/service.py` is a legacy high-debt file governed by strict micro-diff discipline and changed-line cleanliness.

---

## Relationship to Deploy Observability

This baseline was formalized after the successful closure of the deploy-fingerprint health work:

- P2.5 HEALTHZ-REVISION-FINGERPRINT-01
- P2.5R HEALTHZ-COMMITSHA-RUNTIME-01

That task chain validated the importance of keeping service.py changes:
- minimal
- explicit
- evidence-backed
- production-verified

This baseline preserves that standard for future work.

---

## Practical Review Checklist for Future service.py Changes

For future scoped edits in `backend/api/service.py`, reviewers should expect proof of:

- exact scope and target lines
- clean working tree before edits
- syntax validation
- UTF-8 / BOM integrity
- changed-line lint cleanliness
- explicit confirmation that unrelated protected files were not touched
- runtime validation when behavior is affected

---

## Final Baseline Statement

This document is the authoritative hygiene baseline for `backend/api/service.py` until a dedicated refactor phase replaces it with a newer approved standard.
