// Local Bambu Studio observer. No printer protocol, credentials, or chat dependency.
// Control operations are explicit; the default probe is read-only and never prompts for permissions.
import AppKit
import ApplicationServices
import CoreGraphics
import Vision
import CryptoKit
import Darwin

struct BridgeError: Error { let message: String }
func fail(_ s: String) throws -> Never { throw BridgeError(message:s) }
func attr(_ e: AXUIElement, _ name: String) -> CFTypeRef? {
    var result: CFTypeRef?; AXUIElementCopyAttributeValue(e,name as CFString,&result); return result
}
var responseURL: URL? = nil
var ipcRequestID: String? = nil
func emit(_ d:[String:Any]) {
    var result=d
    if let id=ipcRequestID { result["request_id"]=id }
    let data=try! JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
    if let target=responseURL {
        do {try data.write(to:target,options:.atomic);try FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:target.path)}
        catch {fputs("IPC response write failed\n",stderr)}
    } else {print(String(data:data,encoding:.utf8)!)}
}
func ipcArguments(_ original:[String]) throws -> [String] {
    guard original.first=="--ipc" else {return original}
    guard original.count==3 else {try fail("Invalid IPC invocation")}
    let input=URL(fileURLWithPath:original[1]);let output=URL(fileURLWithPath:original[2])
    let parent=input.deletingLastPathComponent()
    guard input.path.hasPrefix("/"),input.lastPathComponent=="request.json",output.lastPathComponent=="response.json",output.deletingLastPathComponent()==parent,
          !FileManager.default.fileExists(atPath:output.path),input.resolvingSymlinksInPath()==input,parent.resolvingSymlinksInPath()==parent else {try fail("Invalid IPC paths")}
    for path in [parent.path,input.path] {
        let attrs=try FileManager.default.attributesOfItem(atPath:path)
        guard (attrs[.ownerAccountID] as? NSNumber)?.uint32Value==getuid(),let mode=attrs[.posixPermissions] as? NSNumber,mode.intValue & 0o077==0 else {try fail("IPC ownership or permissions mismatch")}
    }
    let request=try JSONSerialization.jsonObject(with:Data(contentsOf:input)) as? [String:Any] ?? [:]
    guard let id=request["request_id"] as? String,UUID(uuidString:id) != nil,let created=request["created_at"] as? Double,abs(Date().timeIntervalSince1970-created)<120,
          let args=request["args"] as? [String],!args.isEmpty else {try fail("Invalid or stale IPC request")}
    responseURL=output;ipcRequestID=id
    return args
}
func windows(_ pid: pid_t) -> [[String:Any]] {
    let ax = AXUIElementCreateApplication(pid)
    return (attr(ax,kAXWindowsAttribute) as? [AXUIElement] ?? []).map { w in
        ["title":(attr(w,kAXTitleAttribute) as? String ?? ""),
         "minimized":(attr(w,kAXMinimizedAttribute) as? Bool ?? false),
         "edited":(attr(w,"AXEdited") as? Bool ?? false)]
    }
}
func probe() -> [String:Any] {
    let session=CGSessionCopyCurrentDictionary() as? [String:Any] ?? [:]
    let apps=NSRunningApplication.runningApplications(withBundleIdentifier:"com.bambulab.bambu-studio")
    return ["ok":true,"session_on_console":session["kCGSSessionOnConsoleKey"] as? Bool ?? false,"screen_locked":session["CGSSessionScreenIsLocked"] as? Bool ?? false,"accessibility":AXIsProcessTrusted(),"screen_capture":CGPreflightScreenCaptureAccess(),
            "helper_bundle_id":Bundle.main.bundleIdentifier ?? "unbundled","helper_app_path":Bundle.main.bundlePath,
            "studio_version":Bundle(path:"/Applications/BambuStudio.app")?.infoDictionary?["CFBundleShortVersionString"] as? String ?? "",
            "instances":apps.map { ["pid":Int($0.processIdentifier),"active":$0.isActive,"windows":windows($0.processIdentifier)] }]
}
func target(_ pid:pid_t) throws -> NSRunningApplication {
    guard AXIsProcessTrusted(),CGPreflightScreenCaptureAccess() else {try fail("Accessibility or screen capture permission missing for this process")}
    guard let app=NSRunningApplication(processIdentifier:pid),app.bundleIdentifier=="com.bambulab.bambu-studio" else {try fail("Target is not Bambu Studio")}
    return app
}
func snapshot(_ pid:pid_t,_ title:String,raise:Bool=false) throws -> [String:Any] {
    let app=try target(pid)
    let ax=AXUIElementCreateApplication(pid)
    let matches=(attr(ax,kAXWindowsAttribute) as? [AXUIElement] ?? []).filter {(attr($0,kAXTitleAttribute) as? String)==title}
    guard matches.count==1 else {try fail("Exact accessible window is absent or ambiguous")}
    if raise { app.activate(options:[.activateAllWindows]); AXUIElementSetAttributeValue(matches[0],kAXMinimizedAttribute as CFString,kCFBooleanFalse); AXUIElementPerformAction(matches[0],kAXRaiseAction as CFString); Thread.sleep(forTimeInterval:1.0) }
    let infos=CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] ?? []
    let candidates=infos.filter {($0[kCGWindowOwnerPID as String] as? Int)==Int(pid) && ($0[kCGWindowName as String] as? String)==title && [0,8].contains($0[kCGWindowLayer as String] as? Int ?? -1)}
    guard candidates.count==1,let info=candidates.first,let wid=info[kCGWindowNumber as String] as? Int,let bounds=info[kCGWindowBounds as String] as? [String:Double] else {try fail("Exact visible window is absent or ambiguous")}
    let path=FileManager.default.temporaryDirectory.appendingPathComponent("printlab-studio-\(UUID().uuidString).png")
    defer {try? FileManager.default.removeItem(at:path)}
    let task=Process();task.executableURL=URL(fileURLWithPath:"/usr/sbin/screencapture");task.arguments=["-x","-R",["X","Y","Width","Height"].map{String(Int(bounds[$0] ?? 0))}.joined(separator:","),path.path];task.standardError=FileHandle.nullDevice;try task.run();task.waitUntilExit()
    guard task.terminationStatus==0,let data=try? Data(contentsOf:path),let image=NSImage(data:data),let cg=image.cgImage(forProposedRect:nil,context:nil,hints:nil) else {try fail("Window capture failed")}
    let req=VNRecognizeTextRequest();req.recognitionLevel = .accurate;req.recognitionLanguages=["zh-Hans","en-US"];req.usesLanguageCorrection=false
    try VNImageRequestHandler(cgImage:cg).perform([req])
    let tokens=(req.results ?? []).compactMap { observation -> [String:Any]? in
        guard let best=observation.topCandidates(1).first else{return nil};let b=observation.boundingBox
        var greenCount=0; var greenX=0.0
        if let crop=cg.cropping(to:CGRect(x:b.minX*Double(cg.width),y:(1-b.maxY)*Double(cg.height),width:b.width*Double(cg.width),height:b.height*Double(cg.height))) {
            let bitmap=NSBitmapImageRep(cgImage:crop)
            for y in 0..<bitmap.pixelsHigh { for x in 0..<bitmap.pixelsWide {
                if let c=bitmap.colorAt(x:x,y:y)?.usingColorSpace(.deviceRGB),c.greenComponent>0.35,c.greenComponent>c.redComponent+0.12,c.greenComponent>c.blueComponent+0.08 {greenCount += 1;greenX += Double(x)/Double(bitmap.pixelsWide)}
            }}
        }
        return ["text":best.string,"confidence":Double(best.confidence),"x":Double(b.minX),"y":Double(1-b.maxY),"width":Double(b.width),"height":Double(b.height),"green_pixels":greenCount,"green_center_x":greenCount>0 ? greenX/Double(greenCount) : -1]
    }
    return ["ok":true,"pid":Int(pid),"window_id":wid,"title":title,"bounds":bounds,"width":cg.width,"height":cg.height,
            "sha256":SHA256.hash(data:cg.dataProvider!.data! as Data).map{String(format:"%02x",$0)}.joined(),"observed_at":Date().timeIntervalSince1970,"tokens":tokens,"active":app.isActive]
}
func clickToken(_ shot:[String:Any],_ text:String) throws {
    guard let pid=shot["pid"] as? Int,let bounds=shot["bounds"] as? [String:Double],let tokens=shot["tokens"] as? [[String:Any]],let observed=shot["observed_at"] as? Double,Date().timeIntervalSince1970-observed<2 else {try fail("Stale observation")}
    let hits=tokens.filter{($0["text"] as? String)==text && ($0["confidence"] as? Double ?? 0)>=0.5}
    guard hits.count==1,let b=hits.first,let x=b["x"] as? Double,let y=b["y"] as? Double,let w=b["width"] as? Double,let h=b["height"] as? Double else {try fail("Unique exact button text not recognized: " + String(describing: tokens.filter{ ($0["text"] as? String ?? "").contains("打印") }))}
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier==pid_t(pid) else {try fail("Studio lost foreground")}
    let p=CGPoint(x:(bounds["X"] ?? 0)+(x+w/2)*(bounds["Width"] ?? 0),y:(bounds["Y"] ?? 0)+(y+h/2)*(bounds["Height"] ?? 0))
    guard let down=CGEvent(mouseEventSource:nil,mouseType:.leftMouseDown,mouseCursorPosition:p,mouseButton:.left),let up=CGEvent(mouseEventSource:nil,mouseType:.leftMouseUp,mouseCursorPosition:p,mouseButton:.left) else {try fail("Cannot construct mouse event")}
    down.post(tap:.cghidEventTap);up.post(tap:.cghidEventTap)
}
do {
    let args=try ipcArguments(Array(CommandLine.arguments.dropFirst()));let mode=args.first ?? "probe"
    switch mode {
    case "probe": emit(probe())
    case "request-permissions":
        // This mode is only called by an explicit user setup action. Probe never
        // calls either prompting API and never opens System Settings.
        let application=NSApplication.shared;application.setActivationPolicy(.accessory);application.activate(ignoringOtherApps:true)
        let options=[kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String:true] as CFDictionary
        let accessibility=AXIsProcessTrustedWithOptions(options)
        let screen=CGPreflightScreenCaptureAccess() ? true : CGRequestScreenCaptureAccess()
        emit(["ok":true,"requested":true,"printed":false,"accessibility":accessibility,"screen_capture":screen,"helper_bundle_id":Bundle.main.bundleIdentifier ?? "unbundled"])
    case "snapshot", "inspect-panel", "open-panel":
        guard args.count==3,let pid=Int32(args[1]) else {try fail("Expected mode pid exact-window-title")}
        let shot=try snapshot(pid,args[2],raise:mode != "snapshot")
        if mode=="open-panel" { guard args[2].hasSuffix(".gcode"),!args[2].contains("*") else {try fail("Only exact sliced job preview may open send panel")};try clickToken(shot,"打印单盘");emit(["ok":true,"opened_panel":true,"sent":false]) }
        else {emit(shot)}
    case "prepare-options":
        guard args.count==2,let pid=Int32(args[1]) else {try fail("Expected pid")}
        let shot=try snapshot(pid,"发送打印任务",raise:true)
        let tokens=shot["tokens"] as? [[String:Any]] ?? []
        let labels=tokens.filter{($0["text"] as? String ?? "").hasPrefix("延时摄影")}
        guard labels.count==1,let y=labels[0]["y"] as? Double else {try fail("Timelapse row not recognized")}
        let close=tokens.filter{($0["text"] as? String)=="关闭" && abs(($0["y"] as? Double ?? 9)-y)<0.025 && ($0["x"] as? Double ?? 9)<0.5}
        guard close.count==1 else {try fail("Unique timelapse off option absent")}
        var subset=shot;subset["tokens"]=close;try clickToken(subset,"关闭")
        Thread.sleep(forTimeInterval:0.5);emit(try snapshot(pid,"发送打印任务"))
    case "send-once":
        // The helper cannot create approval or reservation. It consumes an exact existing
        // PrintLab reservation, and a crash after claiming is deliberately non-retryable.
        guard args.count==2 else {try fail("Expected bound request file")}
        let request=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:args[1]))) as? [String:Any] ?? [:]
        guard let pid=request["pid"] as? Int,let jid=request["job_id"] as? String,
              let receiptPath=request["receipt_path"] as? String,let artifactPath=request["artifact_path"] as? String,
              let artifactHash=request["artifact_sha256"] as? String,let fingerprint=request["fingerprint"] as? String,
              let expectedShot=request["snapshot_sha256"] as? String else {try fail("Incomplete bound request")}
        guard Bundle(path:"/Applications/BambuStudio.app")?.infoDictionary?["CFBundleShortVersionString"] as? String=="02.08.02.61" else {try fail("Unverified Studio version")}
        let configURL=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/BambuStudio/BambuStudio.conf")
        let config=try JSONSerialization.jsonObject(with:Data(contentsOf:configURL)) as? [String:Any] ?? [:]
        let selected=(config["app"] as? [String:Any])?["user_last_selected_machine"] as? String ?? ""
        let selectedHash=SHA256.hash(data:Data(selected.utf8)).map{String(format:"%02x",$0)}.joined()
        guard !selected.isEmpty,request["selected_serial_sha256"] as? String==selectedHash else {try fail("Studio selected printer serial changed")}
        let receiptURL=URL(fileURLWithPath:receiptPath);let dir=receiptURL.deletingLastPathComponent()
        guard receiptURL.lastPathComponent=="dispatch.json",dir.lastPathComponent==jid,
              URL(fileURLWithPath:artifactPath).deletingLastPathComponent()==dir else {try fail("Reservation path mismatch")}
        let receipt=try JSONSerialization.jsonObject(with:Data(contentsOf:receiptURL)) as? [String:Any] ?? [:]
        let approval=try JSONSerialization.jsonObject(with:Data(contentsOf:dir.appendingPathComponent("approval.json"))) as? [String:Any] ?? [:]
        let formatter=ISO8601DateFormatter();formatter.formatOptions=[.withInternetDateTime,.withFractionalSeconds]
        guard receipt["state"] as? String=="awaiting_ui_send",receipt["job_id"] as? String==jid,
              receipt["transport"] as? String=="bambu_studio",receipt["command_sent"] as? Bool==false,
              receipt["fingerprint"] as? String==fingerprint,approval["fingerprint"] as? String==fingerprint,
              receipt["artifact_sha256"] as? String==artifactHash,
              let deadline=formatter.date(from:receipt["send_deadline"] as? String ?? ""),deadline>Date(),deadline.timeIntervalSinceNow<=60 else {try fail("Reservation missing, stale, or does not match approval")}
        let actualHash=SHA256.hash(data:try Data(contentsOf:URL(fileURLWithPath:artifactPath))).map{String(format:"%02x",$0)}.joined()
        guard actualHash==artifactHash else {try fail("Artifact changed")}
        let shot=try snapshot(pid_t(pid),"发送打印任务",raise:true)
        guard shot["sha256"] as? String==expectedShot else {try fail("Send dialog changed since validated snapshot")}
        let tokens=shot["tokens"] as? [[String:Any]] ?? []
        guard tokens.contains(where:{($0["text"] as? String ?? "").hasPrefix(jid+".gcode")}) else {try fail("Wrong job displayed")}
        let claim=dir.appendingPathComponent("studio-send-claimed.json").path
        let fd=open(claim,O_WRONLY|O_CREAT|O_EXCL,S_IRUSR|S_IWUSR)
        guard fd>=0 else {try fail("Send already claimed; reconcile and never retry")}
        let evidence=try JSONSerialization.data(withJSONObject:["job_id":jid,"claimed_at":Date().timeIntervalSince1970,"snapshot_sha256":expectedShot])
        _=evidence.withUnsafeBytes{write(fd,$0.baseAddress,evidence.count)};fsync(fd);close(fd)
        try clickToken(shot,"发送")
        emit(["ok":true,"executed":true,"command_sent":true,"clicked_send_once":true,"job_id":jid])
    default:try fail("Unsupported command")
    }
} catch {emit(["ok":false,"error":(error as? BridgeError)?.message ?? String(describing:error)]);exit(1)}
