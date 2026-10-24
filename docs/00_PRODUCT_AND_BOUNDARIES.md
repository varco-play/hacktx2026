# 00 — Product definition and frozen constraints

## Problem and proposed benefit

People wearing camera-enabled glasses can inadvertently record bystanders who don't want their **face shown in the wearable-owner accessible or shared footage**. ConsentLens is a camera privacy-layer prototype: detect individuals, recognize explicit objections conveyed in speech or an intentional eye-cover gesture, bind the request to the correct tracked person, selectively blur their face, and preserve that refusal during their return in the *same recording session*. Owner sees a processed output; demo can compare source/protected paths.

**One-line pitch:** “Say ‘please blur me’ and your face stays hidden, even when you leave and come back.”

## Critical semantics

- **Default appearance:** visually unblurred until an explicit objection is established. This is a *visibility state*, not presumed legal consent. New face after uncertainty is resolved may be visible; all candidates potentially matching a previously protected subject must be **temporarily shielded before identity decision**.
- **Speech path:** listen for phrases asking not to be shown; STT transcribes, structured LLM classifies semantics; visual active-speaker matching is **independent**. Only policy engine can commit consent state changes.
- **Gesture path:** sustained hand covering both eyes (optional after voice MVP); can create request without speech. Do not automatically treat eye rubbing as certain refusal.
- **Recognition:** session-local face embeddings and stable opaque IDs; no naming strangers, no across-session persistent biometric database, no remote collection in baseline. Return matching must occur before a protected person is exposed.
- **Authorization:** person can refuse; lowering hand/ceasing speech does NOT undo refusal. Future explicit reversal must require strong subject binding and owner decision about scope; not in MVP without approval. Owner cannot alone reveal a declined face.
- **Two videos:** source/diagnostic (restricted to consenting developers) and actually blurred output. Not a secure evidence-vault or integration with Meta corporate storage. Exported output may still contain **pre-objection footage**; document this honestly unless implementing delay/backfill before export.
- **Meta glasses:** device camera is **simulated by Mac webcam**. Future system-wide integration requires Meta first-party changes and policy review; SDK app-level camera access doesn't guarantee native recording enforcement.
- **Privacy:** face blur does not remove voice, clothing, background, tattoos, or contextual identifiers; do not promise anonymity or universal legality.

## MUST in minimum demo

Live laptop camera; 2 volunteers; 2 distinct current tracks; independent selective blur; actually encoded protected pixels; temporary session identity gallery; correct basic refusal classification; auditable timeline; fallback when speaker/identity uncertain; simple tested UI. Conduct live demonstration, not a prerecorded hidden substitution.

## SHOULD after MVP

Mouth dynamics synchronized with utterance times; controlled one-active-speaker tests; SFace re-entry; Meta Muse transcription API; Gemini intent model; protected/diagnostic video comparison, measured latency/FPS/leakage. Sponsor API integration must be **real** to be claimed.

## MAY if stable

Eye-cover trigger; TalkNet active speaker comparison; delayed output/backfill; camera source adapter; live new/return shielding; polished demo; Meta Muse Spark as alternate intent model; cloud-vs-local recognition benchmark.

## Explicit non-goals

No mass surveillance, crowds, criminal or identity lookup, persistent bystander face database, legal consent determination, facial emotion detection, unrestricted raw-video evidence sharing, automatic proof of speaker identity, arbitrary full-time video uploads to LLM, Meta firmware patch, cloud subscription/production auth, AWS recognition in per-frame hot loop, direct Gemini DB mutations, perfect privacy promise.

## Challenges to confront openly

1. A recorded refusal can occur seconds **after** the face was visible: the earlier frames remain exposed unless output is delayed or reprocessed. Recording only real-time processed pixels is not retroactive redaction.
2. A returning refused subject can be exposed during identity lookup unless shielded before match.
3. Speaker voice label does not equal visual person; lip motion is uncertain with noise, side profile, offscreen speakers, and simultaneous speech.
4. Database of faces creates biometric obligations even without names. Restrict to consenting demo participants.
5. Visible people may be comfortable filming but not public sharing; those are distinct permissions.

## Definition of success for judges

A repeatable live interaction, proof it affects a saved file, measurements from actual trials, a clear limitation statement, and a plausible Meta first-party integration proposal. Two-person project should beat one hard problem, not show ten APIs.
