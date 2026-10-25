// Meta Wearables Device Access Toolkit 1.0.1 lifecycle for ConsentLens.
// API usage mirrors Meta's official CameraAccess sample (configure -> register -> device
// selector -> DeviceSession -> addCamera(StreamConfiguration) -> videoFramePublisher).
// STATUS: written against the 1.0.1 sample; NOT yet compiled (no Xcode on the dev Mac).
//
// The glasses only capture + stream. This app decodes frames, drops to the uplink rate,
// and forwards them to the ConsentLens processing server; nothing heavy runs on the glasses.

import CoreMedia
import Foundation
import MWDATCamera
import MWDATCore
import Observation

@Observable
@MainActor
final class GlassesSession {
  // Mirrored SDK state for the UI
  var registrationState: RegistrationState
  var devices: [DeviceIdentifier] = []
  var sessionState: DeviceSessionState = .idle
  var streamState: StreamState = .stopped
  var framesReceived = 0
  var lastError: String?

  private let wearables: WearablesInterface
  private let selector: AutoDeviceSelector
  private var session: DeviceSession?
  private var camera: Camera?
  private var tokens: [Any] = []          // listener tokens: kept alive while subscribed
  private var tasks: [Task<Void, Never>] = []
  private let decoder = HEVCFrameDecoder()
  let uplink: FrameUplink

  init(wearables: WearablesInterface, uplink: FrameUplink) {
    self.wearables = wearables
    self.uplink = uplink
    self.selector = AutoDeviceSelector(wearables: wearables)
    self.registrationState = wearables.registrationState
    tasks.append(Task { [weak self] in
      for await state in wearables.registrationStateStream() { self?.registrationState = state }
    })
    tasks.append(Task { [weak self] in
      for await devices in wearables.devicesStream() { self?.devices = devices }
    })
  }

  func register() {
    Task {
      do { try await wearables.startRegistration() } catch { lastError = "\(error)" }
    }
  }

  /// Starts a device session; streaming begins once the session reports `.started`.
  func start() {
    guard session == nil else { return }
    do {
      let s = try wearables.createSession(deviceSelector: selector)
      tokens.append(s.statePublisher.listen { [weak self] state in
        Task { @MainActor in self?.onSessionState(state) }
      })
      tokens.append(s.errorPublisher.listen { [weak self] error in
        Task { @MainActor in self?.lastError = error.localizedDescription }
      })
      session = s
      sessionState = .starting
      try s.start()
    } catch {
      lastError = error.localizedDescription
      session = nil
    }
  }

  func stop() {
    camera?.stop()     // cascades to the stream
    session?.stop()    // terminal; state observer cleans up
  }

  private func onSessionState(_ state: DeviceSessionState) {
    sessionState = state
    if state == .started { Task { await beginStream() } }
    if state == .stopped {
      tokens.removeAll()
      camera = nil
      session = nil
      streamState = .stopped
    }
  }

  private func beginStream() async {
    guard let session, camera == nil else { return }
    do {
      // Permission is granted in the Meta AI app (the request redirects there).
      if try await wearables.checkPermissionStatus(.camera) != .granted {
        guard try await wearables.requestPermission(.camera) == .granted else {
          lastError = "Camera permission denied in Meta AI app"; return
        }
      }
      // Values used by Meta's sample (known-valid for 1.0.1). We do NOT request higher rates:
      // the uplink downsamples to the server's needs, keeping glasses streaming load modest.
      let config = StreamConfiguration(videoCodec: VideoCodec.hvc1,
                                       resolution: StreamingResolution.low,
                                       frameRate: 24)
      guard let cam = try session.addCamera(config: config) else {
        lastError = "Couldn't create the camera"; return
      }
      camera = cam
      tokens.append(cam.stream.statePublisher.listen { [weak self] state in
        Task { @MainActor in self?.streamState = state }
      })
      tokens.append(cam.stream.videoFramePublisher.listen { [weak self] frame in
        self?.onFrame(frame.sampleBuffer)
      })
      tokens.append(cam.stream.errorPublisher.listen { [weak self] error in
        Task { @MainActor in self?.lastError = error.localizedDescription }
      })
      streamState = .starting
      cam.stream.start()
    } catch {
      lastError = error.localizedDescription
    }
  }

  /// Called on the SDK's delivery queue. Cheap early-out first: if the uplink is busy or
  /// it isn't time for the next frame, we skip decoding entirely (saves phone CPU/heat).
  nonisolated private func onFrame(_ sample: CMSampleBuffer) {
    guard uplink.wantsFrame() else { return }
    guard let jpeg = decoder.decodeToJPEG(sample, maxWidth: 640, quality: 0.6) else { return }
    uplink.send(jpeg: jpeg, origin: uplink.originLabel)
    Task { @MainActor in self.framesReceived += 1 }
  }
}
