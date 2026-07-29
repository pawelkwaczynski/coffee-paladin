// soctemp.swift — temperatura chipa (SoC) na Apple Silicon BEZ sudo.
//
// macOS nie daje temperatury rdzeni zwykłemu użytkownikowi przez żadne publiczne API,
// a `powermetrics` wymaga hasła. Sensory SMC są jednak widoczne przez IOHIDEventSystem
// (ta sama droga, z której korzystają macmon/asitop) — funkcje są prywatne, więc
// wyciągamy je z IOKit przez dlsym zamiast linkować.
//
// Wyjście (jedna linia, do parsowania):
//   soc=48.3 cpu=47.1 gpu=44.0 n=12
// albo, gdy sensory są niedostępne:
//   soc=- cpu=- gpu=- n=0
//
// Flagi:  --json      wynik jako JSON
//         --list      wypisz wszystkie znalezione sensory z wartościami (diagnostyka)

import Foundation

// MARK: - prywatne API IOKit wyciągane dynamicznie

typealias ClientRef = UnsafeMutableRawPointer
typealias ServiceRef = UnsafeMutableRawPointer
typealias EventRef = UnsafeMutableRawPointer

typealias FnCreate = @convention(c) (CFAllocator?) -> ClientRef?
typealias FnSetMatching = @convention(c) (ClientRef, CFDictionary) -> Void
typealias FnCopyServices = @convention(c) (ClientRef) -> CFArray?
typealias FnCopyProperty = @convention(c) (ServiceRef, CFString) -> CFTypeRef?
typealias FnCopyEvent = @convention(c) (ServiceRef, Int64, Int32, Int64) -> EventRef?
typealias FnGetFloat = @convention(c) (EventRef, Int64) -> Double

// kIOHIDEventTypeTemperature = 15; pole zdarzenia = typ << 16
let kTemperatureEventType: Int64 = 15
let kTemperatureField: Int64 = 15 << 16

// strona/uzycie HID dla sensorow termicznych Apple
let kAppleVendorPage = 0xff00
let kTemperatureUsage = 0x0005

struct IOHID {
    let create: FnCreate
    let setMatching: FnSetMatching
    let copyServices: FnCopyServices
    let copyProperty: FnCopyProperty
    let copyEvent: FnCopyEvent
    let getFloat: FnGetFloat

    init?() {
        guard let h = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_NOW) else { return nil }
        func sym<T>(_ name: String) -> T? {
            guard let p = dlsym(h, name) else { return nil }
            return unsafeBitCast(p, to: T.self)
        }
        guard let a: FnCreate = sym("IOHIDEventSystemClientCreate"),
              let b: FnSetMatching = sym("IOHIDEventSystemClientSetMatching"),
              let c: FnCopyServices = sym("IOHIDEventSystemClientCopyServices"),
              let d: FnCopyProperty = sym("IOHIDServiceClientCopyProperty"),
              let e: FnCopyEvent = sym("IOHIDServiceClientCopyEvent"),
              let f: FnGetFloat = sym("IOHIDEventGetFloatValue") else { return nil }
        create = a; setMatching = b; copyServices = c
        copyProperty = d; copyEvent = e; getFloat = f
    }
}

// MARK: - odczyt

struct Reading { let name: String; let value: Double }

func readSensors() -> [Reading] {
    guard let api = IOHID(), let client = api.create(kCFAllocatorDefault) else { return [] }
    let matching: [String: Int] = [
        "PrimaryUsagePage": kAppleVendorPage,
        "PrimaryUsage": kTemperatureUsage,
    ]
    api.setMatching(client, matching as CFDictionary)
    guard let services = api.copyServices(client) as? [ServiceRef] else { return [] }

    var out: [Reading] = []
    for svc in services {
        guard let raw = api.copyProperty(svc, "Product" as CFString) else { continue }
        let name = (raw as! CFString) as String
        guard let ev = api.copyEvent(svc, kTemperatureEventType, 0, 0) else { continue }
        let v = api.getFloat(ev, kTemperatureField)
        // odsiewamy sensory odlaczone (0) i ewidentne smieci
        if v > 1.0 && v < 150.0 { out.append(Reading(name: name, value: v)) }
    }
    return out
}

// MARK: - grupowanie

/// Sensory na M-serii nazywaja sie np. "pACC MTR Temp Sensor0", "eACC MTR Temp Sensor1",
/// "GPU MTR Temp Sensor2", "SOC MTR Temp Sensor3", "ANE MTR Temp Sensor". Bierzemy MAKSIMUM
/// z grupy — nie srednia: przegrzewa sie najgoretszy punkt, a nie punkt przecietny.
func maxWhere(_ rs: [Reading], _ pred: (String) -> Bool) -> Double? {
    let v = rs.filter { pred($0.name.lowercased()) }.map { $0.value }
    return v.isEmpty ? nil : v.max()
}

let args = Set(CommandLine.arguments.dropFirst())
let sensors = readSensors()

if args.contains("--list") {
    if sensors.isEmpty {
        FileHandle.standardError.write("brak sensorów (IOHID niedostępny albo model bez czujników)\n".data(using: .utf8)!)
        exit(1)
    }
    for r in sensors.sorted(by: { $0.value > $1.value }) {
        print(String(format: "%7.2f °C  %@", r.value, r.name))
    }
    exit(0)
}

let cpu = maxWhere(sensors) { $0.contains("pacc") || $0.contains("eacc") || $0.contains("cpu") }
let gpu = maxWhere(sensors) { $0.contains("gpu") }
// "SoC" traktujemy jako najgoretszy punkt calego ukladu — to jest liczba, na ktorej ma
// dzialac bezpiecznik. Gdy brak dedykowanego sensora SOC, bierzemy maksimum ze wszystkich.
let soc = maxWhere(sensors) { $0.contains("soc") } ?? sensors.map { $0.value }.max()

func fmt(_ d: Double?) -> String { d == nil ? "-" : String(format: "%.1f", d!) }

if args.contains("--json") {
    var parts: [String] = []
    parts.append("\"soc\":" + (soc == nil ? "null" : fmt(soc)))
    parts.append("\"cpu\":" + (cpu == nil ? "null" : fmt(cpu)))
    parts.append("\"gpu\":" + (gpu == nil ? "null" : fmt(gpu)))
    parts.append("\"n\":\(sensors.count)")
    print("{" + parts.joined(separator: ",") + "}")
} else {
    print("soc=\(fmt(soc)) cpu=\(fmt(cpu)) gpu=\(fmt(gpu)) n=\(sensors.count)")
}
exit(sensors.isEmpty ? 1 : 0)
