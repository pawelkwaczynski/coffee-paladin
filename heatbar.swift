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
    "!": "!",
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
    "Settings": "Ustawienia",
    "Chip pause threshold": "Próg pauzy chipa",
    "Battery gate": "Bramka baterii",
    "pause below this charge when unplugged": "pauza poniżej tego poziomu bez zasilacza",
    "TOO LOW - an idle M-series chip already sits at 40-55 C, the guard would pause constantly":
        "ZA NISKO - bezczynny chip M-serii ma 40-55 C, guard pauzowałby bez przerwy",
    "very conservative - a quiet, cool Mac, but long jobs will crawl":
        "bardzo ostrożnie - cichy, chłodny Mac, ale długie zadania będą się wlekły",
    "conservative - good for a fanless Mac (Air, 12-inch)":
        "ostrożnie - dobre dla Maca bez wentylatorów (Air, 12-cal)",
    "recommended - well below Apple's own throttling point (~100-108 C)":
        "zalecane - wyraźnie poniżej progu, na którym macOS sam dławi (~100-108 C)",
    "aggressive - close to the temperature at which macOS throttles by itself":
        "agresywnie - blisko temperatury, w której macOS sam zaczyna dławić",
    "Notifications": "Powiadomienia",
    "Watch only, never touch processes (dry run)": "Tylko obserwuj, nie ruszaj procesów (dry run)",
    "Language: Polish": "Język: polski",
    "resume at %.0f C, terminate at %.0f C": "wznowienie przy %.0f C, ubicie przy %.0f C",
    "no fans (fanless Mac)": "brak wentylatorów (Mac bez wentylatorów)",
    "What does watch-only mode do?": "Co daje tryb „tylko obserwuj”?",
    "Report a problem (GitHub)...": "Zgłoś problem lub pomysł (GitHub)...",
    "Write to the author...": "Napisz do autora...",
    "Watch only (dry run)": "Tylko obserwuj (dry run)",
    """
With this on, thermal-guard measures everything and writes to its log exactly what it WOULD do \
- "would pause Python (595% CPU)" - but sends no signal and never touches a single process.

Use it to see whether the thresholds suit your machine before you let the tool freeze real work. \
Open "Show the guard log" after a heavy job and you will know if it would have interfered too \
eagerly, or not soon enough.

Remember to switch it off afterwards: in this mode nothing protects the Mac.
""": """
Przy włączonym trybie thermal-guard mierzy wszystko i zapisuje w logu dokładnie to, co ZROBIŁBY \
- „pauza Python (595% CPU)” - ale nie wysyła żadnego sygnału i nie rusza ani jednego procesu.

Służy do sprawdzenia, czy progi pasują do Twojej maszyny, zanim pozwolisz narzędziu zamrażać \
realną pracę. Po ciężkim zadaniu otwórz „Pokaż log guarda” i zobaczysz, czy wtrącałby się za \
gorliwie, czy odwrotnie - za późno.

Pamiętaj potem wyłączyć: w tym trybie nic nie chroni Maca.
""",
]

func T(_ s: String) -> String { lang == "pl" ? (PL[s] ?? s) : s }

// MARK: - icons

/// Ikony na pasku to SF Symbols, nie emoji. Powody sa praktyczne: emoji maja wlasny, staly kolor
/// (wiec w ciemnym motywie odcinaja sie jak naklejki), roznia sie szerokoscia miedzy wersjami
/// systemu i psuja rownanie tekstu. Symbol szablonowy przyjmuje kolor paska i wyglada jak czesc
/// systemu. Gdy symbol nie istnieje na danym macOS, wracamy do krotkiego napisu.
func icon(_ name: String, fallback: String, size: CGFloat = 12) -> NSAttributedString {
    guard let raw = NSImage(systemSymbolName: name, accessibilityDescription: nil) else {
        return NSAttributedString(string: fallback)
    }
    let cfg = NSImage.SymbolConfiguration(pointSize: size, weight: .regular)
    let img = raw.withSymbolConfiguration(cfg) ?? raw
    img.isTemplate = true
    let att = NSTextAttachment()
    att.image = img
    att.bounds = CGRect(x: 0, y: -2, width: img.size.width, height: img.size.height)
    return NSAttributedString(attachment: att)
}

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

