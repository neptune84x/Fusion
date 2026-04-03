import AppKit

// MARK: - MainWindowController

final class MainWindowController: NSWindowController, NSWindowDelegate {

    private let prefs = Preferences.shared
    private var items: [QueueItem] = []
    private var activeQueue: [QueueItem] = []

    // UI refs
    private weak var tableView: NSTableView?
    private weak var statusLabel: NSTextField?
    private weak var progressBar: NSProgressIndicator?
    private weak var settingsPanel: SettingsPanel?

    // Toolbar
    private let toolbarController = ToolbarController()

    convenience init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 420),
            styleMask:   [.titled, .closable, .miniaturizable, .resizable],
            backing:     .buffered,
            defer:       false
        )
        window.title = "Fusion"
        window.minSize = NSSize(width: 480, height: 300)
        window.center()
        self.init(window: window)

        window.delegate = self

        // Toolbar
        let toolbar = toolbarController.makeToolbar()
        toolbarController.onStart    = { [weak self] in self?.startProcessing() }
        toolbarController.onSettings = { [weak self] in self?.toggleSettings()  }
        toolbarController.onAdd      = { [weak self] in self?.openFiles()        }
        window.toolbar = toolbar
        window.titleVisibility = .visible

        setupContent(in: window)
        setupMenu()
        setupDragDrop(on: window.contentView!)
    }

    // MARK: - Content Layout

    private func setupContent(in window: NSWindow) {
        guard let contentView = window.contentView else { return }

        // ── Title label "Queue" (left of toolbar area, inside content) ──
        // The window title is "Fusion" in the title bar.
        // We add a bold label inside the content to match Subler's "Queue" label.
        let queueLabel = NSTextField(labelWithString: "Queue")
        queueLabel.font = .boldSystemFont(ofSize: 13)
        queueLabel.textColor = .labelColor
        queueLabel.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(queueLabel)

        // ── Table view ──────────────────────────────────────────────
        let scrollView = NSScrollView()
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true

        let tv = NSTableView()
        tv.dataSource = self
        tv.delegate   = self
        tv.allowsMultipleSelection   = true
        tv.allowsEmptySelection      = true
        tv.usesAlternatingRowBackgroundColors = true
        tv.rowHeight = 24
        tv.headerView = nil
        tv.selectionHighlightStyle  = .regular
        tv.intercellSpacing         = NSSize(width: 0, height: 0)

        let col = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("file"))
        col.isEditable = false
        tv.addTableColumn(col)

        scrollView.documentView = tv
        contentView.addSubview(scrollView)
        self.tableView = tv

        // Context menu
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Remove Selected",
                                action: #selector(removeSelected), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Clear Completed",
                                action: #selector(clearCompleted), keyEquivalent: ""))
        tv.menu = menu

        // ── Footer ──────────────────────────────────────────────────
        let footer = NSView()
        footer.translatesAutoresizingMaskIntoConstraints = false
        footer.wantsLayer = true
        footer.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor

        let separator = NSBox()
        separator.translatesAutoresizingMaskIntoConstraints = false
        separator.boxType = .separator
        footer.addSubview(separator)

        let statusLbl = NSTextField(labelWithString: "0 items in queue.")
        statusLbl.translatesAutoresizingMaskIntoConstraints = false
        statusLbl.font = .systemFont(ofSize: 11)
        statusLbl.textColor = .secondaryLabelColor
        footer.addSubview(statusLbl)
        self.statusLabel = statusLbl

        let progress = NSProgressIndicator()
        progress.translatesAutoresizingMaskIntoConstraints = false
        progress.style = .bar
        progress.isIndeterminate = false
        progress.minValue = 0
        progress.maxValue = 100
        progress.doubleValue = 0
        footer.addSubview(progress)
        self.progressBar = progress

        contentView.addSubview(footer)

        // ── Constraints ─────────────────────────────────────────────
        NSLayoutConstraint.activate([
            // Queue label
            queueLabel.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 12),
            queueLabel.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 8),

            // Table
            scrollView.topAnchor.constraint(equalTo: queueLabel.bottomAnchor, constant: 4),
            scrollView.leadingAnchor.constraint(equalTo: contentView.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: contentView.trailingAnchor),
            scrollView.bottomAnchor.constraint(equalTo: footer.topAnchor),

            // Footer
            footer.leadingAnchor.constraint(equalTo: contentView.leadingAnchor),
            footer.trailingAnchor.constraint(equalTo: contentView.trailingAnchor),
            footer.bottomAnchor.constraint(equalTo: contentView.bottomAnchor),
            footer.heightAnchor.constraint(equalToConstant: 28),

            // Footer separator
            separator.leadingAnchor.constraint(equalTo: footer.leadingAnchor),
            separator.trailingAnchor.constraint(equalTo: footer.trailingAnchor),
            separator.topAnchor.constraint(equalTo: footer.topAnchor),

            // Status label
            statusLbl.leadingAnchor.constraint(equalTo: footer.leadingAnchor, constant: 10),
            statusLbl.centerYAnchor.constraint(equalTo: footer.centerYAnchor, constant: 2),

            // Progress
            progress.trailingAnchor.constraint(equalTo: footer.trailingAnchor, constant: -10),
            progress.centerYAnchor.constraint(equalTo: footer.centerYAnchor, constant: 2),
            progress.widthAnchor.constraint(equalToConstant: 130),
        ])
    }

    private func setupMenu() {
        let mb = NSApp.mainMenu ?? NSMenu()
        NSApp.mainMenu = mb

        // File menu
        let fileItem = NSMenuItem()
        let fileMenu = NSMenu(title: "File")
        fileItem.submenu = fileMenu

        let addItem = NSMenuItem(title: "Add to Queue…",
                                 action: #selector(openFiles),
                                 keyEquivalent: "o")
        addItem.target = self
        fileMenu.addItem(addItem)
        fileMenu.addItem(.separator())

        let removeItem = NSMenuItem(title: "Remove Selected",
                                    action: #selector(removeSelected),
                                    keyEquivalent: "")
        removeItem.target = self
        fileMenu.addItem(removeItem)

        let clearItem = NSMenuItem(title: "Clear Completed",
                                   action: #selector(clearCompleted),
                                   keyEquivalent: "")
        clearItem.target = self
        fileMenu.addItem(clearItem)

        if mb.item(withTitle: "File") == nil {
            mb.addItem(fileItem)
        }

        // Queue menu
        let queueMenuItem = NSMenuItem()
        let queueMenu = NSMenu(title: "Queue")
        queueMenuItem.submenu = queueMenu

        let startItem = NSMenuItem(title: "Start",
                                   action: #selector(startProcessing),
                                   keyEquivalent: "\r")
        startItem.target = self
        queueMenu.addItem(startItem)

        if mb.item(withTitle: "Queue") == nil {
            mb.addItem(queueMenuItem)
        }
    }

    private func setupDragDrop(on view: NSView) {
        view.registerForDraggedTypes([.fileURL])
    }

    // MARK: - Drag & Drop on window content

    override func windowDidLoad() {
        super.windowDidLoad()
        window?.contentView?.registerForDraggedTypes([.fileURL])
    }

    // MARK: - Actions

    @objc func openFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseFiles          = true
        panel.canChooseDirectories    = false
        panel.allowedContentTypes     = []   // all files
        panel.message = "Select video files to add to queue"
        panel.beginSheetModal(for: window!) { [weak self] response in
            guard response == .OK else { return }
            self?.addURLs(panel.urls)
        }
    }

    func addURLs(_ urls: [URL]) {
        let videoExts = Set(["mkv","mp4","avi","mov","ts","m2ts","m4v","webm"])
        let filtered  = urls.filter { videoExts.contains($0.pathExtension.lowercased()) }
        guard !filtered.isEmpty else { return }
        for url in filtered {
            items.append(QueueItem(url: url))
        }
        tableView?.reloadData()
        updateStatus()
    }

    @objc func removeSelected() {
        guard let tv = tableView else { return }
        let indices = tv.selectedRowIndexes
        items.remove(atOffsets: IndexSet(indices))
        tv.reloadData()
        updateStatus()
    }

    @objc func clearCompleted() {
        items.removeAll { $0.status == .done }
        tableView?.reloadData()
        updateStatus()
    }

    @objc func startProcessing() {
        activeQueue = items.filter { $0.status == .waiting }
        guard !activeQueue.isEmpty else { return }
        progressBar?.doubleValue = 0
        processNext()
    }

    private func processNext() {
        guard !activeQueue.isEmpty else {
            statusLabel?.stringValue = "Completed."
            return
        }
        let item = activeQueue.removeFirst()
        item.status = .working
        tableView?.reloadData()

        ConversionEngine.process(item: item, prefs: prefs) { [weak self] in
            guard let self = self else { return }
            item.status = .done
            self.tableView?.reloadData()
            let done  = Double(self.items.filter { $0.status == .done  }.count)
            let total = Double(self.items.count)
            if total > 0 { self.progressBar?.doubleValue = done / total * 100 }
            self.processNext()
        }
    }

    // MARK: - Settings

    @objc func toggleSettings() {
        if let panel = settingsPanel, panel.isVisible {
            panel.close()
            settingsPanel = nil
            return
        }
        let panel = SettingsPanel(prefs: prefs)
        panel.parentWindow = window
        // Position below toolbar
        if let window = window {
            let winFrame  = window.frame
            let panelSize = panel.frame.size
            let x = winFrame.maxX - panelSize.width - 10
            let y = winFrame.maxY - 70 - panelSize.height
            panel.setFrameOrigin(NSPoint(x: x, y: y))
        }
        panel.makeKeyAndOrderFront(nil)
        settingsPanel = panel
    }

    // MARK: - Status

    private func updateStatus() {
        let n = items.count
        statusLabel?.stringValue = n == 1 ? "1 item in queue." : "\(n) items in queue."
    }

    // MARK: - NSWindowDelegate

    func windowDidBecomeKey(_ notification: Notification) {}
}

