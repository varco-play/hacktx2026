# Demo guide

## Start

```bash
cd ConsentLens && scripts/run.sh          # Terminal.app; http://127.0.0.1:8000
```

Dashboard: pick **USB / external: <your phone>** in the source list → **Start session** → **Start voice** → **Start recording**. Profile: BALANCED (switch to ECO if the laptop runs hot; it also switches automatically).

## 2-minute script (two people, A and B)

| Time | Action | Expected |
| --- | --- | --- |
| 0:00 | A and B in frame | two IDs, both `UNKNOWN · visible` |
| 0:15 | A says **"please blur me"** (B silent) | chime + "You're blurred", A `DENIED`, voice log `→ person_A (av_sync …)` |
| 0:30 | B walks around | B stays visible, A stays blurred |
| 0:40 | B closes eyes for 2 s | B `DENIED (eyes closed)` |
| 0:55 | A turns sideways / looks away | A stays blurred ("face turned — following head") |
| 1:05 | A leaves for 5 s, returns elsewhere | "checking…" shield, then A matched, still blurred |
| 1:20 | A holds ✌ beside own face for 1 s | "You're visible again", A `GRANTED` |
| 1:30 | B holds ✌ next to **A's** face | nothing changes for B (must be their own face) |
| 1:40 | Stop recording → open the protected link | blur is in the saved video |
| 1:50 | Show Diagnostics panel | measured FPS, latency, CPU, thermal; "unavailable" where not measurable |

## What to say about Meta glasses (accurate version)

"ConsentLens treats glasses as a capture device. Our source layer accepts a USB phone camera today and a companion-app stream built on Meta's Wearables Device Access Toolkit 1.0. The iOS companion is written against the official CameraAccess sample, including the Mock Device Kit path, **but it isn't compiled or run yet** — today's demo uses the phone as the camera and the Mac as the processor. Processing is adaptive: we measured ~44% of one core at 10 fps vs ~105% at 30 fps on an M4, and the system drops to the eco profile automatically when macOS reports thermal pressure. We can't change recordings made by the glasses' own camera app; we protect footage captured through our app."

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Phone not in source list | unlock/hold iPhone still; check `system_profiler SPCameraDataType`; reconnect cable |
| Black preview / "camera not available" | grant Terminal camera access; restart `scripts/run.sh` |
| "CAMERA DISCONNECTED" slate | phone unplugged/locked; it reconnects to the same phone automatically |
| Buttons return 403 | refresh the page (needs the current dashboard code) |
| Voice "UNAVAILABLE" | `META_MODEL_API_KEY` missing; Start voice again |
| "Couldn't tell who said that" | speaker faces the camera and repeats; only one person talks |
| Laptop hot | choose ECO; check Diagnostics → thermal |