// MARK: - guard configuration (thresholds live in config.json, the daemon re-reads it every cycle)

/// Odczyt i zapis config.json guarda. Zawsze scalamy z istniejaca trescia — plik nalezy do
/// demona i zawiera znacznie wiecej niz to, co pokazuje pasek.
enum GuardCfg {
    static func all() -> [String: Any] {
        guard let d = FileManager.default.contents(atPath: configPath),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        return j
    }

    static func double(_ key: String, _ fallback: Double) -> Double {
        (all()[key] as? Double) ?? Double((all()[key] as? Int) ?? 0).nonZero ?? fallback
    }

    static func bool(_ key: String, _ fallback: Bool) -> Bool { (all()[key] as? Bool) ?? fallback }
    static func string(_ key: String, _ fallback: String) -> String { (all()[key] as? String) ?? fallback }

    static func set(_ values: [String: Any]) {
        var j = all()
        for (k, v) in values { j[k] = v }
        if let d = try? JSONSerialization.data(withJSONObject: j, options: [.prettyPrinted, .sortedKeys]) {
            try? d.write(to: URL(fileURLWithPath: configPath))
        }
    }
}

extension Double { var nonZero: Double? { self == 0 ? nil : self } }

/// Ostrzezenie dobrane do wartosci suwaka. Sens: uzytkownik ma zobaczyc konsekwencje ZANIM
/// ustawi absurd. Najczestszy blad to przenoszenie progu baterii (45 C) na chip — przy 45 C
/// bezpiecznik pauzowalby wszystko bez przerwy, bo bezczynny chip ma juz 40-55 C.
/// Drugi element pary to nazwa SF Symbol — zadnych emoji: maja wlasny staly kolor
/// i w menu wygladaja jak naklejki, symbol szablonowy przyjmuje kolor tekstu.
func thresholdWarning(_ v: Double) -> (String, String) {
    if v < 60 { return (T("TOO LOW - an idle M-series chip already sits at 40-55 C, the guard would pause constantly"), "nosign") }
    if v < 70 { return (T("very conservative - a quiet, cool Mac, but long jobs will crawl"), "exclamationmark.triangle") }
    if v < 80 { return (T("conservative - good for a fanless Mac (Air, 12-inch)"), "lightbulb") }
    if v <= 92 { return (T("recommended - well below Apple's own throttling point (~100-108 C)"), "checkmark.circle") }
    return (T("aggressive - close to the temperature at which macOS throttles by itself"), "exclamationmark.triangle")
}

/// Wiersz menu z suwakiem. NSMenuItem.view pozwala wstawic dowolny widok, wiec suwak
/// z opisem siedzi wprost w menu, bez osobnego okna preferencji.
///
/// Trzy rzeczy, ktore musialy byc poprawione po pierwszej wersji: opis nie moze byc obcinany
/// (dlatego zawija sie na dwie linie), kolor musi byc czytelny na tle menu (dlatego tekst jest
/// w labelColor, a nasilenie ostrzezenia nosi symbol, nie kolor), a linia z wartosciami
/// pochodnymi musi odswiezac sie W TRAKCIE przesuwania — wczesniej pokazywala stan z chwili
/// otwarcia menu, wiec przy suwaku na 65 C nadal twierdzila "wznowienie przy 76 C".
final class SliderRow: NSView {
    let slider = NSSlider()
    private let value = NSTextField(labelWithString: "")
    private let note = NSTextField(labelWithString: "")
    private let derived = NSTextField(labelWithString: "")
    private let onChange: (Double) -> Void
    private let unit: String
    private let describe: (Double) -> (String, String)
    private let derive: ((Double) -> String)?

