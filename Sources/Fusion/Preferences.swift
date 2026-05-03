import Foundation

final class Preferences {
    static let shared = Preferences()
    private init() {}

    var outputFormat: String {
        get { UserDefaults.standard.string(forKey: "outputFormat") ?? "mkv" }
        set { UserDefaults.standard.set(newValue, forKey: "outputFormat") }
    }

    var convertToSRT: Bool {
        get {
            guard UserDefaults.standard.object(forKey: "convertToSRT") != nil else { return true }
            return UserDefaults.standard.bool(forKey: "convertToSRT")
        }
        set { UserDefaults.standard.set(newValue, forKey: "convertToSRT") }
    }

    var loadExternalSubs: Bool {
        get {
            guard UserDefaults.standard.object(forKey: "loadExternalSubs") != nil else { return true }
            return UserDefaults.standard.bool(forKey: "loadExternalSubs")
        }
        set { UserDefaults.standard.set(newValue, forKey: "loadExternalSubs") }
    }
}
