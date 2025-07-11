# RFC‑Lite Workflow

This document defines **how Round Table Consensus evolves its written protocol and reference implementation**. The process is deliberately lightweight so that **humans *and* AI agents** can propose, review, and land changes using nothing more than GitHub Issues & Pull Requests.

---

## 1  Purpose & Scope

* Keep the canonical spec in sync with code.
* Guarantee every normative change is traceable.
* Allow parallel “small fix” PRs while bigger design shifts move through RFC review.

---

## 2  Directory & file conventions

```
/spec/        → Version‑tagged Markdown spec (e.g. round-table-consensus-v1.0.0.md)
/rfcs/
   draft/     → Open proposals (RFC‑NNN‑short-name.md)
   accepted/  → Merged proposals
   rejected/  → Closed without merge
.github/
   ISSUE_TEMPLATE/  → YAML files
   rfc-template.md  → One‑page RFC skeleton
```

---

## 3  Labels

| Label                                                                       | Meaning                      |
| --------------------------------------------------------------------------- | ---------------------------- |
| `area:spec`                                                                 | Touches the written protocol |
| `area:code`                                                                 | Simulator / tooling          |
| `type:question`                                                             | Clarification request        |
| `type:enhancement`                                                          | New behaviour                |
| `type:bug`                                                                  | Implementation defect        |
| `type:rfc`                                                                  | Formal proposal PR           |
| `status:draft` / `status:last-call` / `status:accepted` / `status:rejected` | RFC stage                    |

Create labels via **Repo → Settings → Labels**. Our GitHub Action moves the `status:*` label automatically when authors comment `/last-call` or maintainers comment `/accept` or `/reject`.

---

## 4  Roles

| Role           | Who can be one   | Powers                                     |
| -------------- | ---------------- | ------------------------------------------ |
| **Author**     | Any contributor  | Opens RFC PR, responds to feedback         |
| **Reviewer**   | Humans & AI bots | Inline comments, approve / request changes |
| **Maintainer** | Core team        | Merge, tag, and cut releases               |

> \[!TIP]
> Give AI reviewers their own GitHub identity (e.g. `@rtc-ai-reviewer`) so their comments are label‑filtered and auditable.

---

## 5  Lifecycle (6 steps)

1. **Open an Issue** → use a template. Labels distinguish spec vs code.
2. **Draft RFC** (if needed) → new branch `rfc/NNN-short-name`, add file to `/rfcs/draft/`, open Draft PR.
3. **Discussion** → lazy consensus: 72 h with no blocking feedback ⇒ author posts `/last-call` (label flips).
4. **Last‑Call window** → 48 h final objections. Maintainer then `/accept` or `/reject`.
5. **Merge** → file moves to `/rfcs/accepted/` or `/rejected/`. Bump spec version & CHANGELOG if accepted.
6. **Implementation** tasks tracked as regular `area:code` Issues referencing the RFC.

---

## 6  RFC Template (excerpt)

```md
# RFC‑NNN: <short title>
*Status*: Draft
*Issue*: #<id>
*Target version*: 1.1.0

## Motivation
...
## Proposal
...
## Backwards Compatibility
...
## Reference Implementation Checklist
- [ ] Spec patch
- [ ] Code change (#...)
- [ ] Tests pass
```

Full template lives at `.github/rfc-template.md`.

---

## 7  Versioning rules

| Change type                        | SemVer bump |
| ---------------------------------- | ----------- |
| Editorial / typo                   | `+0.0.1`    |
| Clarification (no behaviour shift) | `+0.1.0`    |
| Behaviour change                   | `+1.0.0`    |

Tag releases on `main` (e.g. `v1.1.0`) immediately after merging the spec patch.

---

## 8  Automation (optional)

* **Label‑Mover Action** – reacts to `/last-call`, `/accept`, `/reject`.
* **AI‑Review Action** – posts an LLM critique on every RFC Draft PR.
* **Spec‑diff CI** – fails build if `/spec/` changed outside an RFC PR.

---

## 9  Cheat‑sheet commands

```bash
# new RFC draft
issue=42
short-name=canonical-noaction
num=001

git switch -c rfc/$num-$short-name
cp .github/rfc-template.md rfcs/draft/RFC-$num-$short-name.md
# edit file ...

git add rfcs/draft/RFC-$num-$short-name.md
git commit -m "RFC-$num: canonical NoAction merge"
git push -u origin rfc/$num-$short-name
# open Draft PR, link Issue $issue
```

---

## 10  FAQ

**Q — Can I fix a typo in the spec without an RFC?**
Yes—open a PR that cites the Issue and uses label `area:spec`, `type:bug`. Maintainers may merge immediately if truly non‑normative.

**Q — What if a code PR requires spec changes?**
Split the work: land the RFC & spec bump first, then update the code in a follow‑up PR.

**Q — How are Conviction Point economics tweaks handled?**
Always via RFC because they affect long‑term fairness; simulation results should be attached to the PR.

---

> *This process keeps Round Table Consensus evolving quickly without sacrificing determinism or auditability.*
