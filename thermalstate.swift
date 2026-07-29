// thermalstate — wypisuje stan termiczny macOS bez sudo.
// nominal | fair | serious | critical  (NSProcessInfo.thermalState)
import Foundation

let names = ["nominal", "fair", "serious", "critical"]
let raw = ProcessInfo.processInfo.thermalState.rawValue
print(names.indices.contains(raw) ? names[raw] : "unknown")
