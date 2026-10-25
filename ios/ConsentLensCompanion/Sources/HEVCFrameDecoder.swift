// Decodes DAT HEVC (hvc1) sample buffers and re-encodes a downscaled JPEG for the uplink.
// Hardware decode via VideoToolbox; scaling/JPEG via Core Image (GPU). One decode per
// forwarded frame only — skipped frames are never decoded (see GlassesSession.onFrame).
// STATUS: not yet compiled (no Xcode on the dev Mac).

import CoreImage
import CoreMedia
import Foundation
import VideoToolbox

final class HEVCFrameDecoder: @unchecked Sendable {
  private let lock = NSLock()
  private var session: VTDecompressionSession?
  private var format: CMFormatDescription?
  private let ciContext = CIContext(options: [.useSoftwareRenderer: false])

  func decodeToJPEG(_ sample: CMSampleBuffer, maxWidth: CGFloat, quality: CGFloat) -> Data? {
    lock.lock(); defer { lock.unlock() }
    guard let fmt = CMSampleBufferGetFormatDescription(sample) else { return nil }
    if session == nil || format.map({ !CMFormatDescriptionEqual($0, otherFormatDescription: fmt) }) ?? true {
      if let s = session { VTDecompressionSessionInvalidate(s) }
      session = nil
      let attrs: [CFString: Any] = [kCVPixelBufferPixelFormatTypeKey: kCVPixelFormatType_32BGRA]
      var s: VTDecompressionSession?
      guard VTDecompressionSessionCreate(allocator: nil, formatDescription: fmt, decoderSpecification: nil,
                                         imageBufferAttributes: attrs as CFDictionary,
                                         outputCallback: nil, decompressionSessionOut: &s) == noErr,
            let created = s else { return nil }
      session = created
      format = fmt
    }
    guard let session else { return nil }

    var output: CVPixelBuffer?
    let status = VTDecompressionSessionDecodeFrame(session, sampleBuffer: sample, flags: [],
                                                   infoFlagsOut: nil) { status, _, imageBuffer, _, _ in
      if status == noErr { output = imageBuffer }
    }
    // Waits for this frame only (synchronous decode keeps ordering simple at uplink rates).
    VTDecompressionSessionWaitForAsynchronousFrames(session)
    guard status == noErr, let pixels = output else { return nil }

    var image = CIImage(cvPixelBuffer: pixels)
    let scale = min(1.0, maxWidth / image.extent.width)
    if scale < 1.0 { image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale)) }
    return ciContext.jpegRepresentation(of: image, colorSpace: CGColorSpaceCreateDeviceRGB(),
                                        options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: quality])
  }

  deinit {
    if let s = session { VTDecompressionSessionInvalidate(s) }
  }
}
