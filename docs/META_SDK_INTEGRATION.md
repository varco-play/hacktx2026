# Meta Wearables Device Access Toolkit (DAT) integration

**Status, honestly (2026-10-25):**

| Layer | State |
| --- | --- |
| Server side (Python): `CompanionStreamSource` + `/api/ingest` WebSocket | **Implemented and tested** (unit tests + end-to-end with `scripts/companion_sim.py`: 91 frames ingested, processed by the same engine) |
| iOS companion app (`ios/ConsentLensCompanion/`) using DAT 1.0.1 | **Written, NOT compiled** — the dev Mac has no Xcode (only Command Line Tools) |
| Mock Device Kit run (Mode B) | **Not run** — needs Xcode + iOS Simulator/iPhone |
| Real glasses (Mode C) | **Not tested** — no hardware |

Nothing in this repo should be described as a working Meta SDK integration until the iOS app compiles and the Mock Device Kit run below passes.

## Three input modes

| Mode | Path | Purpose |
| --- | --- | --- |
| A — USB phone camera (demo) | Phone camera → USB/Continuity → Mac → `AVFoundationCameraSource` → engine | Works today; the phone is a **camera substitute**, not an SDK emulator |
| B — Meta Mock Device | `MWDATMockDevice` simulated Ray-Ban Meta → companion app (DAT session + camera stream) → `/api/ingest` → `CompanionStreamSource` → engine | Validates the SDK lifecycle without glasses |
| C — Real glasses | Meta AI glasses → DAT (`MWDATCore`, `MWDATCamera`) → companion app → `/api/ingest` → engine | Same app code as B with the mock disabled |

The engine, consent logic, renderer and recorder are identical in all three — only the source adapter changes (`backend/app/capture.py`).

## What the SDK gives us (verified from the official repo, v1.0.1, 2026-10-25)

Source: `github.com/facebook/meta-wearables-dat-ios` (Swift Package, tags 1.0.x), `samples/CameraAccess`.

| Need | DAT 1.0.1 API (as used in Meta's sample) |
| --- | --- |
| Init | `try Wearables.configure()`; `Wearables.shared` |
| Registration (via Meta AI app) | `startRegistration()`, `registrationStateStream()`, URL callback `Wearables.shared.handleUrl(url)` |
| Devices | `devicesStream()`, `AutoDeviceSelector(wearables:)` |
| Session | `createSession(deviceSelector:)` → `DeviceSession`; `start()`, `stop()`; `statePublisher`, `errorPublisher` |
| Permission | `checkPermissionStatus(.camera)`, `requestPermission(.camera)` (redirects to Meta AI app) |
| Camera stream | `session.addCamera(config: StreamConfiguration(videoCodec: .hvc1, resolution: .low, frameRate: 24))` → `camera.stream.videoFramePublisher` (`frame.sampleBuffer`, HEVC), `statePublisher`, `start()`, `camera.stop()` |
| Mock Device Kit | `MockDeviceKit.shared.enable()`, `pairGlasses(model: .rayBanMeta)`, `powerOn/unfold/don/doff/fold`, `services.camera.setCameraFeed(fileURL:)` |
| Audio | Glasses mic reaches iOS over Bluetooth HFP (sample's `AudioCaptureHandler`); not part of the SDK video stream |
| Info.plist | `MWDAT` dict: `AppLinkURLScheme`, `MetaAppID`, `ClientToken`, `TeamID`; Bluetooth + local-network usage strings |

**Not found in the 1.0.1 sample:** glasses thermal or battery readings. The companion therefore reports the **phone's** `ProcessInfo.thermalState` and battery, labeled as phone metrics; glasses values show as "unavailable".

**Not possible with DAT:** intercepting or modifying recordings made by the glasses' own camera button / Meta AI app. ConsentLens protects footage captured **through the companion app** only.

## Companion app design (`ios/ConsentLensCompanion/Sources`)

| File | Role |
| --- | --- |
| `ConsentLensCompanionApp.swift` | `Wearables.configure()`, server URL + token, Mock toggle, registration URL handling |
| `GlassesSession.swift` | registration → session → permission → `addCamera` → frame listener; mirrors SDK state for the UI |
| `HEVCFrameDecoder.swift` | VideoToolbox HEVC decode → Core Image downscale → JPEG (GPU) |
| `FrameUplink.swift` | WebSocket uplink; **one frame in flight**, rate-limited (default 12 fps); skipped frames are never decoded |
| `MockGlassesController.swift` | DEBUG: pair mock Ray-Ban Meta, power on, unfold, don, feed a bundled clip |

Wire format (shared with `scripts/companion_sim.py` and tested in `tests/unit/test_sources.py`): one binary WebSocket message per frame = 4-byte big-endian header length + JSON header (`seq`, `origin`, `thermal_state`, `battery_level`) + JPEG. The server replies `{"ack": seq, "accepted": bool}` per frame.

## Running Mode B once Xcode is installed

1. Install Xcode 16+ from the App Store (large download; the build is CPU-heavy — do it when the laptop can run warm).
2. `brew install xcodegen && cd ios/ConsentLensCompanion && xcodegen` (or create an iOS App target and add `Sources/`, `Info.plist`, and the package `https://github.com/facebook/meta-wearables-dat-ios` @ 1.0.1 with products MWDATCore, MWDATCamera, MWDATMockDevice).
3. Add a short clip as `consentlens_test.mp4` to the app bundle (for the mock camera feed).
4. On the Mac: set `INGEST_TOKEN` in `.env`, run `scripts/run.sh --lan`, choose **Companion app** in the dashboard source picker, Start session.
5. Run the app (Simulator or iPhone, DEBUG): enter `ws://<mac-ip>:8000` + token, keep "Use Meta Mock Device" on, Connect → Register → Start glasses camera.
6. Record results per step below.

### Mock Device Kit test checklist (fill in when run)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 1 | Configure SDK | no error logged | NOT TESTED |
| 2 | Mock pair + power on + don | device appears in `devices` | NOT TESTED |
| 3 | Registration | state → registered | NOT TESTED |
| 4 | Session start | `sessionState == .started` | NOT TESTED |
| 5 | Camera stream | `streamState == .streaming`, frames forwarded > 0 | NOT TESTED |
| 6 | Server receives | dashboard source `companion:meta_mock_device (reported by app)`, faces tracked | NOT TESTED (server side passes with simulator) |
| 7 | Stop stream / session | states → stopped, server shows CAMERA DISCONNECTED slate after 2 s | NOT TESTED |
| 8 | doff / fold / power off | session/stream stop, app shows state, server degrades safely | NOT TESTED |
| 9 | Permission denied path | error shown, no crash | NOT TESTED |

## Production direction (beyond the hackathon)

The Mac is a stand-in for processing that would run **on the phone** (preferred: privacy, no upload) or an optional backend. Portable pieces: YuNet/SFace are ONNX (ONNX Runtime Mobile or Core ML conversion), MediaPipe has iOS/Android Tasks with the same `.task` models, and the consent policy/state machine is small deterministic logic to port to Swift/Kotlin. Not portable as-is: the Python process itself.
