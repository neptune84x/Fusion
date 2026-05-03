import AppKit

// MARK: - Colours (matching Python constants exactly)
private let COL_TOOLBAR_BG  = NSColor(hex: "#f5f5f5")
private let COL_TOOLBAR_BOR = NSColor(hex: "#d0d0d0")
private let COL_FOOTER_BG   = NSColor(hex: "#ececec")
private let COL_FOOTER_BOR  = NSColor(hex: "#c8c8c8")
private let COL_ZEBRA_ODD   = NSColor(hex: "#efefef")
private let COL_ZEBRA_EVEN  = NSColor.white
private let COL_SEL_BG      = NSColor(hex: "#1560d4")
private let COL_SEL_TXT     = NSColor.white
private let COL_TXT_PRI     = NSColor(hex: "#1d1d1f")
private let COL_TXT_SEC     = NSColor(hex: "#6e6e73")
private let COL_DOT_WAIT    = NSColor(hex: "#b0b0b8")
private let COL_DOT_WORK    = NSColor(hex: "#ff9500")
private let COL_DOT_DONE    = NSColor(hex: "#30d158")
private let COL_PROG_BG     = NSColor(hex: "#d0d0d0")
private let COL_PROG_FG     = NSColor(hex: "#1560d4")
private let COL_SETTINGS_BG = NSColor(hex: "#f5f5f7")
private let COL_SECT_LINE   = NSColor(hex: "#d8d8dc")

extension NSColor {
    convenience init(hex: String) {
        var h = hex.trimmingCharacters(in: .init(charactersIn: "#"))
        if h.count == 6 { h += "ff" }
        let val = UInt64(h, radix: 16) ?? 0
        self.init(
            red:   CGFloat((val >> 24) & 0xff) / 255,
            green: CGFloat((val >> 16) & 0xff) / 255,
            blue:  CGFloat((val >>  8) & 0xff) / 255,
            alpha: CGFloat( val        & 0xff) / 255
        )
    }
}

// MARK: - MainWindowController

