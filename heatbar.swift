// heatbar.swift - thermal state of the Mac in the menu bar.
//
// It measures nothing on its own: it reads ~/.thermal-guard/status.json, which thermal-guard
// writes on every cycle (every 15 s). That is why it costs no CPU and can never disagree with
// the guard. Manual commands are passed back through a file and executed by the daemon, so
// exactly one process ever decides what gets paused.
//
// In the bar:  thermometer C67 G64 B33 fan3.3k 42W RAM62% DISK46%
//   C/G/B - chip, GPU, battery;  fan - rpm (warning when stopped while hot);  W - power draw;
//   brain - RAM used;  disk - disk used;  bolt - macOS is throttling;  pause - something paused.
//
// Pick what is shown: menu > Show in the bar (checkboxes), stored in ~/.thermal-guard/heatbar.json.
// Language: TG_LANG=en|pl, or "lang" in ~/.thermal-guard/config.json. Default: en.
//
// Build:  swiftc -O -o ~/.local/bin/heatbar heatbar.swift

import Cocoa

let VERSION = "1.0"
let SIGNATURE = "thermal-guard v\(VERSION)  ·  FOCUS FRAME 2026"

let base = NSString(string: "~/.thermal-guard").expandingTildeInPath
let statusPath = base + "/status.json"
let historyPath = base + "/history.csv"
let logPath = base + "/guard.log"
let commandPath = base + "/command"
let configPath = base + "/config.json"
let prefsPath = base + "/heatbar.json"
let reportBin = NSString(string: "~/.local/bin/thermal-report").expandingTildeInPath

// MARK: - language

let lang: String = {
    let env = (ProcessInfo.processInfo.environment["TG_LANG"] ?? "").lowercased()
    if env.hasPrefix("pl") { return "pl" }
    if env.hasPrefix("en") { return "en" }
    if let d = FileManager.default.contents(atPath: configPath),
       let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
       let l = (j["lang"] as? String)?.lowercased() {
        if l.hasPrefix("pl") { return "pl" }
        if l.hasPrefix("en") { return "en" }
    }
    return "en"
}()

let PL: [String: String] = [
    "no data - is thermal-guard running?": "brak danych - czy thermal-guard działa?",
    "data is stale (%@) - the guard may have died": "dane nieświeże (%@) - guard mógł paść",
    "the Mac shut down without warning: %@": "Mac zgasł bez ostrzeżenia: %@",
    "Battery:  %@": "Bateria:  %@",
    "Fans:  %@": "Wentylatory:  %@",
    "stopped": "stoi", "%d rpm": "%d obr/min", "n/a": "n/d",
    "Draw:  %.1f W": "Pobór:  %.1f W",
    "RAM:  %.1f / %.1f GB (%d%%)": "RAM:  %.1f / %.1f GB (%d%%)",
    "swap %.2f GB": "swap %.2f GB",
    "Disk:  %d / %d GB used (%d%%)": "Dysk:  %d / %d GB zajęte (%d%%)",
    "Power:  %@": "Zasilanie:  %@",
    "AC adapter": "zasilacz", "battery %@": "bateria %@",
    "Load:  %.2f    CPU available: %d%%": "Obciążenie:  %.2f    CPU dostępne: %d%%",
    "   readings: %.0f-%.0f C": "   ostatnie pomiary: %.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "rośnie %.1f C/min - do pauzy ok. %.0f min",
    "rising %.1f C/min": "rośnie %.1f C/min",
    "Supervised jobs (safe-run):": "Zadania pod nadzorem (safe-run):",
    "Top CPU:  %@ (%d%%)": "Najwięcej CPU:  %@ (%d%%)",
    "Paused: %@": "Wstrzymane: %@",
    "  (manual)": "  (ręcznie)",
    "State: %@": "Stan: %@",
    "calm": "spokój", "warm": "ciepło", "HOT - paused": "GORĄCO - pauza", "CRITICAL": "KRYTYCZNIE",
    "Chip thresholds:  pause %.0f C, kill %.0f C": "Progi chipa:  pauza %.0f C, ubicie %.0f C",
    "Today: %d x pause": "Dziś: %d x pauza", ", %d x kill": ", %d x ubicie",
    "Resume paused jobs": "Wznów wstrzymane",
    "Freeze all heavy jobs now": "Zamroź teraz wszystko ciężkie",
    "Show in the bar": "Pokaż na pasku",
    "Export report for a repair shop...": "Eksportuj raport dla serwisu...",
    "Show the guard log": "Pokaż log guarda",
    "Quit heatbar": "Zakończ heatbar",
    "Chip temperature": "Temperatura chipa", "GPU temperature": "Temperatura GPU",
    "Battery temperature": "Temperatura baterii", "Fan rpm": "Obroty wentylatorów",
    "Power draw (W)": "Pobór mocy (W)", "RAM used": "Zajęty RAM", "Disk used": "Zajęty dysk",
    "Throttling marker": "Znacznik dławienia", "Pause marker": "Znacznik pauzy",
]

