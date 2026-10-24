# 06 — Verification plan: tests that actually matter

No claim of “100%,” zero leakage, latency or identification accuracy without measured experiments. Use only informed consenting adult volunteers. Keep local fixtures anonymized/ephemeral. Add deterministic unit tests and real live trials.

## Automated unit tests (minimum)

1. LLM output schema rejects invalid intent/extra fields/target IDs/scores, ignores hallucinated tool instructions.
2. Policy: `DENY + SELF + reliable same-turn MATCHED` -> correct person protected. Third-person hearsay, negation (“don't unblur me”), ambiguous/offscreen voice -> no unauthorized reveal.
3. Denied identity persists across motion tracker disappearance and start/stop of recording within same session.
4. Re-ID one-to-one: two simultaneous faces never share person ID; nonmatch cannot overwrite protected gallery.
5. Duplicate final/partial transcriptions do not create duplicate decisions; stale prior-session turns ignored.
6. Renderer doesn't mutate source input; protected writer never receives unmodified input for known protected/uncertain regions, even after detector error.
7. Paired recorded outputs finalize playable, timestamps monotonic, protected face visibly pixel-changed, lengths plausible.
8. Low/high capture queue load: bounded backlog, no stale-frame mismatches, shield on exception rather than raw fallback.
9. API health/settings endpoints never expose API keys, embeddings or raw frames.
10. Session end removes biometric gallery and respects intended media cleanup scope.

## Live trials matrix

| Scenario | Pass condition | What failure reveals |
| --- | --- | --- |
| A and B visible, nobody objects | both visible, state `VISIBLE_NO_REQUEST` | mistaken permission inference |
| A says explicit refusal, B silent | A blurred, B visible after verified association | voice-person binding |
| B speaks with moving mouth; A silent | B correctly selected | bias to nearest/largest face |
| Both speak / off-screen refusal | unresolved + shield/pause, NO random person | unsafe speaker attribution |
| “My friend said yes” | no permission for friend | semantic hallucination |
| “Don't unblur me” | no grant | negation robustness |
| A says no, later says yes | A remains protected until verified reauthorization flow exists | unsafe reversal |
| A leaves and returns opposite side | temporary shield then same person ID and denial restored | re-ID privacy leak |
| A/B cross in front of camera | no confident swap; shield uncertainty | tracker ID switch |
| New C resembles A | candidate shield until match decision, avoid false attach | recognition false positive |
| A occludes face/turns sideways | protected or full shield; never raw fallback | occlusion problem |
| Gesture: hands on eyes vs rub/glasses | deliberate sustained cover only (optional) | UX false trigger |
| Camera or detector model exception | protected output shielded/stopped | fail-open |
| Internet disconnect after first denial | existing blur continues; voice degraded announced | cloud coupling |
| Record, stop and inspect file | actual persistent blur pixels, no missing frames mislabeled | preview-only illusion |
| Objection 5s after start | disclose 5s earlier unblurred or prove delayed/redacted output | retroactive exposure |
| Reset and start new session | documented reset behavior | claim of enforcement after restart |

## Collect data honestly

`evaluation/trials.csv` columns:

```csv
trial_id,session_id,scenario,subject,expected_target_id,actual_target_id,auto_matched,uncertain,leak_frames,false_protect,source_fps,processed_fps,preview_age_ms,utterance_to_apply_ms,notes
```

For minimum credible report, target 10 repeats each of refusal, speaker attribution, return, false gesture and occlusion if time allows; report `n/N`, not universal “accuracy.” Track protected-person **exposure frames** specifically after refusal, during re-entry, and before late refusal. Note that earlier visible-by-default footage remains a deliberate limitation. Use p50/p95 only with enough samples and disclose sample size.

## Judge proof

Have one side-by-side *controlled developer diagnostic* showing original/processed saved files (not only browser CSS), one event timeline `A refused -> protection latched -> A exited -> re-identified`, live run, failure-case explanation, measured FPS. Do not expose raw recording to ordinary users by default. Feature-list each item as “working,” “experimental,” or “future”.
