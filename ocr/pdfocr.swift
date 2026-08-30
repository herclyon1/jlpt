import Foundation
import Vision
import CoreGraphics
import ImageIO

// 用法: pdfocr <pdf路径> [起始页] [结束页]   —— 页码从1开始, 省略则全部
let args = CommandLine.arguments
guard args.count >= 2, let doc = CGPDFDocument(URL(fileURLWithPath: args[1]) as CFURL) else {
    FileHandle.standardError.write("用法: pdfocr <file.pdf> [from] [to]\n".data(using:.utf8)!); exit(1)
}
let total = doc.numberOfPages
let from = args.count > 2 ? max(1, Int(args[2]) ?? 1) : 1
let to   = args.count > 3 ? min(total, Int(args[3]) ?? total) : total
let scale: CGFloat = 3.0

for p in from...to {
    guard let page = doc.page(at: p) else { continue }
    let box = page.getBoxRect(.mediaBox)
    let w = Int(box.width * scale), h = Int(box.height * scale)
    guard w > 0, h > 0,
          let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { continue }
    ctx.setFillColor(CGColor(red:1,green:1,blue:1,alpha:1))
    ctx.fill(CGRect(x:0,y:0,width:w,height:h))
    ctx.scaleBy(x: scale, y: scale)
    ctx.translateBy(x: -box.origin.x, y: -box.origin.y)
    ctx.drawPDFPage(page)
    guard let img = ctx.makeImage() else { continue }

    let req = VNRecognizeTextRequest()
    req.recognitionLanguages = ["ja-JP", "zh-Hans", "en-US"]
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: img, options: [:])
    do { try handler.perform([req]) } catch { continue }
    guard let obs = req.results else { continue }

    // 按版面顺序: 先按纵向分行(y降序), 同行内按x升序
    let lines = obs.compactMap { o -> (CGFloat, CGFloat, String)? in
        guard let t = o.topCandidates(1).first?.string else { return nil }
        return (o.boundingBox.midY, o.boundingBox.minX, t)
    }.sorted { a, b in abs(a.0 - b.0) > 0.008 ? a.0 > b.0 : a.1 < b.1 }

    print("=== PAGE \(p)")
    for l in lines { print(l.2) }
}
