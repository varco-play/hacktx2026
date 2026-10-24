# 10 — HackTX judging, pitch, technical proof

## Goal

Prove a new, visually demonstrable privacy interaction with a credible first-party Meta integration proposal. Meta 2026 sponsor prompt: build AI-powered social products that help connect people; using Meta's Muse tools is encouraged, not automatically mandatory. If Meta tools aren't integrated, state it. Main prize for Meta top 3: second-round event invitation, per ceremony slides. Also explore Best Overall and Best Pitch; confirm any per-track selection rules on Devpost/Discord. Never assume three distinct projects permitted.

## 120-second demo script (adapt to what ACTUALLY works)

**0–15s:** “Smart glasses capture moments, but a bystander can't control how their face appears in shared media.”

**15–30s:** Show two consenting demo volunteers with normal visible faces and individual IDs in webcam camera. Clarify absence of refusal isn't proof of legal consent.

**30–55s:** Volunteer A says “Please blur me.” Show real STT utterance text and active speaker evidence/mouth movement candidate, then validated `DENY` event. A blurred, B stays visible.

**55–75s:** A leaves, returns on other side; shield while matching; known denied state restored. B remains unblurred. If re-ID incomplete, label experimental rather than pretending it succeeded.

**75–95s:** Stop recorder, play **actual saved** protected output (no fake CSS overlay), show privacy event timeline. If original diagnostic displayed, explain access is **developer-only**, not secure vault.

**95–110s:** Mention architecture and actual integrated Meta Muse Voice model or alternate, Gemini structured interpretation, local vision for low latency. Explain why no cloud face recognition in hot loop.

**110–120s:** State two hard boundaries: early unblurred frames before objection and no native glasses enforcement without Meta first-party integration. End with why predictable bystander control could improve trust in camera-mediated social interaction.

## High-value judge evidence

- Live camera after real speech (not canned phrase overlay), face-specific independent blur.
- Re-entry test and event ID. No exposed frames during *tested* re-entry or transparent failure counter.
- Measured local FPS, frame processing duration, voice turn-to-activation latency and trial counts, not simulated metrics.
- Honest vendor integration status (working Muse/Gemini vs fallback).
- Rehearsed “why not AWS” explanation: cloud FaceIds not speaker identity; local processing minimizes latency, cost, data transmission.
- Does NOT claim to run as a compulsory feature on stock Meta glasses.
- Pilot customer: conference/event videographer with measurable editing workload; not established commercial buyer.

## Likely judge questions and answers

**Who spoke?** Visual active-speaker evidence synchronized to the turn, not Gemini. Ambiguous cases fail conservatively. Mouth heuristics are not definitive; tests and limitations disclosed.

**Why an LLM?** To understand varied language, negation, indirect requests; deterministic policy handles real permission state. Fixed expressions should be handled without network round trips.

**Why persistent IDs?** To associate an opted-out volunteer with later appearances in the same session. Local in-memory facial embeddings are sensitive and deleted at end; production privacy/legal questions remain.

**Does this prevent recording?** No. It modifies owner-facing shared footage in our app. It does not prevent raw capture or all identification.

**What about earlier footage?** Visible-by-default allows exposure before refusal. Backfill/delayed publish would be future improvement unless implemented and demonstrated.

**Can wearer override?** Not a denial in MVP. Subsequent explicit subject-verified consent reversal is future workflow.

**How does it work on Meta glasses?** We simulate camera input via Mac and propose Meta first-party protected media integration. Public DAT does not automatically enforce every native recording.

## Submission checklist

- [ ] Final Devpost deadline rechecked with organizers; code written during allowed period.
- [ ] Source repo commit/README with reliable local setup steps, models/licenses list, no secrets/biometric video.
- [ ] Protected video from real engine playable; demo fallback clip labeled recording.
- [ ] Build architecture diagram and actual API/model attribution.
- [ ] Working vs experimental vs proposed labels accurate.
- [ ] Actual measurements recorded with sample sizes and known failing cases.
- [ ] Pitch and optional pitch-signup confirmed in event Discord.
- [ ] Consent of demo participants; diagnostic originals deleted or kept with explicit agreed retention.