// MARK: - NSTableViewDataSource

extension MainWindowController: NSTableViewDataSource {
    func numberOfRows(in tableView: NSTableView) -> Int { items.count }
}

// MARK: - NSTableViewDelegate

extension MainWindowController: NSTableViewDelegate {

    func tableView(_ tableView: NSTableView,
                   viewFor tableColumn: NSTableColumn?,
                   row: Int) -> NSView? {
        let item = items[row]
        let id   = NSUserInterfaceItemIdentifier("cell")

        var cell = tableView.makeView(withIdentifier: id, owner: nil) as? QueueCellView
        if cell == nil {
            cell = QueueCellView()
            cell?.identifier = id
        }
        cell?.configure(with: item)
        return cell
    }

    func tableView(_ tableView: NSTableView, heightOfRow row: Int) -> CGFloat { 24 }
}

// MARK: - Drag & Drop on NSWindow content

extension MainWindowController: NSDraggingDestination {
    func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation { .copy }
    func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let pb   = sender.draggingPasteboard
        let urls = pb.readObjects(forClasses: [NSURL.self]) as? [URL] ?? []
        addURLs(urls)
        return true
    }
}

// MARK: - ToolbarController

final class ToolbarController: NSObject, NSToolbarDelegate {
    var onStart:    (() -> Void)?
    var onSettings: (() -> Void)?
    var onAdd:      (() -> Void)?