    init(title: String, min: Double, max: Double, current: Double, unit: String,
         describe: @escaping (Double) -> (String, String),
         derive: ((Double) -> String)? = nil,
         onChange: @escaping (Double) -> Void) {
        self.onChange = onChange
        self.unit = unit
        self.describe = describe
        self.derive = derive
        let height: CGFloat = derive == nil ? 82 : 100
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: height))

        var y = height - 26

        let label = NSTextField(labelWithString: title)
        label.font = .menuFont(ofSize: 13)
        label.textColor = .labelColor
        label.frame = NSRect(x: 16, y: y, width: 250, height: 18)
        addSubview(label)

        value.font = .monospacedDigitSystemFont(ofSize: 13, weight: .bold)
        value.alignment = .right
        value.textColor = .labelColor
        value.frame = NSRect(x: 270, y: y, width: 114, height: 18)
        addSubview(value)

        y -= 26
        slider.minValue = min
        slider.maxValue = max
        slider.doubleValue = current
        slider.isContinuous = true
        slider.numberOfTickMarks = Int((max - min) / 5) + 1
        slider.allowsTickMarkValuesOnly = true
        slider.target = self
        slider.action = #selector(moved)
        slider.frame = NSRect(x: 16, y: y, width: 368, height: 20)
        addSubview(slider)

        y -= 32
        note.font = .systemFont(ofSize: 11)
        note.textColor = .labelColor
        note.maximumNumberOfLines = 2
        note.lineBreakMode = .byWordWrapping
        note.cell?.wraps = true
        note.cell?.isScrollable = false
        note.frame = NSRect(x: 16, y: y, width: 368, height: 30)
        addSubview(note)

        if derive != nil {
            y -= 20
            derived.font = .monospacedDigitSystemFont(ofSize: 11, weight: .regular)
            derived.textColor = .secondaryLabelColor
            derived.frame = NSRect(x: 16, y: y, width: 368, height: 16)
            addSubview(derived)
        }

        render()
    }

    required init?(coder: NSCoder) { fatalError() }

    private func render() {
        value.stringValue = String(format: "%.0f %@", slider.doubleValue, unit)
        let (text, mark) = describe(slider.doubleValue)
        let out = NSMutableAttributedString()
        if !mark.isEmpty {
            out.append(icon(mark, fallback: "", size: 11))
            out.append(NSAttributedString(string: " "))
        }
        out.append(NSAttributedString(string: text))
        out.addAttributes([.font: NSFont.systemFont(ofSize: 11),
                           .foregroundColor: NSColor.labelColor],
                          range: NSRange(location: 0, length: out.length))
        note.attributedStringValue = out
        if let d = derive { derived.stringValue = d(slider.doubleValue) }
    }

    @objc private func moved() {
        render()
        onChange(slider.doubleValue)
    }
}

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
        // macOS domyslnie wygasza pozycje menu bez akcji — a u nas wiekszosc wierszy to
        // informacje, nie polecenia. Bez tej flagi caly odczyt byl szary i nieczytelny.
        menu.autoenablesItems = false
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
        let bold = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        guard let s = readSnap() else {
            let out = NSMutableAttributedString()
            out.append(icon("thermometer.medium", fallback: "T"))
            out.append(NSAttributedString(string: " —"))
            out.addAttributes([.foregroundColor: NSColor.secondaryLabelColor, .font: bold],
                              range: NSRange(location: 0, length: out.length))
            item.button?.attributedTitle = out
            return
        }

        let out = NSMutableAttributedString()
        func text(_ t: String) { out.append(NSAttributedString(string: t)) }
        func gap() { if out.length > 0 { text(" ") } }

        out.append(icon("thermometer.medium", fallback: "T"))
        var temps: [String] = []
        if prefs.enabled(.chip) { temps.append(s.chip.map { String(format: "%.0f°", $0) } ?? "—") }
        if prefs.enabled(.gpu), let g = s.gpu { temps.append(String(format: "%.0f°", g)) }
        if prefs.enabled(.battery), let b = s.batt { temps.append(String(format: "%.0f°", b)) }
        if !temps.isEmpty { text(" " + temps.joined(separator: "/")) }

        if prefs.enabled(.fans), let f = s.fans.max() {
            gap()
            if f == 0 && (s.chip ?? 0) >= 70 {
                out.append(icon("exclamationmark.triangle.fill", fallback: "!"))
                text(" 0")
            } else {
                out.append(icon("fan", fallback: "fan"))
                text(" " + (f >= 1000 ? String(format: "%.1fk", Double(f) / 1000.0) : "\(f)"))
            }
        }
        if prefs.enabled(.watts), let w = s.watts, w >= 1 {
            gap(); out.append(icon("bolt.fill", fallback: "W")); text(String(format: " %.0fW", w))
        }
        if prefs.enabled(.ram), let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            gap(); out.append(icon("memorychip", fallback: "RAM"))
            text(String(format: " %.0f%%", 100 * u / t))
            // swap w uzyciu to mocniejszy sygnal presji pamieci niz sam procent
            if (s.swap ?? 0) > 0.1 { out.append(icon("arrow.down.circle", fallback: "!")) }
        }
        if prefs.enabled(.disk), let p = s.diskPct {
            gap(); out.append(icon("internaldrive", fallback: "SSD")); text(" \(p)%")
        }
        if prefs.enabled(.throttle), s.cpuLimit < 100 {
            gap(); out.append(icon("tortoise.fill", fallback: "slow"))
        }
        if prefs.enabled(.paused), !s.paused.isEmpty {
            gap(); out.append(icon("pause.circle.fill", fallback: "||"))
        }

        out.addAttributes([.foregroundColor: tint(s), .font: bold],
                          range: NSRange(location: 0, length: out.length))
        item.button?.attributedTitle = out

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

        if s.stale { row(T("!") + " " + String(format: T("data is stale (%@) - the guard may have died"), s.stamp)) }
        if let c = s.lastCrash { row(String(format: T("the Mac shut down without warning: %@"), c)) }

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
                row(String(format: T("rising %.1f C/min - about %.0f min to pause"), t, e))
            } else {
                row(String(format: T("rising %.1f C/min"), t))
            }
        }

        m.addItem(.separator())
        if !s.jobs.isEmpty {
            row(T("Supervised jobs (safe-run):"))
            for j in s.jobs { row("   - \(j.name) — \(j.minutes) min") }
        }
        if let p = s.topProc, let c = s.topCPU { row(String(format: T("Top CPU:  %@ (%d%%)"), p, c)) }
        if !s.paused.isEmpty {
            row(String(format: T("Paused: %@"), s.paused.joined(separator: ", "))
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
            m.addItem(withTitle: T("Resume paused jobs"),
                      action: #selector(resume), keyEquivalent: "").target = self
        } else {
            m.addItem(withTitle: T("Freeze all heavy jobs now"),
                      action: #selector(freeze), keyEquivalent: "").target = self
        }

        // checkboxes deciding what appears in the bar; state kept in heatbar.json
        let showItem = NSMenuItem(title: T("Show in the bar"), action: nil, keyEquivalent: "")
        let sub = NSMenu()
        sub.autoenablesItems = false
        for (i, it) in Item.allCases.enumerated() {
            let mi = NSMenuItem(title: it.label, action: #selector(toggleItem(_:)), keyEquivalent: "")
            mi.target = self
            mi.tag = i
            mi.state = prefs.enabled(it) ? .on : .off
            sub.addItem(mi)
        }
        showItem.submenu = sub
        m.addItem(showItem)

        // panel ustawien: progi suwakiem + przelaczniki. Demon czyta config.json w kazdym
        // przebiegu, wiec zmiana dziala od razu, bez restartu czegokolwiek.
        let setItem = NSMenuItem(title: T("Settings"), action: nil, keyEquivalent: "")
        let ss = NSMenu()
        ss.autoenablesItems = false

        let pauseNow = GuardCfg.double("soc_pause_c", 85)
        let chipRow = NSMenuItem()
        chipRow.view = SliderRow(
            title: T("Chip pause threshold"), min: 55, max: 100, current: pauseNow, unit: "°C",
            describe: thresholdWarning,
            derive: { v in String(format: T("resume at %.0f C, terminate at %.0f C"),
                                  v - 9, Swift.min(v + 5, 100)) }) { v in
            // pochodne trzymamy spojne: histereza 9 C w dol, ubicie 5 C w gore (nie wyzej niz 100)
            GuardCfg.set(["soc_pause_c": v,
                          "soc_resume_c": v - 9,
                          "soc_kill_c": Swift.min(v + 5, 100)])
        }
        ss.addItem(chipRow)
        ss.addItem(.separator())

        let battRow = NSMenuItem()
        battRow.view = SliderRow(title: T("Battery gate"), min: 5, max: 50,
                                 current: GuardCfg.double("batt_pct_pause", 10), unit: "%",
                                 describe: { _ in (T("pause below this charge when unplugged"), "") }) { v in
            GuardCfg.set(["batt_pct_pause": Int(v), "batt_pct_resume": Int(v) + 15])
        }
        ss.addItem(battRow)
        ss.addItem(.separator())

        let notif = NSMenuItem(title: T("Notifications"), action: #selector(toggleNotify), keyEquivalent: "")
        notif.target = self
        notif.state = GuardCfg.bool("notify", true) ? .on : .off
        ss.addItem(notif)

        let dry = NSMenuItem(title: T("Watch only, never touch processes (dry run)"),
                             action: #selector(toggleDry), keyEquivalent: "")
        dry.target = self
        dry.state = GuardCfg.bool("dry_run", false) ? .on : .off
        ss.addItem(dry)

        let help = NSMenuItem(title: T("What does watch-only mode do?"), action: #selector(explainDry), keyEquivalent: "")
        help.target = self
        ss.addItem(help)
        ss.addItem(.separator())

        let pl = NSMenuItem(title: T("Language: Polish"), action: #selector(toggleLang), keyEquivalent: "")
        pl.target = self
        pl.state = GuardCfg.string("lang", "en").hasPrefix("pl") ? .on : .off
        ss.addItem(pl)

        setItem.submenu = ss
        m.addItem(setItem)

        m.addItem(withTitle: T("Export report for a repair shop..."), action: #selector(report), keyEquivalent: "").target = self
        m.addItem(withTitle: T("Show the guard log"), action: #selector(openLog), keyEquivalent: "").target = self
        m.addItem(.separator())
        m.addItem(withTitle: T("Report a problem (GitHub)..."), action: #selector(openIssues), keyEquivalent: "").target = self
        m.addItem(withTitle: T("Write to the author..."), action: #selector(mailAuthor), keyEquivalent: "").target = self
        m.addItem(.separator())

        // nazwa, wersja i sygnatura autora — pozycja nieaktywna, sama informacja
        let sig = NSMenuItem(title: SIGNATURE, action: nil, keyEquivalent: "")
        sig.isEnabled = false
        m.addItem(sig)
        m.addItem(withTitle: T("Quit heatbar"), action: #selector(quit), keyEquivalent: "q").target = self
    }

    /// Tryb "tylko obserwuj" bywa niezrozumialy, a to najwazniejsza opcja dla kogos, kto boi sie
    /// oddac narzedziu wladze nad swoimi procesami — wiec tlumaczymy go wprost.
    @objc func explainDry() {
        let a = NSAlert()
        a.messageText = T("Watch only (dry run)")
        a.informativeText = T("""
With this on, thermal-guard measures everything and writes to its log exactly what it WOULD do - "would pause Python (595% CPU)" - but sends no signal and never touches a single process.

Use it to see whether the thresholds suit your machine before you let the tool freeze real work. Open "Show the guard log" after a heavy job and you will know if it would have interfered too eagerly, or not soon enough.

Remember to switch it off afterwards: in this mode nothing protects the Mac.
""")
        a.alertStyle = .informational
        a.addButton(withTitle: "OK")
        a.runModal()
    }

    @objc func toggleNotify() { GuardCfg.set(["notify": !GuardCfg.bool("notify", true)]) }
    @objc func toggleDry() { GuardCfg.set(["dry_run": !GuardCfg.bool("dry_run", false)]) }

    /// Zmiana jezyka wymaga restartu paska (katalog jest wczytywany raz, przy starcie).
    /// launchd podnosi go z powrotem, bo wyjscie z bledem liczy sie jako awaria.
    @objc func toggleLang() {
        let pl = GuardCfg.string("lang", "en").hasPrefix("pl")
        GuardCfg.set(["lang": pl ? "en" : "pl"])
        exit(1)
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

    @objc func openIssues() {
        NSWorkspace.shared.open(URL(string: "https://github.com/pawelkwaczynski/thermal-guard/issues")!)
    }

    @objc func mailAuthor() {
        NSWorkspace.shared.open(URL(string: "mailto:kwaczynski.pawel@gmail.com?subject=thermal-guard%20v\(VERSION)")!)
    }
    @objc func quit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon, no window
let bar = Bar()
app.run()
