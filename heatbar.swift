// heatbar.swift — stan termiczny Maca na pasku menu.
//
// Nic nie mierzy samodzielnie: czyta ~/.thermal-guard/status.json, ktory thermal-guard
// zapisuje przy kazdym przebiegu (co 15 s). Dzieki temu pasek kosztuje zero CPU i nigdy
// nie pokazuje czegos innego niz bezpiecznik.
//
// Na pasku:  🌡 C67° G64° B33° 🌀3.3k 42W
//   C/G/B — chip, GPU, bateria;  🌀 — obroty (⚠︎0 gdy stoja przy goracym chipie);
//   W — pobor mocy;  ⚡ — macOS dlawi CPU;  ⏸ — cos wstrzymane.
//
// Budowa:  swiftc -O -o ~/.local/bin/heatbar heatbar.swift

import Cocoa

let base = NSString(string: "~/.thermal-guard").expandingTildeInPath
let statusPath = base + "/status.json"
let historyPath = base + "/history.csv"
let logPath = base + "/guard.log"
let commandPath = base + "/command"
let reportBin = NSString(string: "~/.local/bin/thermal-report").expandingTildeInPath

struct Zadanie { let nazwa: String; let minuty: Int }

struct Snap {
    var chip: Double?, gpu: Double?, batt: Double?, watts: Double?
    var fans: [Int] = []
    var pct: Int?, onAC = true, level = 0, load = 0.0, cpuLimit = 100
    var reason = "", topProc: String?, topCPU: Int?
    var paused: [String] = []
    var recznaPauza = false
    var trend: Double?, eta: Double?
    var zadania: [Zadanie] = []
    var pauzyDzis = 0, ubiciaDzis = 0
    var ostatniPad: String?
    var progPauza: Double?, progUbicie: Double?
    var stamp = ""
    var stale = true
}

func readSnap() -> Snap? {
    guard let data = FileManager.default.contents(atPath: statusPath),
          let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
    var s = Snap()
    s.chip = j["chip_c"] as? Double
    s.gpu = j["gpu_c"] as? Double
    s.batt = j["bateria_c"] as? Double
    s.watts = j["waty"] as? Double
    s.fans = (j["wentylatory"] as? [Int]) ?? []
    s.pct = j["bateria_pct"] as? Int
    s.onAC = (j["na_zasilaczu"] as? Bool) ?? true
    s.level = (j["poziom"] as? Int) ?? 0
    s.load = (j["load1"] as? Double) ?? 0
    s.cpuLimit = (j["cpu_limit"] as? Int) ?? 100
    s.reason = (j["powod"] as? String) ?? ""
    s.topProc = j["top_proc"] as? String
    s.topCPU = j["top_cpu"] as? Int
    s.paused = (j["wstrzymane"] as? [String]) ?? []
    s.recznaPauza = (j["reczna_pauza"] as? Bool) ?? false
    s.trend = j["trend_c_min"] as? Double
    s.eta = j["eta_pauza_min"] as? Double
    s.stamp = (j["czas"] as? String) ?? ""
    if let z = j["zadania"] as? [[String: Any]] {
        s.zadania = z.map { Zadanie(nazwa: ($0["nazwa"] as? String) ?? "?",
                                    minuty: ($0["minuty"] as? Int) ?? 0) }
    }
    if let st = j["statystyki"] as? [String: Any] {
        s.pauzyDzis = (st["pauzy"] as? Int) ?? 0
        s.ubiciaDzis = (st["ubicia"] as? Int) ?? 0
    }
    if let p = j["ostatni_pad"] as? [String: Any] { s.ostatniPad = p["czas"] as? String }
    if let pr = j["progi"] as? [String: Any] {
        s.progPauza = pr["pauza"] as? Double
        s.progUbicie = pr["ubicie"] as? Double
    }
    if let m = try? FileManager.default.attributesOfItem(atPath: statusPath)[.modificationDate] as? Date {
        s.stale = Date().timeIntervalSince(m) > 90     // guard nie zyje albo sie zaciął
    }
    return s
}

