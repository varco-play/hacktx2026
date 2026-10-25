// Mode B: Meta Mock Device Kit. Pairs simulated Ray-Ban Meta glasses so the full DAT
// lifecycle (registration, session, camera stream, stop, disconnect) runs without hardware.
// Calls mirror Meta's CameraAccess sample (MockDeviceKitViewModel / MockDeviceCardViewModel).
// STATUS: not yet compiled (no Xcode on the dev Mac).
#if DEBUG
import Foundation
import MWDATMockDevice

@MainActor
final class MockGlassesController {
  static let shared = MockGlassesController()
  private(set) var glasses: MockGlasses?

  /// Enable the kit, pair one Ray-Ban Meta, power on, unfold, put on, and feed the mock
  /// camera from a bundled clip (add `consentlens_test.mp4` to the app bundle) or the phone camera.
  func pairAndWear() {
    let kit = MockDeviceKit.shared
    if !kit.isEnabled { kit.enable() }
    if glasses == nil {
      do { glasses = try kit.pairGlasses(model: .rayBanMeta) } catch {
        NSLog("[ConsentLens] mock pair failed: \(error)"); return
      }
    }
    guard let g = glasses else { return }
    g.powerOn()
    g.unfold()
    g.don()
    if let clip = Bundle.main.url(forResource: "consentlens_test", withExtension: "mp4") {
      g.services.camera.setCameraFeed(fileURL: clip)
    }
  }

  /// Simulate the wearer taking the glasses off / folding them (lifecycle + disconnect tests).
  func takeOff() { glasses?.doff(); glasses?.fold() }
  func powerOff() { glasses?.powerOff() }

  func unpair() {
    if let g = glasses { MockDeviceKit.shared.unpairDevice(g) }
    glasses = nil
  }
}
#endif