func T(_ s: String) -> String { lang == "pl" ? (PL[s] ?? s) : s }

// MARK: - what to show in the bar

/// Every bar element can be switched on and off: the menu bar is scarce space and everyone
/// wants something different there. The choice lives in heatbar.json, so it survives a restart.
enum Item: String, CaseIterable {
    case chip, gpu, battery, fans, watts, ram, disk, throttle, paused

    var label: String {
        switch self {
        case .chip: return T("Chip temperature")
        case .gpu: return T("GPU temperature")
        case .battery: return T("Battery temperature")
        case .fans: return T("Fan rpm")
        case .watts: return T("Power draw (W)")
        case .ram: return T("RAM used")
        case .disk: return T("Disk used")
        case .throttle: return T("Throttling marker")
        case .paused: return T("Pause marker")
        }
    }

    /// Safety-related items are on by default; RAM and disk are an extra.
    var byDefault: Bool {
        switch self {
        case .ram, .disk: return false
        default: return true
        }
    }
}

final class Prefs {
    private var on: [String: Bool] = [:]
    init() { load() }
    func load() {
        guard let d = FileManager.default.contents(atPath: prefsPath),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let s = j["show"] as? [String: Bool] else { return }
        on = s
    }
    func save() {
        if let d = try? JSONSerialization.data(withJSONObject: ["show": on], options: [.prettyPrinted]) {
            try? d.write(to: URL(fileURLWithPath: prefsPath))
        }
    }
    func enabled(_ i: Item) -> Bool { on[i.rawValue] ?? i.byDefault }
    func toggle(_ i: Item) { on[i.rawValue] = !enabled(i); save() }
}

let prefs = Prefs()

// MARK: - snapshot

struct Job { let name: String; let minutes: Int }

struct Snap {
    var chip: Double?, gpu: Double?, batt: Double?, watts: Double?
    var fans: [Int] = []
    var ramUsed: Double?, ramTotal: Double?, swap: Double?
    var diskUsed: Int?, diskTotal: Int?, diskPct: Int?
    var pct: Int?, onAC = true, level = 0, load = 0.0, cpuLimit = 100
    var reason = "", topProc: String?, topCPU: Int?
    var paused: [String] = []
    var manualPause = false
    var trend: Double?, eta: Double?
    var jobs: [Job] = []
    var pausesToday = 0, killsToday = 0
    var lastCrash: String?
    var thrPause: Double?, thrKill: Double?
    var stamp = ""
    var stale = true
}

