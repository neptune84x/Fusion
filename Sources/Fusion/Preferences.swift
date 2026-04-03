import Foundation

final class Preferences {
    static let shared = Preferences()

    var outputFormat: String {
        get { UserDefaults.standard.string(forKey: "outputFormat") ?? "mkv" }
        set { UserDefaults.standard.set(newValue, forKey: "outputFormat") }
    }

    var convertToSRT: Bool {
        get {
            if UserDefaults.standard.object(forKey: "convertToSRT") == nil { return true }
            return UserDefaults.standard.bool(forKey: "convertToSRT")
        }
        set { UserDefaults.standard.set(newValue, forKey: "convertToSRT") }
    }

    var loadExternalSubs: Bool {
        get {
            if UserDefaults.standard.object(forKey: "loadExternalSubs") == nil { return true }
            return UserDefaults.standard.bool(forKey: "loadExternalSubs")
        }
        set { UserDefaults.standard.set(newValue, forKey: "loadExternalSubs") }
    }
}