final class MainWindowController: NSWindowController, NSWindowDelegate,
                                   NSToolbarDelegate, NSDraggingDestination {

    // State
    private let prefs = Preferences.shared
    private var items: [QueueItem] = []
    private var workQueue: [QueueItem] = []

    // Views
    private var tableView: FusionTableView!
    private var statusLabel: NSTextField!
    private var progressBar: NSProgressIndicator!
    private var settingsPanel: SettingsFloatingPanel?

    // ─────────────────────────────────────────────────
    convenience init() {
        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 420),
            styleMask:   [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered, defer: false)
        win.title        = "Fusion"
        win.minSize      = NSSize(width: 480, height: 300)
        win.titlebarAppearsTransparent = false
        win.isMovableByWindowBackground = false
        win.center()
        self.init(window: win)
        win.delegate = self

        buildToolbar(for: win)
        buildContent(in:  win)
        buildMenus()

        win.contentView?.registerForDraggedTypes([.fileURL])
        win.contentView?.wantsLayer = true
    }

    // MARK: Toolbar

    private func buildToolbar(for win: NSWindow) {
        let tb = NSToolbar(identifier: "FusionToolbar")
        tb.delegate                 = self
        tb.displayMode              = .iconAndLabel
        tb.allowsUserCustomization  = false
        win.toolbar = tb
    }

    func toolbar(_ tb: NSToolbar,
                 itemForItemIdentifier id: NSToolbarItem.Identifier,
                 willBeInsertedIntoToolbar _: Bool) -> NSToolbarItem? {
        switch id.rawValue {
        case "start":
            return makeToolbarItem(id: id, label: "Start",
                                   symbol: "play.fill",
                                   action: #selector(startProcessing))
        case "settings":
            return makeToolbarItem(id: id, label: "Settings",
                                   symbol: "gearshape.fill",
                                   action: #selector(toggleSettings))
        case "add":
            return makeToolbarItem(id: id, label: "Add Item",
                                   symbol: "plus.rectangle.on.folder.fill",
                                   action: #selector(openFiles))
        default: return nil
        }
    }

    private func makeToolbarItem(id: NSToolbarItem.Identifier,
                                  label: String,
                                  symbol: String,
                                  action: Selector) -> NSToolbarItem {
        let item    = NSToolbarItem(itemIdentifier: id)
        item.label  = label
        item.image  = NSImage(systemSymbolName: symbol,
                              accessibilityDescription: label)
        item.isBordered = true
        item.target = self
        item.action = action
        return item
    }

    func toolbarDefaultItemIdentifiers(_ tb: NSToolbar) -> [NSToolbarItem.Identifier] {
        [.flexibleSpace,
         .init("start"), .init("settings"), .init("add")]
    }
    func toolbarAllowedItemIdentifiers(_ tb: NSToolbar) -> [NSToolbarItem.Identifier] {
        toolbarDefaultItemIdentifiers(tb)
    }

    // MARK: Content layout

    private func buildContent(in win: NSWindow) {
        guard let cv = win.contentView else { return }

        // "Queue" label — bold, top-left (like Python "Queue" title)
        let qLbl = NSTextField(labelWithString: "Queue")
        qLbl.font        = .boldSystemFont(ofSize: 13)
        qLbl.textColor   = COL_TXT_PRI
        qLbl.translatesAutoresizingMaskIntoConstraints = false
        cv.addSubview(qLbl)

        // Zebra table
        tableView = FusionTableView()
        tableView.dataSource = self
        tableView.delegate   = self
        tableView.headerView = nil
        tableView.intercellSpacing   = .zero
        tableView.rowHeight          = 24
        tableView.allowsMultipleSelection  = true
        tableView.allowsEmptySelection     = true
        tableView.usesAlternatingRowBackgroundColors = false  // We paint manually
        tableView.backgroundColor    = .clear
        tableView.selectionHighlightStyle = .regular

        let col = NSTableColumn(identifier: .init("file"))
        col.isEditable = false
        tableView.addTableColumn(col)

        // Right-click menu
        let ctxMenu = NSMenu()
        ctxMenu.addItem(NSMenuItem(title: "Remove Selected",
                                   action: #selector(removeSelected), keyEquivalent: ""))
        ctxMenu.addItem(NSMenuItem(title: "Clear Completed",
                                   action: #selector(clearCompleted), keyEquivalent: ""))
        tableView.menu = ctxMenu

        let scroll = NSScrollView()
        scroll.documentView       = tableView
        scroll.hasVerticalScroller       = true
        scroll.hasHorizontalScroller     = false
        scroll.autohidesScrollers        = true
        scroll.drawsBackground           = false
        scroll.translatesAutoresizingMaskIntoConstraints = false
        cv.addSubview(scroll)

        // Footer
        let footer = NSView()
        footer.wantsLayer = true
        footer.layer?.backgroundColor = COL_FOOTER_BG.cgColor
        footer.translatesAutoresizingMaskIntoConstraints = false
        cv.addSubview(footer)

        let footerSep = NSBox(); footerSep.boxType = .separator
        footerSep.translatesAutoresizingMaskIntoConstraints = false
        footer.addSubview(footerSep)

        statusLabel = NSTextField(labelWithString: "0 items in queue.")
        statusLabel.font      = .systemFont(ofSize: 11)
        statusLabel.textColor = COL_TXT_SEC
        statusLabel.translatesAutoresizingMaskIntoConstraints = false
        footer.addSubview(statusLabel)

        progressBar = NSProgressIndicator()
        progressBar.style           = .bar
        progressBar.isIndeterminate = false
        progressBar.minValue        = 0
        progressBar.maxValue        = 100
        progressBar.doubleValue     = 0
        progressBar.translatesAutoresizingMaskIntoConstraints = false
        progressBar.controlSize     = .small
        footer.addSubview(progressBar)

        // Constraints
        NSLayoutConstraint.activate([
            qLbl.leadingAnchor.constraint(equalTo: cv.leadingAnchor, constant: 12),
            qLbl.topAnchor.constraint(equalTo: cv.topAnchor, constant: 8),

            scroll.topAnchor.constraint(equalTo: qLbl.bottomAnchor, constant: 4),
            scroll.leadingAnchor.constraint(equalTo: cv.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: cv.trailingAnchor),
            scroll.bottomAnchor.constraint(equalTo: footer.topAnchor),

            footer.leadingAnchor.constraint(equalTo: cv.leadingAnchor),
            footer.trailingAnchor.constraint(equalTo: cv.trailingAnchor),
            footer.bottomAnchor.constraint(equalTo: cv.bottomAnchor),
            footer.heightAnchor.constraint(equalToConstant: 24),

            footerSep.leadingAnchor.constraint(equalTo: footer.leadingAnchor),
            footerSep.trailingAnchor.constraint(equalTo: footer.trailingAnchor),
            footerSep.topAnchor.constraint(equalTo: footer.topAnchor),

            statusLabel.leadingAnchor.constraint(equalTo: footer.leadingAnchor, constant: 10),
            statusLabel.centerYAnchor.constraint(equalTo: footer.centerYAnchor, constant: 2),

            progressBar.trailingAnchor.constraint(equalTo: footer.trailingAnchor, constant: -10),
            progressBar.centerYAnchor.constraint(equalTo: footer.centerYAnchor, constant: 2),
            progressBar.widthAnchor.constraint(equalToConstant: 130),
        ])
    }

    // MARK: Menus

    private func buildMenus() {
        let mb = NSApp.mainMenu ?? {
            let m = NSMenu(); NSApp.mainMenu = m; return m
        }()

        // File
        if mb.item(withTitle: "File") == nil {
            let fm = NSMenu(title: "File")
            let fi = NSMenuItem(); fi.submenu = fm
            mb.addItem(fi)

            let add = NSMenuItem(title: "Add to Queue…",
                                 action: #selector(openFiles), keyEquivalent: "o")
            add.target = self; fm.addItem(add)
            fm.addItem(.separator())

            let rem = NSMenuItem(title: "Remove Selected",
                                 action: #selector(removeSelected), keyEquivalent: "")
            rem.target = self; fm.addItem(rem)

            let clr = NSMenuItem(title: "Clear Completed",
                                 action: #selector(clearCompleted), keyEquivalent: "")
            clr.target = self; fm.addItem(clr)
        }

        // Queue
        if mb.item(withTitle: "Queue") == nil {
            let qm = NSMenu(title: "Queue")
            let qi = NSMenuItem(); qi.submenu = qm
            mb.addItem(qi)

            let start = NSMenuItem(title: "Start",
                                   action: #selector(startProcessing),
                                   keyEquivalent: "\r")
            start.target = self; qm.addItem(start)
        }
    }

    // MARK: - Actions

    @objc private func openFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseFiles          = true
        panel.canChooseDirectories    = false
        panel.beginSheetModal(for: window!) { [weak self] r in
            guard r == .OK else { return }
            self?.addURLs(panel.urls)
        }
    }

    func addURLs(_ urls: [URL]) {
        let exts = Set(["mkv","mp4","avi","mov","ts","m2ts","m4v","webm"])
        let valid = urls.filter { exts.contains($0.pathExtension.lowercased()) }
        guard !valid.isEmpty else { return }
        valid.forEach { items.append(QueueItem(url: $0)) }
        tableView.reloadData()
        refreshStatus()
    }

    @objc private func removeSelected() {
        let sel = tableView.selectedRowIndexes
        guard !sel.isEmpty else { return }
        sel.sorted().reversed().forEach { items.remove(at: $0) }
        tableView.reloadData()
        refreshStatus()
    }

    @objc private func clearCompleted() {
        items.removeAll { $0.status == .done }
        tableView.reloadData()
        refreshStatus()
    }

    @objc private func startProcessing() {
        workQueue = items.filter { $0.status == .waiting }
        guard !workQueue.isEmpty else { return }
        progressBar.doubleValue = 0
        processNext()
    }

    private func processNext() {
        guard !workQueue.isEmpty else {
            statusLabel.stringValue = "Completed."
            return
        }
        let item = workQueue.removeFirst()
        item.status = .working
        tableView.reloadData()

        ConversionEngine.process(item: item, prefs: prefs) { [weak self] in
            guard let self = self else { return }
            item.status = .done
            self.tableView.reloadData()
            let done  = Double(self.items.filter { $0.status == .done }.count)
            let total = Double(self.items.count)
            if total > 0 { self.progressBar.doubleValue = done / total * 100 }
            self.processNext()
        }
    }

    @objc private func toggleSettings() {
        if let p = settingsPanel, p.isVisible { p.close(); settingsPanel = nil; return }
        let panel = SettingsFloatingPanel(prefs: prefs)
        if let win = window {
            // Position below toolbar right edge (matching Python behaviour)
            let wf     = win.frame
            let ph     = panel.frame.height
            let pw     = panel.frame.width
            let x      = wf.maxX - pw - 8
            let y      = wf.maxY - 70 - ph
            panel.setFrameOrigin(NSPoint(x: x, y: y))
        }
        panel.makeKeyAndOrderFront(nil)
        settingsPanel = panel
    }

    // MARK: Status

    private func refreshStatus() {
        let n = items.count
        statusLabel.stringValue = n == 1 ? "1 item in queue." : "\(n) items in queue."
    }

    // MARK: Drag & drop (window content)

    func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation { .copy }
    func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation { .copy }
    func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let urls = sender.draggingPasteboard
            .readObjects(forClasses: [NSURL.self], options: nil) as? [URL] ?? []
        addURLs(urls)
        return true
    }

    // MARK: NSWindowDelegate

    func windowShouldClose(_ sender: NSWindow) -> Bool { true }
}

// MARK: - NSTableViewDataSource / Delegate

extension MainWindowController: NSTableViewDataSource, NSTableViewDelegate {

    func numberOfRows(in tv: NSTableView) -> Int { items.count }

    func tableView(_ tv: NSTableView,
                   viewFor col: NSTableColumn?, row: Int) -> NSView? {
        let id  = NSUserInterfaceItemIdentifier("row")
        var cell = tv.makeView(withIdentifier: id, owner: nil) as? RowCellView
        if cell == nil { cell = RowCellView(); cell?.identifier = id }
        cell?.configure(item: items[row], isSelected: tv.selectedRowIndexes.contains(row))
        return cell
    }

    func tableView(_ tv: NSTableView, rowViewForRow row: Int) -> NSTableRowView? {
        FusionRowView(zebra: row % 2 == 1)
    }

    func tableView(_ tv: NSTableView, shouldSelectRow row: Int) -> Bool { true }

    func tableViewSelectionDidChange(_ n: Notification) { tableView.reloadData() }
}

// MARK: - Zebra table view (custom background)

final class FusionTableView: NSTableView {
    override func drawBackground(in clipRect: NSRect) {
        // Painted per-row in FusionRowView
    }
}

// MARK: - Row view (zebra stripes + selection highlight)

final class FusionRowView: NSTableRowView {
    private let isOdd: Bool
    init(zebra odd: Bool) { isOdd = odd; super.init(frame: .zero) }
    required init?(coder: NSCoder) { fatalError() }

    override func drawBackground(in dirtyRect: NSRect) {
        (isOdd ? COL_ZEBRA_ODD : COL_ZEBRA_EVEN).setFill()
        dirtyRect.fill()
    }
    override func drawSelection(in dirtyRect: NSRect) {
        COL_SEL_BG.setFill()
        NSBezierPath(roundedRect: bounds.insetBy(dx: 0, dy: 0),
                     xRadius: 3, yRadius: 3).fill()
    }
    override var isEmphasized: Bool { get { true } set {} }
}

// MARK: - Cell view (dot + name)

final class RowCellView: NSTableCellView {
    private let dot  = NSTextField(labelWithString: "●")
    private let name = NSTextField(labelWithString: "")

    override init(frame: NSRect) {
        super.init(frame: frame)
        dot.font  = .systemFont(ofSize: 7)
        dot.setContentHuggingPriority(.required, for: .horizontal)
        name.font = .systemFont(ofSize: 12)
        name.lineBreakMode = .byTruncatingMiddle

        [dot, name].forEach {
            $0.translatesAutoresizingMaskIntoConstraints = false
            $0.isEditable = false; $0.isBezeled = false
            $0.drawsBackground = false
            addSubview($0)
        }

        NSLayoutConstraint.activate([
            dot.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            dot.centerYAnchor.constraint(equalTo: centerYAnchor),
            dot.widthAnchor.constraint(equalToConstant: 12),

            name.leadingAnchor.constraint(equalTo: dot.trailingAnchor, constant: 5),
            name.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            name.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])
    }
    required init?(coder: NSCoder) { fatalError() }

    func configure(item: QueueItem, isSelected: Bool) {
        name.stringValue = item.displayName
        if isSelected {
            name.textColor = COL_SEL_TXT
            dot.textColor  = NSColor.white.withAlphaComponent(0.8)
        } else {
            name.textColor = COL_TXT_PRI
            dot.textColor  = {
                switch item.status {
                case .waiting: return COL_DOT_WAIT
                case .working: return COL_DOT_WORK
                case .done:    return COL_DOT_DONE
                case .failed:  return NSColor.systemRed
                }
            }()
        }
    }
}

// MARK: - Settings floating panel

final class SettingsFloatingPanel: NSPanel {
    private let prefs: Preferences
    private var convertCheckbox: NSButton!

    init(prefs: Preferences) {
        self.prefs = prefs
        super.init(contentRect: NSRect(x: 0, y: 0, width: 300, height: 10),
                   styleMask:  [.titled, .closable, .nonactivatingPanel],
                   backing: .buffered, defer: false)
        self.title                  = "Settings"
        self.isFloatingPanel        = true
        self.hidesOnDeactivate      = true
        self.level                  = .floating
        self.becomesKeyOnlyIfNeeded = true
        buildUI()
    }

    private func buildUI() {
        guard let cv = contentView else { return }
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment   = .leading
        stack.spacing     = 8
        stack.translatesAutoresizingMaskIntoConstraints = false
        cv.addSubview(stack)

        // Output Format
        let fmtTitle = bold("Output Format:")
        stack.addArrangedSubview(fmtTitle)

        let fmtPop = NSPopUpButton()
        fmtPop.addItems(withTitles: ["mkv", "mp4"])
        fmtPop.selectItem(withTitle: prefs.outputFormat)
        fmtPop.target = self; fmtPop.action = #selector(formatChanged(_:))
        stack.addArrangedSubview(fmtPop)

        // Convert SRT (visible only when mkv selected)
        convertCheckbox = NSButton(checkboxWithTitle: "Convert subtitles to SRT",
                                   target: self, action: #selector(convertChanged(_:)))
        convertCheckbox.state = prefs.convertToSRT ? .on : .off
        convertCheckbox.isHidden = prefs.outputFormat == "mp4"
        stack.addArrangedSubview(convertCheckbox)

        // Separator
        let sep = NSBox(); sep.boxType = .separator
        stack.addArrangedSubview(sep)

        // Load external subs
        let extTitle = bold("Subtitles:")
        stack.addArrangedSubview(extTitle)

        let extCB = NSButton(checkboxWithTitle: "Load external subtitles",
                             target: self, action: #selector(extChanged(_:)))
        extCB.state = prefs.loadExternalSubs ? .on : .off
        stack.addArrangedSubview(extCB)

        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: cv.topAnchor, constant: 14),
            stack.leadingAnchor.constraint(equalTo: cv.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: cv.trailingAnchor, constant: -16),
            stack.bottomAnchor.constraint(equalTo: cv.bottomAnchor, constant: -16),
        ])

        layoutIfNeeded()
        let h = stack.fittingSize.height + 30
        setContentSize(NSSize(width: 280, height: h))
    }

    private func bold(_ text: String) -> NSTextField {
        let lbl = NSTextField(labelWithString: text)
        lbl.font = .boldSystemFont(ofSize: 12)
        return lbl
    }

    @objc private func formatChanged(_ sender: NSPopUpButton) {
        let fmt = sender.titleOfSelectedItem ?? "mkv"
        prefs.outputFormat = fmt
        convertCheckbox.isHidden = fmt == "mp4"
    }

    @objc private func convertChanged(_ sender: NSButton) {
        prefs.convertToSRT = sender.state == .on
    }

    @objc private func extChanged(_ sender: NSButton) {
        prefs.loadExternalSubs = sender.state == .on
    }
}