/// Wykres temperatury chipa z historii — znakami blokowymi, bez rysowania.
func sparkline(limit: Int = 40) -> (String, Double, Double)? {
    guard let tekst = try? String(contentsOfFile: historyPath, encoding: .utf8) else { return nil }
    var wartosci: [Double] = []
    for linia in tekst.split(separator: "\n").suffix(limit + 1) {
        let c = linia.split(separator: ",", omittingEmptySubsequences: false)
        if c.count > 2, let v = Double(c[2]) { wartosci.append(v) }
    }
    guard wartosci.count >= 3 else { return nil }
    let bloki = Array("▁▂▃▄▅▆▇█")
    let lo = wartosci.min()!, hi = wartosci.max()!
    let rozpietosc = max(hi - lo, 1.0)
    let linia = wartosci.map { v -> Character in
        let i = Int(((v - lo) / rozpietosc) * Double(bloki.count - 1))
        return bloki[min(max(i, 0), bloki.count - 1)]
    }
    return (String(linia), lo, hi)
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

    /// Kolor wg poziomu guarda, nie wg golej liczby — pasek ma mowic to samo co bezpiecznik.
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
                string: "🌡 —", attributes: [.foregroundColor: NSColor.secondaryLabelColor])
            return
        }
        var parts: [String] = []
        parts.append(s.chip.map { String(format: "C%.0f°", $0) } ?? "C—")
        if let g = s.gpu { parts.append(String(format: "G%.0f°", g)) }
        if let b = s.batt { parts.append(String(format: "B%.0f°", b)) }
        if let f = s.fans.max() {
            if f == 0 {
                parts.append((s.chip ?? 0) >= 70 ? "🌀⚠︎0" : "🌀0")
            } else {
                parts.append("🌀" + (f >= 1000 ? String(format: "%.1fk", Double(f) / 1000.0) : "\(f)"))
            }
        }
        // pobor mocy: najlepszy pojedynczy wskaznik "jak bardzo sie meczy"
        if let w = s.watts, w >= 1 { parts.append(String(format: "%.0fW", w)) }
        if s.cpuLimit < 100 { parts.append("⚡") }        // macOS sam dlawi CPU
        if !s.paused.isEmpty { parts.append(s.recznaPauza ? "⏸︎" : "⏸") }

        item.button?.attributedTitle = NSAttributedString(
            string: "🌡 " + parts.joined(separator: " "),
            attributes: [.foregroundColor: tint(s),
                         .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)])
        var tip = s.reason.isEmpty ? "thermal-guard: spokój" : s.reason
        if let e = s.eta { tip += String(format: "\nDo pauzy ok. %.0f min przy obecnym tempie", e) }
        item.button?.toolTip = tip
    }

    func menuNeedsUpdate(_ m: NSMenu) {
        m.removeAllItems()
        guard let s = readSnap() else {
            m.addItem(NSMenuItem(title: "brak danych — czy thermal-guard działa?", action: nil, keyEquivalent: ""))
            addTail(m, paused: false); return
        }
        func row(_ t: String) { m.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
        func mono(_ t: String) {
            let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            it.attributedTitle = NSAttributedString(
                string: t, attributes: [.font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)])
            m.addItem(it)
        }

        if s.stale { row("⚠️ dane nieświeże (\(s.stamp)) — guard mógł paść") }
        if let pad = s.ostatniPad { row("🛑 Mac zgasł bez ostrzeżenia: \(pad)") }

        row("Chip:  \(s.chip.map { String(format: "%.1f °C", $0) } ?? "n/d")"
            + (s.gpu != nil ? String(format: "   GPU: %.1f °C", s.gpu!) : ""))
        row("Bateria:  \(s.batt.map { String(format: "%.1f °C", $0) } ?? "n/d")")
        let fanTxt = s.fans.isEmpty ? "n/d" : s.fans.map { $0 == 0 ? "stoi" : "\($0) obr/min" }.joined(separator: ", ")
        row("Wentylatory:  \(fanTxt)")
        if let w = s.watts { row(String(format: "Pobór:  %.1f W", w)) }
        row("Zasilanie:  " + (s.onAC ? "zasilacz" : "bateria \(s.pct.map { "\($0)%" } ?? "?")"))
        row(String(format: "Obciążenie:  %.2f    CPU dostępne: %d%%", s.load, s.cpuLimit))

        // wykres ostatniej godziny
        if let (linia, lo, hi) = sparkline() {
            m.addItem(.separator())
            mono("  " + linia)
            row(String(format: "   ostatnie pomiary: %.0f–%.0f °C", lo, hi))
        }
        if let t = s.trend, t > 0.5 {
            if let e = s.eta {
                row(String(format: "📈 rośnie %.1f °C/min — do pauzy ok. %.0f min", t, e))
            } else {
                row(String(format: "📈 rośnie %.1f °C/min", t))
            }
        }

        m.addItem(.separator())
        if !s.zadania.isEmpty {
            row("Zadania pod nadzorem (safe-run):")
            for z in s.zadania { row("   • \(z.nazwa) — \(z.minuty) min") }
        }
        if let p = s.topProc, let c = s.topCPU { row("Najwięcej CPU:  \(p) (\(c)%)") }
        if !s.paused.isEmpty {
            row("⏸ Wstrzymane: " + s.paused.joined(separator: ", ")
                + (s.recznaPauza ? "  (ręcznie)" : ""))
        } else {
            let opis = ["spokój", "ciepło", "GORĄCO — pauza", "KRYTYCZNIE"][min(s.level, 3)]
            row("Stan: \(opis)" + (s.reason.isEmpty ? "" : " — \(s.reason)"))
        }
        if let pp = s.progPauza, let pu = s.progUbicie {
            row(String(format: "Progi chipa:  pauza %.0f °C, ubicie %.0f °C", pp, pu))
        }
        if s.pauzyDzis > 0 || s.ubiciaDzis > 0 {
            row("Dziś: \(s.pauzyDzis) × pauza" + (s.ubiciaDzis > 0 ? ", \(s.ubiciaDzis) × ubicie" : ""))
        }
        addTail(m, paused: !s.paused.isEmpty)
    }

    func addTail(_ m: NSMenu, paused: Bool) {
        m.addItem(.separator())
        if paused {
            m.addItem(withTitle: "▶︎ Wznów wstrzymane", action: #selector(resume), keyEquivalent: "").target = self
        } else {
            m.addItem(withTitle: "⏸ Zamroź teraz wszystko ciężkie", action: #selector(freeze), keyEquivalent: "").target = self
        }
        m.addItem(withTitle: "Eksportuj raport dla serwisu…", action: #selector(report), keyEquivalent: "").target = self
        m.addItem(withTitle: "Pokaż log guarda", action: #selector(openLog), keyEquivalent: "").target = self
        m.addItem(.separator())
        m.addItem(withTitle: "Zakończ heatbar", action: #selector(quit), keyEquivalent: "q").target = self
    }

    /// Rozkazy ida przez plik — guard wykonuje je i kasuje. Pasek nie dotyka procesow sam,
    /// zeby istniala dokladnie JEDNA rzecz decydujaca o pauzach.
    func send(_ rozkaz: String) {
        try? rozkaz.write(toFile: commandPath, atomically: true, encoding: .utf8)
    }

    @objc func freeze() { send("freeze") }
    @objc func resume() { send("resume") }

    @objc func report() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: reportBin)
        p.arguments = ["--dni", "14"]
        let pipe = Pipe()
        p.standardOutput = pipe
        do { try p.run() } catch { return }
        p.waitUntilExit()
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let sciezka = out.trimmingCharacters(in: .whitespacesAndNewlines)
        if !sciezka.isEmpty {
            NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: sciezka)])
        }
    }

    @objc func openLog() { NSWorkspace.shared.open(URL(fileURLWithPath: logPath)) }
    @objc func quit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // bez ikony w Docku i bez okna
let bar = Bar()
app.run()
