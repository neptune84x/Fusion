import Foundation

enum ItemStatus: String {
    case waiting, working, done, failed
}

final class QueueItem {
    let url: URL
    var status: ItemStatus = .waiting
    var displayName: String { url.lastPathComponent }
    init(url: URL) { self.url = url }
}