    func makeToolbar() -> NSToolbar {
        let tb = NSToolbar(identifier: "FusionToolbar")
        tb.delegate           = self
        tb.displayMode        = .iconAndLabel
        tb.allowsUserCustomization = false
        return tb
    }

    func toolbar(_ toolbar: NSToolbar,
                 itemForItemIdentifier id: NSToolbarItem.Identifier,
                 willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        switch id.rawValue {
        case "start":
            return makeItem(id: id, label: "Start",
                            symbol: "play.fill", action: #selector(didStart))
        case "settings":
            return makeItem(id: id, label: "Settings",
                            symbol: "gearshape.fill", action: #selector(didSettings))
        case "add":
            return makeItem(id: id, label: "Add Item",
                            symbol: "plus.rectangle.on.folder.fill", action: #selector(didAdd))
        default: return nil
        }
    }

    private func makeItem(id: NSToolbarItem.Identifier,
                          label: String,
                          symbol: String,
                          action: Selector) -> NSToolbarItem {
        let item        = NSToolbarItem(itemIdentifier: id)
        item.label      = label
        item.image      = NSImage(systemSymbolName: symbol,
                                  accessibilityDescription: label)
        item.isBordered = true
        item.target     = self
        item.action     = action
        return item
    }

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [.flexibleSpace,
         NSToolbarItem.Identifier("start"),
         NSToolbarItem.Identifier("settings"),
         NSToolbarItem.Identifier("add")]
    }

    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        toolbarDefaultItemIdentifiers(toolbar)
    }

    @objc private func didStart()    { onStart?()    }
    @objc private func didSettings() { onSettings?() }
    @objc private func didAdd()      { onAdd?()      }
}

// MARK: - Queue Cell View

final class QueueCellView: NSTableCellView {
    private let dotView   = NSTextField(labelWithString: "●")
    private let nameField = NSTextField(labelWithString: "")

