# Phone as the glasses camera (Mode A)

The phone is a **camera substitute** for the glasses. Processing runs on the Mac.

## Connect

- **iPhone (Continuity Camera):** same Apple ID on Mac and iPhone, Wi-Fi + Bluetooth on, iPhone locked and held still in landscape (a USB cable works too). It appears as a camera named after the iPhone.
- **Android / other:** a UVC webcam app over USB (e.g. Camo, DroidCam, Iriun). It appears as an external camera.

Check what macOS sees:

```bash
system_profiler SPCameraDataType | grep -E "^\s{4}\S.*:$"
```

## Permissions

Start the server from **Terminal.app** (`scripts/run.sh`). The first session triggers macOS prompts for **Camera** and, when you click Start voice, **Microphone** for Terminal. If no prompt appears: System Settings → Privacy & Security → Camera / Microphone → enable Terminal, then restart the server.

## Select the camera

The dashboard's source picker lists every camera with its type ("USB / external" or "Built-in"). By default ConsentLens picks the **first external camera** (your phone), otherwise the built-in one. To pin a device: `CAMERA=iPhone` (any part of the name) or `CAMERA=1` (index) in `.env`.

The session is bound to that **physical device** (AVFoundation unique ID). If the phone disconnects, the preview shows a "CAMERA DISCONNECTED" slate, the recording receives no frames, and the app retries the **same** phone every 2 s — it never silently switches to the laptop camera.

## Audio

Voice commands use the **Mac's** microphone (the only input on this machine today). The video may come from the phone, so audio and video come from different devices: both are stamped on the server's monotonic clock on arrival. Expected offset: camera transport + capture delay (tens of ms over USB, more over Wi-Fi Continuity) versus ~100 ms mic chunks. The speaker matcher searches lags of ±200 ms when correlating lips with loudness, which covers this. If speaker matching is weak with the phone, keep the Mac close to the people talking.

## Start

```bash
scripts/run.sh            # open http://127.0.0.1:8000
```

Pick the phone in the source list → Start session → Start voice → Start recording.
