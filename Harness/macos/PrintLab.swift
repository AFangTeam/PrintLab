import AppKit
import WebKit

@MainActor
final class PrintLabDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate {
    private var window: NSWindow!
    private var web: WKWebView!
    private let home = URL(string: "http://127.0.0.1:8018/#/overview")!
    private var readinessGeneration = 0

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMenus()
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        window = NSWindow(contentRect: NSRect(x:0,y:0,width:1240,height:860), styleMask:[.titled,.closable,.miniaturizable,.resizable], backing:.buffered, defer:false)
        window.title = "PrintLab"
        window.minSize = NSSize(width:720,height:560)
        window.setFrameAutosaveName("PrintLabStudioWindow")
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.contentView = web
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        connect()
    }

    private func setupMenus() {
        let bar = NSMenu()
        let appItem = NSMenuItem();bar.addItem(appItem)
        let appMenu = NSMenu();appItem.submenu = appMenu
        appMenu.addItem(withTitle:"关于 PrintLab", action:#selector(about), keyEquivalent:"")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle:"隐藏 PrintLab", action:#selector(NSApplication.hide(_:)), keyEquivalent:"h")
        let hideOthers=appMenu.addItem(withTitle:"隐藏其他",action:#selector(NSApplication.hideOtherApplications(_:)),keyEquivalent:"h")
        hideOthers.keyEquivalentModifierMask=[.command,.option]
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle:"退出 PrintLab",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q")
        let editItem=NSMenuItem();bar.addItem(editItem)
        let edit=NSMenu(title:"编辑");editItem.submenu=edit
        for (title,action,key) in [("撤销","undo:","z"),("剪切","cut:","x"),("复制","copy:","c"),("粘贴","paste:","v"),("全选","selectAll:","a")] {
            edit.addItem(withTitle:title,action:Selector(action),keyEquivalent:key)
        }
        let viewItem=NSMenuItem();bar.addItem(viewItem)
        let view=NSMenu(title:"工作室");viewItem.submenu=view
        for (index,pair) in [("总览","overview"),("项目图册","projects"),("购物清单","shop"),("资料与经验","library"),("设备与材料","device")].enumerated() {
            let item=view.addItem(withTitle:pair.0,action:#selector(goToSection(_:)),keyEquivalent:String(index+1))
            item.representedObject=pair.1;item.target=self
        }
        view.addItem(.separator())
        let reload=view.addItem(withTitle:"重新载入",action:#selector(reload),keyEquivalent:"r");reload.target=self
        let browser=view.addItem(withTitle:"在浏览器中打开",action:#selector(openInBrowser),keyEquivalent:"");browser.target=self
        let folder=view.addItem(withTitle:"打开工作空间文件夹",action:#selector(openWorkspace),keyEquivalent:"");folder.target=self
        let windowItem=NSMenuItem();bar.addItem(windowItem)
        let winMenu=NSMenu(title:"窗口");windowItem.submenu=winMenu
        winMenu.addItem(withTitle:"最小化",action:#selector(NSWindow.performMiniaturize(_:)),keyEquivalent:"m")
        winMenu.addItem(withTitle:"关闭窗口",action:#selector(NSWindow.performClose(_:)),keyEquivalent:"w")
        NSApp.windowsMenu=winMenu
        NSApp.mainMenu=bar
    }

    @objc private func about() {
        NSApp.orderFrontStandardAboutPanel(options:[.applicationName:"PrintLab",.applicationVersion:"1.0",.credits:NSAttributedString(string:"PrintLab by AFangTeam\n本机项目 · 模型共创 · 打印管理")])
    }
    @objc private func goToSection(_ item:NSMenuItem) {
        guard let section=item.representedObject as? String else{return}
        window.makeKeyAndOrderFront(nil)
        web.load(URLRequest(url:URL(string:"http://127.0.0.1:8018/#/\(section)")!))
    }
    @objc private func reload(){connect()}
    @objc private func openInBrowser(){NSWorkspace.shared.open(web.url?.host=="127.0.0.1" ? web.url! : home)}
    @objc private func openWorkspace(){NSWorkspace.shared.open(URL(fileURLWithPath:Bundle.main.object(forInfoDictionaryKey:"PrintLabWorkspace") as? String ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("PrintLab").path,isDirectory:true))}

    private func startExistingService(_ label:String) {
        let proc=Process();proc.executableURL=URL(fileURLWithPath:"/bin/launchctl")
        // No -k: an already-running service, including an active print, stays running.
        proc.arguments=["kickstart","gui/\(getuid())/\(label)"]
        proc.standardOutput=FileHandle.nullDevice;proc.standardError=FileHandle.nullDevice
        try? proc.run()
    }
    private func connect() {
        let destination=web.url.flatMap{internalURL($0) ? $0:nil} ?? home
        readinessGeneration+=1
        let generation=readinessGeneration
        message("正在打开设计工作室", detail:"读取本机项目与材料…", retry:false)
        checkReady(attempt:0,generation:generation,destination:destination)
    }
    private func checkReady(attempt:Int,generation:Int,destination:URL) {
        var request=URLRequest(url:URL(string:"http://127.0.0.1:8018/api/health")!)
        request.timeoutInterval=2
        URLSession.shared.dataTask(with:request){[weak self] data,response,error in
            let health = data.flatMap{try? JSONSerialization.jsonObject(with:$0) as? [String:Any]}
            let ready=(response as? HTTPURLResponse)?.statusCode==200 && health?["ok"] as? Bool==true
            DispatchQueue.main.async {
                guard let self=self,self.readinessGeneration==generation else{return}
                if ready {
                    self.startExistingService("com.afang.printlab.bambuddy")
                    self.web.load(URLRequest(url:destination))
                } else if attempt<10 {
                    if attempt==0 {self.startExistingService("com.afang.printlab.studio")}
                    DispatchQueue.main.asyncAfter(deadline:.now()+0.5){self.checkReady(attempt:attempt+1,generation:generation,destination:destination)}
                } else {
                    self.message("工作室暂时无法连接",detail:"本机服务尚未就绪。请稍后重试，或打开 PrintLab 文件夹查看资料。",retry:true)
                }
            }
        }.resume()
    }
    private func message(_ title:String,detail:String,retry:Bool) {
        let actions=retry ? "<a href='printlab://retry'>重新连接</a><a class='secondary' href='printlab://workspace'>打开工作空间</a>" : ""
        web.loadHTMLString("""
        <!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
        :root{color-scheme:light dark}body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:0;min-height:100vh;display:grid;place-items:center;background:#f7f8f5;color:#28332b}main{text-align:center;max-width:480px;padding:32px}h1{font-size:28px;font-weight:600}p{line-height:1.8;color:#757e73}a{display:inline-block;margin:24px 8px 0;padding:12px 24px;border-radius:8px;text-decoration:none;background:#456c4c;color:white}.secondary{background:#e6eddf;color:#456c4c}@media(prefers-color-scheme:dark){body{background:#191e1a;color:#e1e8dc}p{color:#a1aa9a}}
        </style><main><h1>\(title)</h1><p>\(detail)</p>\(actions)</main></html>
        """,baseURL:nil)
    }
    private func internalURL(_ url:URL)->Bool {url.scheme=="http" && url.host=="127.0.0.1" && url.port==8018}
    func webView(_ webView:WKWebView,decidePolicyFor navigationAction:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void) {
        guard let url=navigationAction.request.url else{decisionHandler(.cancel);return}
        if url.scheme=="printlab" {
            if url.host=="retry" {connect()}
            if url.host=="workspace" {openWorkspace()}
            decisionHandler(.cancel);return
        }
        if navigationAction.shouldPerformDownload {
            NSWorkspace.shared.open(url);decisionHandler(.cancel);return
        }
        if internalURL(url) || url.scheme=="about" {decisionHandler(.allow);return}
        if navigationAction.navigationType == .linkActivated, ["http","https"].contains(url.scheme ?? "") {NSWorkspace.shared.open(url)}
        decisionHandler(.cancel)
    }
    func webView(_ webView:WKWebView,createWebViewWith configuration:WKWebViewConfiguration,for navigationAction:WKNavigationAction,windowFeatures:WKWindowFeatures)->WKWebView? {
        if let url=navigationAction.request.url {
            if internalURL(url){web.load(URLRequest(url:url))}
            else if ["http","https"].contains(url.scheme ?? ""){NSWorkspace.shared.open(url)}
        }
        return nil
    }
    func webView(_ webView:WKWebView,didFailProvisionalNavigation navigation:WKNavigation!,withError error:Error) {
        if (error as NSError).code != NSURLErrorCancelled {message("页面暂时无法打开",detail:"请通过“工作室 → 重新载入”再次连接。",retry:true)}
    }
    func applicationShouldHandleReopen(_ sender:NSApplication,hasVisibleWindows flag:Bool)->Bool {
        window.makeKeyAndOrderFront(nil);return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool {false}
}
MainActor.assumeIsolated {
    let application=NSApplication.shared
    application.setActivationPolicy(.regular)
    let delegate=PrintLabDelegate()
    application.delegate=delegate
    application.run()
}