    override init(frame: NSRect) {
        super.init(frame: frame)

        dotView.font      = .systemFont(ofSize: 8)
        dotView.alignment = .center
        dotView.translatesAutoresizingMaskIntoConstraints = false

        nameField.font    = .systemFont(ofSize: 12)
        nameField.translatesAutoresizingMaskIntoConstraints = false
        nameField.lineBreakMode = .byTruncatingMiddle

        addSubview(dotView)
        addSubview(nameField)

        NSLayoutConstraint.activate([
            dotView.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            dotView.centerYAnchor.constraint(equalTo: centerYAnchor),
            dotView.widthAnchor.constraint(equalToConstant: 14),

            nameField.leadingAnchor.constraint(equalTo: dotView.trailingAnchor, constant: 4),
            nameField.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            nameField.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])
    }

    required init?(coder: NSCoder) { fatalError() }

    func configure(with item: QueueItem) {
        nameField.stringValue = item.displayName
        switch item.status {
        case .waiting: dotView.textColor = NSColor.tertiaryLabelColor
        case .working: dotView.textColor = NSColor.systemOrange
        case .done:    dotView.textColor = NSColor.systemGreen
        case .failed:  dotView.textColor = NSColor.systemRed
        }
    }
}

// MARK: - Settings Panel

final class SettingsPanel: NSPanel {
    private let prefs: Preferences

    init(prefs: Preferences) {
        self.prefs = prefs
        super.init(contentRect: NSRect(x: 0, y: 0, width: 300, height: 200),
                   styleMask:   [.titled, .closable, .utilityWindow],
                   backing:     .buffered,
                   defer:       false)
        self.title              = "Settings"
        self.isFloatingPanel    = true
        self.becomesKeyOnlyIfNeeded = true
        self.hidesOnDeactivate  = true
        self.level              = .floating
        buildUI()
    }

    private func buildUI() {
        guard let cv = contentView else { return }

        let stack = NSStackView()
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.orientation = .vertical
        stack.alignment   = .leading
        stack.spacing     = 10
        cv.addSubview(stack)

        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: cv.topAnchor, constant: 16),
            stack.leadingAnchor.constraint(equalTo: cv.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: cv.trailingAnchor, constant: -16),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: cv.bottomAnchor, constant: -16),
        ])

        // Output Format
        let fmtLabel = NSTextField(labelWithString: "Output Format:")
        fmtLabel.font = .boldSystemFont(ofSize: 12)

        let fmtPop = NSPopUpButton()
        fmtPop.addItems(withTitles: ["mkv", "mp4"])
        fmtPop.selectItem(withTitle: prefs.outputFormat)
        fmtPop.target = self
        fmtPop.action = #selector(formatChanged(_:))

        stack.addArrangedSubview(fmtLabel)
        stack.addArrangedSubview(fmtPop)

        // Convert subtitles to SRT
        let convertCB = NSButton(checkboxWithTitle: "Convert subtitles to SRT",
                                 target: self, action: #selector(convertToggled(_:)))
        convertCB.state = prefs.convertToSRT ? .on : .off
        stack.addArrangedSubview(convertCB)

        // Separator
        let sep = NSBox(); sep.boxType = .separator
        stack.addArrangedSubview(sep)

        // Load external subtitles
        let extCB = NSButton(checkboxWithTitle: "Load external subtitles",
                             target: self, action: #selector(extToggled(_:)))
        extCB.state = prefs.loadExternalSubs ? .on : .off
        stack.addArrangedSubview(extCB)

        // Resize panel to fit content
        let needed = stack.fittingSize
        setContentSize(NSSize(width: 280,
                              height: needed.height + 48))
    }

    @objc private func formatChanged(_ sender: NSPopUpButton) {
        prefs.outputFormat = sender.titleOfSelectedItem ?? "mkv"
    }

    @objc private func convertToggled(_ sender: NSButton) {
        prefs.convertToSRT = sender.state == .on
    }

    @objc private func extToggled(_ sender: NSButton) {
        prefs.loadExternalSubs = sender.state == .on
    }
}
