// ConsentLens companion app: Meta glasses (or Mock Device Kit) -> DAT -> ConsentLens server.
// STATUS: not yet compiled (no Xcode on the dev Mac). Mirrors Meta's CameraAccess sample.

import MWDATCore
import SwiftUI
#if DEBUG
import MWDATMockDevice
#endif

@main
struct ConsentLensCompanionApp: App {
  @State private var glasses: GlassesSession?
  @State private var server = "ws://192.168.1.20:8000"
  @State private var token = ""
  @State private var useMock = true
  @State private var configured = false

  init() {
    do { try Wearables.configure() } catch { NSLog("[ConsentLens] Wearables.configure failed: \(error)") }
  }

  var body: some Scene {
    WindowGroup {
      NavigationStack {
        Form {
          Section("ConsentLens server") {
            TextField("ws://<mac-ip>:8000", text: $server).textInputAutocapitalization(.never)
            SecureField("INGEST_TOKEN", text: $token)
          }
          #if DEBUG
          Section("Device") {
            Toggle("Use Meta Mock Device (no glasses)", isOn: $useMock)
          }
          #endif
          Section {
            Button(configured ? "Reconnect uplink" : "Connect") { connect() }
            if let g = glasses {
              Button("Register with Meta AI app") { g.register() }
              Button("Start glasses camera") { g.start() }
              Button("Stop", role: .destructive) { g.stop() }
            }
          }
          if let g = glasses {
            Section("Status (from the SDK)") {
              LabeledContent("Registration", value: "\(g.registrationState)")
              LabeledContent("Devices", value: "\(g.devices.count)")
              LabeledContent("Session", value: "\(g.sessionState)")
              LabeledContent("Stream", value: "\(g.streamState)")
              LabeledContent("Frames forwarded", value: "\(g.framesReceived)")
              LabeledContent("Uplink sent / skipped", value: "\(g.uplink.sent) / \(g.uplink.dropped)")
              if let e = g.lastError { Text(e).foregroundStyle(.red) }
            }
          }
        }
        .navigationTitle("ConsentLens")
      }
      .onOpenURL { url in
        // Registration callback from the Meta AI app (AppLinkURLScheme in Info.plist).
        Task { _ = try? await Wearables.shared.handleUrl(url) }
      }
    }
  }

  private func connect() {
    #if DEBUG
    if useMock { MockGlassesController.shared.pairAndWear() }
    #endif
    let uplink = FrameUplink(server: server, token: token, origin: useMock ? "meta_mock_device" : "meta_glasses")
    uplink.connect()
    glasses = GlassesSession(wearables: Wearables.shared, uplink: uplink)
    configured = true
  }
}