func readSnap() -> Snap? {
    guard let data = FileManager.default.contents(atPath: statusPath),
          let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
    var s = Snap()
    s.chip = j["chip_c"] as? Double
    s.gpu = j["gpu_c"] as? Double
    s.batt = j["battery_c"] as? Double
    s.watts = j["watts"] as? Double
    s.fans = (j["fans"] as? [Int]) ?? []
    s.ramUsed = j["ram_used_gb"] as? Double
    s.ramTotal = j["ram_total_gb"] as? Double
    s.swap = j["swap_used_gb"] as? Double
    s.diskUsed = j["disk_used_gb"] as? Int
    s.diskTotal = j["disk_total_gb"] as? Int
    s.diskPct = j["disk_used_pct"] as? Int
    s.pct = j["battery_pct"] as? Int
    s.onAC = (j["on_ac"] as? Bool) ?? true
    s.level = (j["level"] as? Int) ?? 0
    s.load = (j["load1"] as? Double) ?? 0
    s.cpuLimit = (j["cpu_limit"] as? Int) ?? 100
    s.reason = (j["reason"] as? String) ?? ""
    s.topProc = j["top_proc"] as? String
    s.topCPU = j["top_cpu"] as? Int
    s.paused = (j["paused"] as? [String]) ?? []
    s.manualPause = (j["manual_pause"] as? Bool) ?? false
    s.trend = j["trend_c_min"] as? Double
    s.eta = j["eta_pause_min"] as? Double
    s.stamp = (j["time"] as? String) ?? ""
    if let z = j["jobs"] as? [[String: Any]] {
        s.jobs = z.map { Job(name: ($0["name"] as? String) ?? "?", minutes: ($0["minutes"] as? Int) ?? 0) }
    }
    if let st = j["stats"] as? [String: Any] {
        s.pausesToday = (st["pauses"] as? Int) ?? 0
        s.killsToday = (st["kills"] as? Int) ?? 0
    }
    if let p = j["last_hard_shutdown"] as? [String: Any] { s.lastCrash = p["time"] as? String }
    if let t = j["thresholds"] as? [String: Any] {
        s.thrPause = t["pause"] as? Double
        s.thrKill = t["kill"] as? Double
    }
    if let m = try? FileManager.default.attributesOfItem(atPath: statusPath)[.modificationDate] as? Date {
        s.stale = Date().timeIntervalSince(m) > 90
    }
    return s
}

/// Chip temperature graph from the history file - block characters, no drawing needed.
func sparkline(limit: Int = 40) -> (String, Double, Double)? {
    guard let text = try? String(contentsOfFile: historyPath, encoding: .utf8) else { return nil }
    var values: [Double] = []
    for line in text.split(separator: "\n").suffix(limit + 1) {
        let c = line.split(separator: ",", omittingEmptySubsequences: false)
        if c.count > 2, let v = Double(c[2]) { values.append(v) }
    }
    guard values.count >= 3 else { return nil }
    let blocks = Array("▁▂▃▄▅▆▇█")
    let lo = values.min()!, hi = values.max()!
    let span = max(hi - lo, 1.0)
    let line = values.map { v -> Character in
        let i = Int(((v - lo) / span) * Double(blocks.count - 1))
        return blocks[min(max(i, 0), blocks.count - 1)]
    }
    return (String(line), lo, hi)
}

