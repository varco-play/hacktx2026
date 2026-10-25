// Sends frames to the ConsentLens server's /api/ingest WebSocket.
// Wire format (must match backend/app/main.py `ingest`): one binary message per frame =
//   4-byte big-endian header length + UTF-8 JSON header + JPEG bytes.
// Back-pressure: at most ONE frame in flight; a frame arriving while the previous one is
// unacknowledged is dropped (never queued), so a slow network never adds latency.
// STATUS: not yet compiled (no Xcode on the dev Mac). Wire format is covered by a Python test.

import Foundation
import UIKit

final class FrameUplink: @unchecked Sendable {
  let originLabel: String               // "meta_glasses" or "meta_mock_device" (reported, not verified)
  private let url: URL
  private let maxFPS: Double
  private let lock = NSLock()
  private var task: URLSessionWebSocketTask?
  private var inFlight = false
  private var lastSent = Date.distantPast
  private var seq = 0
  private(set) var sent = 0
  private(set) var dropped = 0

  /// server: e.g. "ws://192.168.1.20:8000"; token = INGEST_TOKEN from the server's .env
  init(server: String, token: String, origin: String, maxFPS: Double = 12) {
    var c = URLComponents(string: server + "/api/ingest")!
    c.queryItems = [URLQueryItem(name: "token", value: token)]
    self.url = c.url!
    self.originLabel = origin
    self.maxFPS = maxFPS
    UIDevice.current.isBatteryMonitoringEnabled = true
  }

  func connect() {
    lock.lock(); defer { lock.unlock() }
    task?.cancel(with: .goingAway, reason: nil)
    task = URLSession.shared.webSocketTask(with: url)
    task?.resume()
    inFlight = false
    receiveAcks()
  }

  func disconnect() {
    lock.lock(); defer { lock.unlock() }
    task?.cancel(with: .normalClosure, reason: nil)
    task = nil
  }

  /// Cheap check before decoding: rate limit + one-in-flight.
  func wantsFrame() -> Bool {
    lock.lock(); defer { lock.unlock() }
    guard task != nil else { return false }
    if inFlight || Date().timeIntervalSince(lastSent) < 1.0 / maxFPS {
      dropped += 1
      return false
    }
    return true
  }

  func send(jpeg: Data, origin: String) {
    lock.lock()
    guard let task else { lock.unlock(); return }
    seq += 1
    inFlight = true
    lastSent = Date()
    let header: [String: Any] = [
      "seq": seq,
      "origin": origin,
      "t_phone_ms": Int(ProcessInfo.processInfo.systemUptime * 1000),
      // PHONE metrics (real). Glasses thermal/battery are not exposed in the 1.0.1 sample APIs.
      "thermal_state": Self.thermalName(ProcessInfo.processInfo.thermalState),
      "battery_level": UIDevice.current.batteryLevel >= 0 ? Double(UIDevice.current.batteryLevel) : "unavailable",
    ]
    lock.unlock()
    guard let json = try? JSONSerialization.data(withJSONObject: header) else { return }
    var msg = Data()
    var n = UInt32(json.count).bigEndian
    msg.append(Data(bytes: &n, count: 4))
    msg.append(json)
    msg.append(jpeg)
    task.send(.data(msg)) { [weak self] error in
      if error != nil { self?.markIdle() }
    }
  }

  private func receiveAcks() {
    task?.receive { [weak self] result in
      guard let self else { return }
      switch result {
      case .success:
        self.markIdle()          // server acknowledged the last frame
        self.receiveAcks()
      case .failure:
        self.markIdle()
      }
    }
  }

  private func markIdle() {
    lock.lock(); inFlight = false; sent += 1; lock.unlock()
  }

  private static func thermalName(_ s: ProcessInfo.ThermalState) -> String {
    switch s {
    case .nominal: return "nominal"
    case .fair: return "fair"
    case .serious: return "serious"
    case .critical: return "critical"
    @unknown default: return "unknown"
    }
  }
}
