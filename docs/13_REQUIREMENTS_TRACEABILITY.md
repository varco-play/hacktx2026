# 13 — Requirements traceability and explicit trade-offs

**Purpose:** prevent loss of important requirements as Claude/Codex, human teammates, and the owner iterate. The two historical plans are preserved under `history/`. This is a requirements crosswalk, **not proof of completed functionality**. Owner's latest explicit instructions supersede history; unresolved decisions must be stated.

| Origin and user's intent | Current rule / owner-facing wording | Where implemented/tested | Status |
|---|---|---|---|
| Meta glasses video shooting normally | Webcam-simulated glasses source, **visible by default unless an objection**, not blanket legal consent | `00`, `03`, `06` | MVP scope; native Meta enforcement future |
| Human says “don't film me” | Live STT → Gemini/Muse small validated intent enum; no arbitrary tools | `03`, `04`, `07`, `12` | Mandatory voice-path attempt; live provider access contingent |
| Person in frame who spoke is blurred | Video-audio sync + mouth movement/ASD and conservative speaker-to-`person_id` linking | `03`, `04`, `06` | Core R&D risk; may remain conditional |
| Offscreen voice should not blur a random visible person | Mark `UNRESOLVED`, shield/pause protected view until safe resolution; explicit UX limitation | `03`, `04`, `06` | Safety rule |
| Person covers eyes long enough | Separate sustained gesture candidate and body/face association, not an accidental hair/eye touch | `00`, `03`, `05`, `06`; history V1 | Optional after stable voice path; do not delete requirement |
| Each face gets a unique remembered record | Motion `track_id` **different from** session-only `person_id`; local embedding gallery via SFace; no AWS global identity promise | `03`, `04`, `09` | Core |
| Person leaves/returns and blur resumes | Re-ID prior to showing protected candidate unblurred; threshold + multi-frame stability + shielding pending decision | `03`, `04`, `06` | High-priority differentiator |
| “It's okay to film now” unblurs person | Record request but **do not perform unblur automatically**; requires subject-bound verification designed and owner-approved separately | `00`, `01`, `04`, `12` | Product idea retained, not in MVP |
| Original footage saved separately for incidents | Developer diagnostic original only with informed volunteer consent, while protected copy is ordinary preview/export | `03`, `07`, `09`, `10` | Local comparison only; secure evidence custody future |
| Original accessible only to Meta, not wearer | **Not supported** by webcam/stock glasses SDK; requires trusted first-party Meta media pipeline, policy/legal approval | `00`, `03`, `09` | Future hypothesis, do not claim built |
| AWS as face DB / best performance | On-device YuNet + SFace/temporary registry wins for cheap hot loop; Rekognition isolated optional test | `02`, `03`, `07` | Cloud optional; opt-in biometric constraints |
| Meta should be impressed | Real third-party Meta API call if accessible; technical differentiator is robust attribution + persistently correct redaction; no fake sponsor integration | `05`, `06`, `07`, `10` | Evidence-driven |
| Two people / Claude + Codex code merges | One repo, one camera owner, one state registry, contract-first non-overlapping branches, tested PR/handoff | `04`, `08`, `11`, `AGENTS.md`, `CLAUDE.md` | Required workflow |
| Production buyer and real-world use | Explicit threat model, limitations, wearer vs bystander incentives, evaluate customer utility and privacy harms | `00`, `09`, `10` | Research not proven |

## Open contradictions — never paper them over

1. **Default visible vs whole-video opt-out:** the first seconds of a refusing person's recorded appearance can remain unblurred. Either explicitly limit the claim to frames after activation, or implement a delayed buffer/backfill and verify it.
2. **Default visible vs returning protected person:** re-ID needs a temporary shield or buffer; recognize this short protective exception to default visibility.
3. **Automatic voice command vs who spoke:** neither ASR speaker labels nor Gemini semantics reliably identify the face. Use synchronized visual evidence and reject unclear attribution; optional manual confirmation must be labeled if used.
4. **Face protection vs not being recorded at all:** face blurring cannot satisfy every “don't record me” request; production needs a stop-capture policy where appropriate.
5. **Recognition vs avoiding biometrics:** even ephemeral embeddings are biometric features. Only consenting volunteers for demo; never claim anonymous processing merely because IDs are opaque.
6. **Owner reauthorization vs wearer control:** the wearer cannot override someone else's denial. The MVP omits unblurring; future subject-authenticated reversal is a distinct workflow.
7. **Evidence original vs wearer inaccessible:** a second local file does not make a tamper-proof or Meta-managed vault. Secure escrow is *not implemented*.
8. **Hackathon speed vs correctness:** a visually convincing 5-hour demo is not production-grade reliability. Record n/N trials, failures, precise scope.
9. **Voice provider choice vs sponsor:** Gemini intent and Muse ASR may both be used *if actual access works*. Do not require multiple AI cloud services before testing on local camera.

## Change-control mini-template

Whenever the owner modifies product behavior, append to `DECISIONS_LOG.md`:

```text
Date/time:
Exact requested change:
Previous behavior replaced:
Privacy/security impact:
Contracts/tests/docs updated:
Approved by owner (or safely deferred):
```

When a feature is cut from the hackathon MVP, move it to *future/experimental* with reason instead of erasing its original purpose.
