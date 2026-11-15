// Local Bambu Studio observer. No printer protocol, credentials, or chat dependency.
// Control operations are explicit; the default probe is read-only and never prompts for permissions.
import AppKit
import ApplicationServices
import CoreGraphics
import Vision
import CryptoKit
import Darwin

struct BridgeError: Error {
    let message: String
    let code: String
    let stage: String
}
func fail(_ s: String, code: String = "validation_failed", stage: String = "validation") throws -> Never {
    throw BridgeError(message:s, code:code, stage:stage)
}
func attr(_ e: AXUIElement, _ name: String) -> CFTypeRef? {
    var result: CFTypeRef?; AXUIElementCopyAttributeValue(e,name as CFString,&result); return result
}
func accessibleWindows(_ pid: pid_t) throws -> [AXUIElement] {
    let ax = AXUIElementCreateApplication(pid)
    AXUIElementSetMessagingTimeout(ax, 2)
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(ax, kAXWindowsAttribute as CFString, &value)
    guard result == .success, let list = value as? [AXUIElement] else {
        try fail("Cannot read Studio windows (AX error \(result.rawValue))",
                 code:"ax_windows_unavailable", stage:"window_discovery")
    }
    return list
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
    guard original[1].hasPrefix("/"),original[2].hasPrefix("/"),input.lastPathComponent=="request.json",output.lastPathComponent=="response.json",output.deletingLastPathComponent()==parent else {try fail("Invalid IPC paths")}
    // Foundation rewrites the legitimate /private/tmp and /private/var aliases
    // to /tmp and /var. URL equality therefore rejects Python's resolved
    // tempfile paths even when neither the file nor its private parent is a
    // symlink. Inspect the actual directory entries instead.
    var outputStat = stat()
    guard lstat(output.path, &outputStat) != 0, errno == ENOENT else {try fail("IPC response already exists or is inaccessible")}
    for path in [parent.path,input.path] {
        var metadata = stat()
        let kind = path == parent.path ? S_IFDIR : S_IFREG
        guard lstat(path, &metadata) == 0, metadata.st_mode & S_IFMT == kind,
              metadata.st_uid == getuid(), metadata.st_mode & 0o077 == 0 else {try fail("IPC ownership, type, or permissions mismatch")}
    }
    let request=try JSONSerialization.jsonObject(with:Data(contentsOf:input)) as? [String:Any] ?? [:]
    guard let id=request["request_id"] as? String,UUID(uuidString:id) != nil,let created=request["created_at"] as? Double,abs(Date().timeIntervalSince1970-created)<120,
          let args=request["args"] as? [String],!args.isEmpty else {try fail("Invalid or stale IPC request")}
    responseURL=output;ipcRequestID=id
    return args
}
func windows(_ pid: pid_t) -> [[String:Any]] {
    return ((try? accessibleWindows(pid)) ?? []).map { w in
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
    guard AXIsProcessTrusted() else {try fail("Accessibility permission missing for this process", code:"accessibility_denied", stage:"permissions")}
    guard CGPreflightScreenCaptureAccess() else {try fail("Screen capture permission missing for this process", code:"screen_capture_denied", stage:"permissions")}
    let session = CGSessionCopyCurrentDictionary() as? [String:Any] ?? [:]
    guard session["kCGSSessionOnConsoleKey"] as? Bool == true,
          session["CGSSessionScreenIsLocked"] as? Bool != true else {
        try fail("Desktop session is locked or unavailable", code:"desktop_unavailable", stage:"session")
    }
    guard let app=NSRunningApplication(processIdentifier:pid),app.bundleIdentifier=="com.bambulab.bambu-studio" else {try fail("Target is not Bambu Studio", code:"target_missing", stage:"window_discovery")}
    return app
}
func visibleWindows(_ pid: pid_t, _ title: String) -> [[String:Any]] {
    let infos = CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements], kCGNullWindowID) as? [[String:Any]] ?? []
    return infos.filter {
        ($0[kCGWindowOwnerPID as String] as? Int) == Int(pid) &&
        ($0[kCGWindowName as String] as? String) == title &&
        [0,8].contains($0[kCGWindowLayer as String] as? Int ?? -1)
    }
}
func snapshot(_ pid:pid_t,_ title:String,raise:Bool=false) throws -> [String:Any] {
    let app=try target(pid)
    let matches=try accessibleWindows(pid).filter {(attr($0,kAXTitleAttribute) as? String)==title}
    guard matches.count==1 else {try fail("Exact accessible window is absent or ambiguous", code:matches.isEmpty ? "ax_window_missing" : "ax_window_ambiguous", stage:"window_discovery")}
    if raise {
        app.activate(options:[.activateAllWindows])
        if attr(matches[0], kAXMinimizedAttribute) as? Bool == true {
            let restored = AXUIElementSetAttributeValue(matches[0], kAXMinimizedAttribute as CFString, kCFBooleanFalse)
            guard restored == .success else {
                try fail("Cannot restore the exact minimized Studio window (AX error \(restored.rawValue))", code:"restore_failed", stage:"window_recovery")
            }
        }
        let raised = AXUIElementPerformAction(matches[0], kAXRaiseAction as CFString)
        guard raised == .success else {try fail("Cannot raise the exact Studio window (AX error \(raised.rawValue))", code:"raise_failed", stage:"window_recovery")}
    }
    // AXRaise returning is not proof that the compositor has a capturable window.
    // Recover once, then observe until the exact window and geometry settle.
    let deadline = Date(timeIntervalSinceNow:raise ? 3 : 0)
    var candidates = visibleWindows(pid, title)
    var stableIdentity: NSDictionary?
    var settled = !raise
    while raise {
        if candidates.count > 1 {break}
        let identity = candidates.first.map { ["id":$0[kCGWindowNumber as String] ?? -1,
                                              "bounds":$0[kCGWindowBounds as String] ?? [:]] as NSDictionary }
        if let identity=identity, let previous=stableIdentity,
           identity.isEqual(previous), NSWorkspace.shared.frontmostApplication?.processIdentifier == pid {settled=true;break}
        if Date() >= deadline {break}
        stableIdentity = identity
        RunLoop.current.run(until:Date(timeIntervalSinceNow:0.1))
        candidates = visibleWindows(pid, title)
    }
    if raise && NSWorkspace.shared.frontmostApplication?.processIdentifier != pid {
        try fail("Studio activation was not granted; no button clicked", code:"activation_failed", stage:"window_recovery")
    }
    guard candidates.count==1,let info=candidates.first,let wid=info[kCGWindowNumber as String] as? Int,let bounds=info[kCGWindowBounds as String] as? [String:Double],
          (bounds["Width"] ?? 0) > 0, (bounds["Height"] ?? 0) > 0 else {
        try fail("Exact visible window is absent or ambiguous", code:candidates.count > 1 ? "visible_window_ambiguous" : "visible_window_missing", stage:"window_capture")
    }
    guard settled else {try fail("Studio window geometry did not settle", code:"window_unstable", stage:"window_recovery")}
    let path=FileManager.default.temporaryDirectory.appendingPathComponent("printlab-studio-\(UUID().uuidString).png")
    defer {try? FileManager.default.removeItem(at:path)}
    // Capture the selected window, not a desktop rectangle that may contain
    // another app's notification. Input still verifies the real hit target.
    let task=Process();task.executableURL=URL(fileURLWithPath:"/usr/sbin/screencapture");task.arguments=["-x","-o","-a","-l",String(wid),path.path];task.standardError=FileHandle.nullDevice;try task.run();task.waitUntilExit()
    let capturedAt = Date().timeIntervalSince1970
    guard task.terminationStatus==0,let data=try? Data(contentsOf:path),let image=NSImage(data:data),let cg=image.cgImage(forProposedRect:nil,context:nil,hints:nil) else {try fail("Window capture failed", code:"capture_failed", stage:"window_capture")}
    let req=VNRecognizeTextRequest();req.recognitionLevel = .accurate;req.recognitionLanguages=["zh-Hans","en-US"];req.usesLanguageCorrection=false
    // Normalize low-density desktop captures for Vision; retain original pixels
    // for selection color, geometry and the final window fingerprint.
    var recognitionImage = cg
    if cg.width < 1400 {
        guard let context = CGContext(data:nil, width:cg.width * 2, height:cg.height * 2,
                                      bitsPerComponent:8, bytesPerRow:0,
                                      space:CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue) else {
            try fail("Cannot prepare text recognition image")
        }
        context.interpolationQuality = .high
        context.draw(cg, in:CGRect(x:0, y:0, width:cg.width * 2, height:cg.height * 2))
        guard let scaled = context.makeImage() else { try fail("Cannot scale text recognition image") }
        recognitionImage = scaled
    }
    try VNImageRequestHandler(cgImage:recognitionImage).perform([req])
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
    return ["ok":true,"pid":Int(pid),"window_id":wid,"title":title,"bounds":bounds,"width":cg.width,"height":cg.height,"window_recovery_requested":raise,
            "sha256":SHA256.hash(data:cg.dataProvider!.data! as Data).map{String(format:"%02x",$0)}.joined(),"observed_at":capturedAt,"tokens":tokens,
            "active":NSWorkspace.shared.frontmostApplication?.processIdentifier == pid]
}
func clickToken(_ shot:[String:Any],_ text:String) throws {
    guard let pid=shot["pid"] as? Int,let bounds=shot["bounds"] as? [String:Double],let tokens=shot["tokens"] as? [[String:Any]],let observed=shot["observed_at"] as? Double,Date().timeIntervalSince1970-observed<2 else {try fail("Stale observation")}
    let hits=tokens.filter{($0["text"] as? String)==text && ($0["confidence"] as? Double ?? 0)>=0.5}
    guard hits.count==1,let b=hits.first,let x=b["x"] as? Double,let y=b["y"] as? Double,let w=b["width"] as? Double,let h=b["height"] as? Double else {try fail("Unique exact button text not recognized: \(text)", code:"button_not_recognized", stage:"before_input")}
    RunLoop.current.run(until:Date(timeIntervalSinceNow:0.01))
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier==pid_t(pid) else {try fail("Studio lost foreground", code:"foreground_lost", stage:"before_input")}
    guard let title=shot["title"] as? String, let windowID=shot["window_id"] as? Int else {try fail("Missing observed window identity")}
    let current=visibleWindows(pid_t(pid), title)
    guard current.count==1, current[0][kCGWindowNumber as String] as? Int == windowID,
          let currentBounds=current[0][kCGWindowBounds as String] as? [String:Double], currentBounds == bounds else {
        try fail("Studio window changed after capture; no button clicked", code:"window_changed", stage:"before_input")
    }
    let p=CGPoint(x:(bounds["X"] ?? 0)+(x+w/2)*(bounds["Width"] ?? 0),y:(bounds["Y"] ?? 0)+(y+h/2)*(bounds["Height"] ?? 0))
    // A frontmost application may still have a menu, another dialog, or an OS
    // overlay covering the point. Verify the actual accessible hit target.
    var hit: AXUIElement?
    let hitResult=AXUIElementCopyElementAtPosition(AXUIElementCreateSystemWide(), Float(p.x), Float(p.y), &hit)
    var hitPID: pid_t = 0
    guard hitResult == .success, let hit=hit, AXUIElementGetPid(hit, &hitPID) == .success, hitPID == pid_t(pid) else {
        try fail("Observed button is obscured or belongs to another window; no button clicked", code:"input_target_obscured", stage:"before_input")
    }
    let hitWindow: AXUIElement?
    if attr(hit, kAXRoleAttribute) as? String == kAXWindowRole {
        // Custom-drawn wxWidgets controls may expose the containing window.
        hitWindow = hit
    } else if let owner = attr(hit, kAXWindowAttribute), CFGetTypeID(owner) == AXUIElementGetTypeID() {
        hitWindow = (owner as! AXUIElement)
    } else {hitWindow = nil}
    guard let hitWindow=hitWindow, attr(hitWindow, kAXTitleAttribute) as? String == title else {
        try fail("Input target's containing window cannot be verified; no button clicked", code:"input_window_unverified", stage:"before_input")
    }
    guard let down=CGEvent(mouseEventSource:nil,mouseType:.leftMouseDown,mouseCursorPosition:p,mouseButton:.left),let up=CGEvent(mouseEventSource:nil,mouseType:.leftMouseUp,mouseCursorPosition:p,mouseButton:.left) else {try fail("Cannot construct mouse event")}
    down.post(tap:.cghidEventTap);up.post(tap:.cghidEventTap)
}
func printerRefreshToken(_ pid: pid_t, _ shot: [String:Any]) throws -> [String:Any] {
    let dialogs = try accessibleWindows(pid).filter {
        (attr($0, kAXTitleAttribute) as? String) == "发送打印任务"
    }
    guard dialogs.count == 1, let bounds = shot["bounds"] as? [String:Double],
          let left = bounds["X"], let top = bounds["Y"],
          let width = bounds["Width"], let height = bounds["Height"], width > 0, height > 0 else {
        try fail("Exact printer dialog geometry is unavailable")
    }
    var candidates: [[String:Any]] = []
    func visit(_ element: AXUIElement) {
        if (attr(element, kAXRoleAttribute) as? String) == kAXButtonRole,
           (attr(element, kAXTitleAttribute) as? String ?? "").isEmpty,
           (attr(element, kAXHelpAttribute) as? String ?? "").isEmpty,
           let position = attr(element, kAXPositionAttribute), CFGetTypeID(position) == AXValueGetTypeID(),
           let size = attr(element, kAXSizeAttribute), CFGetTypeID(size) == AXValueGetTypeID() {
            var point = CGPoint.zero
            var extent = CGSize.zero
            if AXValueGetValue(position as! AXValue, .cgPoint, &point),
               AXValueGetValue(size as! AXValue, .cgSize, &extent) {
                let x = (point.x-left)/width, y = (point.y-top)/height
                let w = extent.width/width, h = extent.height/height
                // Fixed, validated Studio layout. Require the entire small
                // control inside the right side of the printer card.
                if x > 0.65, x+w < 0.85, y > 0.25, y+h < 0.40,
                   w > 0, w < 0.10, h > 0, h < 0.10 {
                    candidates.append(["text":"printer-refresh", "confidence":1.0,
                                       "x":x, "y":y, "width":w, "height":h])
                }
            }
        }
        for child in attr(element, kAXChildrenAttribute) as? [AXUIElement] ?? [] {
            visit(child)
        }
    }
    visit(dialogs[0])
    guard candidates.count == 1 else { try fail("Unique printer refresh control absent") }
    return candidates[0]
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
    case "snapshot", "recover-window", "inspect-panel", "open-panel":
        guard args.count==3,let pid=Int32(args[1]) else {try fail("Expected mode pid exact-window-title")}
        let shot=try snapshot(pid,args[2],raise:mode != "snapshot")
        if mode=="open-panel" {
            guard args[2].hasSuffix(".gcode"),!args[2].contains("*") else {try fail("Only exact sliced job preview may open send panel")}
            try clickToken(shot,"打印单盘")
            let deadline = Date(timeIntervalSinceNow:5)
            var opened = false
            repeat {
                RunLoop.current.run(until:Date(timeIntervalSinceNow:0.1))
                // Rendering can briefly make AX unavailable. Poll observations
                // within this deadline; never repeat the preparation click.
                if let windows = try? accessibleWindows(pid) {
                    let panels=windows.filter {attr($0,kAXTitleAttribute) as? String == "发送打印任务"}
                    if panels.count > 1 {try fail("Multiple send dialogs appeared", code:"panel_ambiguous", stage:"after_open_panel")}
                    if panels.count == 1 {opened=true;break}
                }
            } while Date() < deadline
            guard opened else {try fail("Preparation click returned but the send dialog was not observed; inspect before retrying", code:"panel_not_observed", stage:"after_open_panel")}
            emit(["ok":true,"opened_panel":true,"sent":false,"title":"发送打印任务"])
        }
        else {emit(shot)}
    case "refresh-printer":
        guard args.count == 4, let pid = Int32(args[1]), args[2].hasSuffix(".gcode"),
              !args[2].contains("*"), !args[3].isEmpty else {
            try fail("Expected pid, exact job title and printer display name")
        }
        let shot = try snapshot(pid, "发送打印任务", raise:true)
        let tokens = shot["tokens"] as? [[String:Any]] ?? []
        let texts = tokens.compactMap { $0["text"] as? String }
        let models = texts.filter({$0.lowercased().hasPrefix("bambu lab ")}).map({$0.lowercased()})
        guard Set(texts).isDisjoint(with:["允许", "不允许", "打开系统设置"]),
              texts.filter({$0.trimmingCharacters(in:CharacterSet(charactersIn:" /")) == args[2]}).count == 1,
              texts.filter({$0 == args[3]}).count == 1,
              models.count == 1, ["bambu lab x2d 0.4mm", "bambu lab x2d 0.4/0.4mm"].contains(models[0]) else {
            try fail("Exact job and printer identity are not visible; no refresh clicked")
        }
        var controlShot = shot
        controlShot["tokens"] = [try printerRefreshToken(pid, shot)]
        try clickToken(controlShot, "printer-refresh")
        RunLoop.current.run(until:Date(timeIntervalSinceNow:1))
        emit(try snapshot(pid, "发送打印任务"))
    case "prepare-options":
        guard args.count==3,let pid=Int32(args[1]),args[2].hasSuffix(".gcode"),!args[2].contains("*") else {
            try fail("Expected pid and exact sliced job title")
        }
        let shot=try snapshot(pid,"发送打印任务",raise:true)
        let tokens=shot["tokens"] as? [[String:Any]] ?? []
        let texts=tokens.compactMap { $0["text"] as? String }
        guard Set(texts).isDisjoint(with:["允许","不允许","打开系统设置"]) else {
            try fail("系统弹窗遮挡发送窗口，请先处理系统提示再继续")
        }
        guard texts.filter({$0.trimmingCharacters(in:CharacterSet(charactersIn:" /"))==args[2]}).count==1 else {
            try fail("Exact job is not visible in the send dialog; no option clicked")
        }
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
} catch {
    let failure=error as? BridgeError
    emit(["ok":false,"error":failure?.message ?? String(describing:error),
          "code":failure?.code ?? "helper_failed", "stage":failure?.stage ?? "helper"])
    exit(1)
}
