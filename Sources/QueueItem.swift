import Foundation

enum ItemStatus { case waiting, working, done, failed }

final class QueueItem: NSObject {
    let url: URL
    var status: ItemStatus = .waiting

    var displayName: String { url.lastPathComponent }

    init(url: URL) { self.url = url }
}