final class Bar: NSObject, NSMenuDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let menu = NSMenu()
    var timer: Timer?

    override init() {
        super.init()
        menu.delegate = self
        item.menu = menu
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.refresh() }
    }

    /// Colour follows the guard's level, not a raw number - the bar must say the same thing
    /// the safety net says.
    func tint(_ s: Snap) -> NSColor {
        if s.stale { return .secondaryLabelColor }
        switch s.level {
        case 3: return .systemRed
        case 2: return .systemOrange
        case 1: return .systemYellow
        default: return .labelColor
        }
    }

    func refresh() {
        guard let s = readSnap() else {
            item.button?.attributedTitle = NSAttributedString(
                string: "\u{1F321} —", attributes: [.foregroundColor: NSColor.secondaryLabelColor])
            return
        }
        var parts: [String] = []
        if prefs.enabled(.chip) { parts.append(s.chip.map { String(format: "C%.0f°", $0) } ?? "C—") }
        if prefs.enabled(.gpu), let g = s.gpu { parts.append(String(format: "G%.0f°", g)) }
        if prefs.enabled(.battery), let b = s.batt { parts.append(String(format: "B%.0f°", b)) }
        if prefs.enabled(.fans), let f = s.fans.max() {
            if f == 0 {
                parts.append((s.chip ?? 0) >= 70 ? "\u{1F300}\u{26A0}\u{FE0E}0" : "\u{1F300}0")
            } else {
                parts.append("\u{1F300}" + (f >= 1000 ? String(format: "%.1fk", Double(f) / 1000.0) : "\(f)"))
            }
        }
        if prefs.enabled(.watts), let w = s.watts, w >= 1 { parts.append(String(format: "%.0fW", w)) }
        if prefs.enabled(.ram), let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            // swap in use is a stronger signal than the RAM percentage alone, so we flag it
            let swapping = (s.swap ?? 0) > 0.1
            parts.append(String(format: "\u{1F9E0}%.0f%%%@", 100 * u / t, swapping ? "\u{26A0}\u{FE0E}" : ""))
        }
        if prefs.enabled(.disk), let p = s.diskPct { parts.append("\u{1F4BE}\(p)%") }
        if prefs.enabled(.throttle), s.cpuLimit < 100 { parts.append("\u{26A1}") }
        if prefs.enabled(.paused), !s.paused.isEmpty { parts.append("\u{23F8}") }

        item.button?.attributedTitle = NSAttributedString(
            string: "\u{1F321} " + parts.joined(separator: " "),
            attributes: [.foregroundColor: tint(s),
                         .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)])
        var tip = s.reason.isEmpty ? "thermal-guard: " + T("calm") : s.reason
        if let e = s.eta { tip += String(format: "\n%.0f min", e) }
        item.button?.toolTip = tip
    }

    func menuNeedsUpdate(_ m: NSMenu) {
        m.removeAllItems()
        guard let s = readSnap() else {
            m.addItem(NSMenuItem(title: T("no data - is thermal-guard running?"), action: nil, keyEquivalent: ""))
            addTail(m, paused: false); return
        }
        func row(_ t: String) { m.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
        func mono(_ t: String) {
            let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            it.attributedTitle = NSAttributedString(
                string: t, attributes: [.font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)])
            m.addItem(it)
        }
        let na = T("n/a")

        if s.stale { row("\u{26A0}\u{FE0F} " + String(format: T("data is stale (%@) - the guard may have died"), s.stamp)) }
        if let c = s.lastCrash { row("\u{1F6D1} " + String(format: T("the Mac shut down without warning: %@"), c)) }

        row("Chip:  " + (s.chip.map { String(format: "%.1f °C", $0) } ?? na)
            + (s.gpu != nil ? String(format: "     GPU: %.1f °C", s.gpu!) : ""))
        row(String(format: T("Battery:  %@"), s.batt.map { String(format: "%.1f °C", $0) } ?? na))
        let fanTxt = s.fans.isEmpty ? na
            : s.fans.map { $0 == 0 ? T("stopped") : String(format: T("%d rpm"), $0) }.joined(separator: ", ")
        row(String(format: T("Fans:  %@"), fanTxt))
        if let w = s.watts { row(String(format: T("Draw:  %.1f W"), w)) }
        if let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            var line = String(format: T("RAM:  %.1f / %.1f GB (%d%%)"), u, t, Int(100 * u / t))
            if let sw = s.swap, sw > 0.01 { line += "     " + String(format: T("swap %.2f GB"), sw) }
            row(line)
        }
        if let du = s.diskUsed, let dt = s.diskTotal, let dp = s.diskPct {
            row(String(format: T("Disk:  %d / %d GB used (%d%%)"), du, dt, dp))
        }
        row(String(format: T("Power:  %@"),
                   s.onAC ? T("AC adapter")
                          : String(format: T("battery %@"), s.pct.map { "\($0)%" } ?? "?")))
        row(String(format: T("Load:  %.2f    CPU available: %d%%"), s.load, s.cpuLimit))

        if let (line, lo, hi) = sparkline() {
            m.addItem(.separator())
            mono("  " + line)
            row(String(format: T("   readings: %.0f-%.0f C"), lo, hi))
        }
        if let t = s.trend, t > 0.5 {
            if let e = s.eta {
                row("\u{1F4C8} " + String(format: T("rising %.1f C/min - about %.0f min to pause"), t, e))
            } else {
                row("\u{1F4C8} " + String(format: T("rising %.1f C/min"), t))
            }
        }

        m.addItem(.separator())
        if !s.jobs.isEmpty {
            row(T("Supervised jobs (safe-run):"))
            for j in s.jobs { row("   - \(j.name) — \(j.minutes) min") }
        }
        if let p = s.topProc, let c = s.topCPU { row(String(format: T("Top CPU:  %@ (%d%%)"), p, c)) }
        if !s.paused.isEmpty {
            row("\u{23F8} " + String(format: T("Paused: %@"), s.paused.joined(separator: ", "))
                + (s.manualPause ? T("  (manual)") : ""))
        } else {
            let names = [T("calm"), T("warm"), T("HOT - paused"), T("CRITICAL")]
            row(String(format: T("State: %@"), names[min(s.level, 3)])
                + (s.reason.isEmpty ? "" : " — \(s.reason)"))
        }
        if let pp = s.thrPause, let pk = s.thrKill {
            row(String(format: T("Chip thresholds:  pause %.0f C, kill %.0f C"), pp, pk))
        }
        if s.pausesToday > 0 || s.killsToday > 0 {
            row(String(format: T("Today: %d x pause"), s.pausesToday)
                + (s.killsToday > 0 ? String(format: T(", %d x kill"), s.killsToday) : ""))
        }
        addTail(m, paused: !s.paused.isEmpty)
    }

    func addTail(_ m: NSMenu, paused: Bool) {
        m.addItem(.separator())
        if paused {
            m.addItem(withTitle: "\u{25B6} " + T("Resume paused jobs"),
                      action: #selector(resume), keyEquivalent: "").target = self
        } else {
            m.addItem(withTitle: "\u{23F8} " + T("Freeze all heavy jobs now"),
                      action: #selector(freeze), keyEquivalent: "").target = self
        }

        // checkboxes deciding what appears in the bar; state kept in heatbar.json
        let showItem = NSMenuItem(title: T("Show in the bar"), action: nil, keyEquivalent: "")
        let sub = NSMenu()
        for (i, it) in Item.allCases.enumerated() {
            let mi = NSMenuItem(title: it.label, action: #selector(toggleItem(_:)), keyEquivalent: "")
            mi.target = self
            mi.tag = i
            mi.state = prefs.enabled(it) ? .on : .off
            sub.addItem(mi)
        }
        showItem.submenu = sub
        m.addItem(showItem)

        m.addItem(withTitle: T("Export report for a repair shop..."), action: #selector(report), keyEquivalent: "").target = self
        m.addItem(withTitle: T("Show the guard log"), action: #selector(openLog), keyEquivalent: "").target = self
        m.addItem(.separator())

        // nazwa, wersja i sygnatura autora — pozycja nieaktywna, sama informacja
        let sig = NSMenuItem(title: SIGNATURE, action: nil, keyEquivalent: "")
        sig.isEnabled = false
        m.addItem(sig)
        m.addItem(withTitle: T("Quit heatbar"), action: #selector(quit), keyEquivalent: "q").target = self
    }

    @objc func toggleItem(_ sender: NSMenuItem) {
        let all = Item.allCases
        guard sender.tag >= 0 && sender.tag < all.count else { return }
        prefs.toggle(all[sender.tag])
        refresh()
    }

    /// Commands go through a file - the daemon executes and clears them.
    func send(_ command: String) {
        try? command.write(toFile: commandPath, atomically: true, encoding: .utf8)
    }

    @objc func freeze() { send("freeze") }
    @objc func resume() { send("resume") }

    @objc func report() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: reportBin)
        p.arguments = ["--days", "14"]
        let pipe = Pipe()
        p.standardOutput = pipe
        do { try p.run() } catch { return }
        p.waitUntilExit()
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let path = out.trimmingCharacters(in: .whitespacesAndNewlines)
        if !path.isEmpty {
            NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
        }
    }

    @objc func openLog() { NSWorkspace.shared.open(URL(fileURLWithPath: logPath)) }
    @objc func quit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon, no window
let bar = Bar()
app.run()
