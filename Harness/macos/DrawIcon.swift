import AppKit

let output = CommandLine.arguments[1]
let canvas = NSSize(width: 1024, height: 1024)
let image = NSImage(size: canvas)
image.lockFocus()
NSColor.clear.setFill()
NSRect(origin: .zero, size: canvas).fill()
let tile = NSBezierPath(roundedRect: NSRect(x: 72, y: 72, width: 880, height: 880), xRadius: 196, yRadius: 196)
NSGraphicsContext.saveGraphicsState()
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.18)
shadow.shadowBlurRadius = 26
shadow.shadowOffset = NSSize(width: 0, height: -10)
shadow.set()
NSColor(calibratedRed: 0.19, green: 0.32, blue: 0.23, alpha: 1).setFill()
tile.fill()
NSGraphicsContext.restoreGraphicsState()
NSGradient(starting: NSColor(calibratedRed: 0.29, green: 0.43, blue: 0.31, alpha: 1), ending: NSColor(calibratedRed: 0.15, green: 0.26, blue: 0.19, alpha: 1))!.draw(in: tile, angle: -80)
NSColor.white.withAlphaComponent(0.13).setStroke()
tile.lineWidth = 2
tile.stroke()
func polygon(_ points: [(CGFloat, CGFloat)], color: NSColor) {
    let path = NSBezierPath()
    path.move(to: NSPoint(x: points[0].0, y: points[0].1))
    for p in points.dropFirst() { path.line(to: NSPoint(x: p.0, y: p.1)) }
    path.close()
    color.setFill(); path.fill()
}
// The workspace's cube mark, drawn as three solid faces for small-size legibility.
NSGraphicsContext.saveGraphicsState()
let cubeShadow = NSShadow()
cubeShadow.shadowColor = NSColor.black.withAlphaComponent(0.18)
cubeShadow.shadowBlurRadius = 24
cubeShadow.shadowOffset = NSSize(width: 0, height: -18)
cubeShadow.set()
polygon([(512, 776),(768, 632),(512, 484),(256, 632)], color: NSColor(calibratedRed: 0.94, green: 0.95, blue: 0.86, alpha: 1))
polygon([(256,632),(512,484),(512,192),(256,340)], color: NSColor(calibratedRed: 0.78, green: 0.84, blue: 0.69, alpha: 1))
polygon([(512,484),(768,632),(768,340),(512,192)], color: NSColor(calibratedRed: 0.61, green: 0.72, blue: 0.53, alpha: 1))
NSGraphicsContext.restoreGraphicsState()
// A quiet inset top edge and two print layers distinguish it from a shipping box.
let top = NSBezierPath()
top.move(to: NSPoint(x: 328, y: 632));top.line(to: NSPoint(x: 512, y: 736));top.line(to: NSPoint(x: 696, y: 632));top.line(to: NSPoint(x: 512, y: 526));top.close()
NSColor(calibratedRed: 0.36, green: 0.48, blue: 0.32, alpha: 0.34).setStroke()
top.lineWidth=10;top.lineJoinStyle = .round;top.stroke()
for y: CGFloat in [392, 448] {
    let left = NSBezierPath()
    left.move(to: NSPoint(x: 292, y: y));left.line(to: NSPoint(x: 476, y: y-106))
    left.lineWidth = 10;left.lineCapStyle = .round
    NSColor(calibratedRed: 0.30, green: 0.44, blue: 0.30, alpha: 0.34).setStroke();left.stroke()
    let right = NSBezierPath()
    right.move(to: NSPoint(x: 548, y: y-106));right.line(to: NSPoint(x: 732, y: y))
    right.lineWidth=10;right.lineCapStyle = .round
    NSColor(calibratedRed: 0.23, green: 0.38, blue: 0.25, alpha: 0.40).setStroke();right.stroke()
}
image.unlockFocus()
guard let tiff=image.tiffRepresentation, let bitmap=NSBitmapImageRep(data:tiff), let png=bitmap.representation(using:.png,properties:[:]) else { fatalError("Cannot render icon") }
try png.write(to:URL(fileURLWithPath:output))
