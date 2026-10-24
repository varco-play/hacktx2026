---
name: privacy-audit
description: Red-team ConsentLens for missed blur, identity swaps, unsafe fallback, and original-video exposure; propose minimal fixes and tests.
---

# Privacy adversarial audit

Inspect the actual repository and trace frame capture -> gesture/voice input -> identity state -> protected compositor -> preview -> recording. Do not infer that code exists from the plan alone.

Check at least these scenarios:
- Two faces; only person A covers both eyes long enough to activate. B stays visible if clearly unrelated.
- A lowers hands: A remains protected.
- A leaves, re-enters; privacy follows only when identity match is adequately supported. On ambiguity, fail safe in the protected output; do not falsely claim re-identification.
- Both people cross/occlude faces; identity swap risk and stale boxes.
- Face detector drops a protected person for a few frames or camera motion shifts the box.
- A cover gesture is too brief or only covers one eye: no unsupported confirmed activation.
- Ambiguous voice request, API timeout, malformed Muse Spark output, multiple people in frame.
- Original remains untouched-input; protected preview/API does not leak the original; stream/file flush on stop; no secret or raw face embedding is sent to LLM/frontend.

Output a severity-ranked table: scenario, observed or code-supported outcome, expected behavior, file/line, fix, verification. Clearly tag every conclusion as `verified by test`, `code inspection`, or `not tested`.

If asked to implement fixes, do one high-risk fix at a time, preserve ownership boundaries, and rerun focused tests. Do not add permanent biometric storage as a shortcut.
