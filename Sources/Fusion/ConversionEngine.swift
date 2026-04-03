import Foundation

// MARK: - Probe models

private struct ProbeStream: Decodable {
    let index: Int
    let codec_type: String?
    let codec_name: String?
    let tags: [String: String]?
}

private struct ProbeChapter: Decodable {
    let id: Int
    let start_time: String
    let end_time: String
    let tags: [String: String]?
}

private struct ProbeResult: Decodable {
    let streams: [ProbeStream]
    let chapters: [ProbeChapter]
}

// MARK: - Internal helpers

private struct SubEntry {
    let path: String
    let lang: String   // 3-letter ISO-639-2
    let codec: String  // "srt" | "ass" | "vtt"
}

private struct FontEntry {
    let path: String
    let filename: String
    let mimetype: String
}

// MARK: - Binary paths

private enum Bin {
    static var ffmpeg:  String { locate("ffmpeg")  }
    static var ffprobe: String { locate("ffprobe") }
    static var mp4box:  String { locate("mp4box")  }

    private static func locate(_ name: String) -> String {
        // Running as .app bundle: binaries in Contents/Resources/
        if let url = Bundle.main.resourceURL {
            let path = url.appendingPathComponent(name).path
            if FileManager.default.isExecutableFile(atPath: path) { return path }
        }
        // Dev fallback
        return name
    }
}

// MARK: - Engine

final class ConversionEngine {

    private static let langMap: [String: String] = [
        "tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger",
        "fr":"fra","es":"spa","it":"ita","pt":"por","ar":"ara"
    ]

    // MARK: Public

    static func process(item: QueueItem,
                        prefs: Preferences,
                        completion: @escaping () -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            convert(item: item, prefs: prefs)
            DispatchQueue.main.async { completion() }
        }
    }

    // MARK: Core

    private static func convert(item: QueueItem, prefs: Preferences) {
        let input      = item.url.path
        let base       = (input as NSString).deletingPathExtension
        let fmt        = prefs.outputFormat          // "mkv" | "mp4"
        let convertSRT = prefs.convertToSRT
        let loadExt    = prefs.loadExternalSubs
        let outFile    = "\(base)_Fusion.\(fmt == "mp4" ? "mp4" : "mkv")"

        // Temp directory (.fusiontemp — hidden by chflags)
        let tmp = base + ".fusiontemp"
        try? FileManager.default.removeItem(atPath: tmp)
        try? FileManager.default.createDirectory(atPath: tmp,
                                                  withIntermediateDirectories: true,
                                                  attributes: nil)
        run("chflags", "hidden", tmp)

        // Probe
        guard let info = probe(input) else {
            try? FileManager.default.removeItem(atPath: tmp)
            return
        }

        let streams      = info.streams
        let chapters     = info.chapters
        let audioStreams  = streams.filter { $0.codec_type == "audio" }
        let subStreams    = streams.filter { $0.codec_type == "subtitle" }
        let attStreams    = streams.filter { $0.codec_type == "attachment" }
        let videoStream  = streams.first  { $0.codec_type == "video" }
        let isHEVC       = videoStream?.codec_name == "hevc"

        // Build subtitle list
        var cleaned: [SubEntry] = []

        for (i, sub) in subStreams.enumerated() {
            let rawLang = sub.tags?["language"] ?? "und"
            let lang3   = langMap[rawLang] ?? rawLang
            let codec   = sub.codec_name ?? ""

            if fmt == "mp4" {
                let srtP = "\(tmp)/int_\(i).srt"
                let vttP = "\(tmp)/int_\(i).vtt"
                run(Bin.ffmpeg, "-y", "-i", input,
                    "-map", "0:\(sub.index)", "-f", "srt", srtP)
                if nonEmpty(srtP) {
                    srtToVtt(srtP, vttP)
                    if nonEmpty(vttP) {
                        cleaned.append(SubEntry(path: vttP, lang: lang3, codec: "vtt"))
                    }
                }
            } else {
                if !convertSRT && (codec == "ass" || codec == "ssa") {
                    let assP = "\(tmp)/int_\(i).ass"
                    run(Bin.ffmpeg, "-y", "-i", input,
                        "-map", "0:\(sub.index)", assP)
                    if nonEmpty(assP) {
                        cleaned.append(SubEntry(path: assP, lang: lang3, codec: "ass"))
                    }
                } else {
                    let srtP = "\(tmp)/int_\(i).srt"
                    run(Bin.ffmpeg, "-y", "-i", input,
                        "-map", "0:\(sub.index)", "-f", "srt", srtP)
                    if nonEmpty(srtP) {
                        cleaned.append(SubEntry(path: srtP, lang: lang3, codec: "srt"))
                    }
                }
            }
        }

        // External subtitles
        if loadExt {
            let dir  = (base as NSString).deletingLastPathComponent
            let stem = (base as NSString).lastPathComponent
            if let files = try? FileManager.default.contentsOfDirectory(atPath: dir) {
                let extFiles = files
                    .filter { $0.hasPrefix(stem) && $0 != (input as NSString).lastPathComponent }
                    .filter { $0.lowercased().hasSuffix(".srt") || $0.lowercased().hasSuffix(".ass") }
                    .map    { "\(dir)/\($0)" }
                    .sorted()

                for fp in extFiles {
                    let isAss  = fp.lowercased().hasSuffix(".ass")
                    let rawLng = langFromPath(fp)
                    let lang3  = langMap[rawLng] ?? rawLng
                    let idx    = cleaned.count

                    if fmt == "mp4" {
                        let srtP = "\(tmp)/ext_\(idx).srt"
                        let vttP = "\(tmp)/ext_\(idx).vtt"
                        if isAss { run(Bin.ffmpeg, "-y", "-i", fp, srtP) }
                        else     { try? FileManager.default.copyItem(atPath: fp, toPath: srtP) }
                        if nonEmpty(srtP) {
                            srtToVtt(srtP, vttP)
                            if nonEmpty(vttP) {
                                cleaned.append(SubEntry(path: vttP, lang: lang3, codec: "vtt"))
                            }
                        }
                    } else {
                        if isAss && !convertSRT {
                            let assP = "\(tmp)/ext_\(idx).ass"
                            try? FileManager.default.copyItem(atPath: fp, toPath: assP)
                            if nonEmpty(assP) {
                                cleaned.append(SubEntry(path: assP, lang: lang3, codec: "ass"))
                            }
                        } else {
                            let srtP = "\(tmp)/ext_\(idx).srt"
                            if isAss { run(Bin.ffmpeg, "-y", "-i", fp, srtP) }
                            else     { try? FileManager.default.copyItem(atPath: fp, toPath: srtP) }
                            if nonEmpty(srtP) {
                                cleaned.append(SubEntry(path: srtP, lang: lang3, codec: "srt"))
                            }
                        }
                    }
                }
            }
        }

        let hasAss = cleaned.contains { $0.codec == "ass" }

        // ──────────────────────────────────────────────────────
        // MP4 MODE
        // ──────────────────────────────────────────────────────
        if fmt == "mp4" {
            let tmpMp4 = "\(tmp)/video.mp4"

            // Step 1: Extract video + ALL audio tracks individually (preserves lang codes)
            var cmd1 = [Bin.ffmpeg, "-y", "-i", input, "-map", "0:v:0"]
            for a in audioStreams { cmd1 += ["-map", "0:\(a.index)"] }
            cmd1 += ["-c", "copy", "-sn", "-map_metadata", "-1", "-movflags", "+faststart"]
            if isHEVC { cmd1 += ["-tag:v", "hvc1"] }
            cmd1.append(tmpMp4)
            runArgs(cmd1)

            // Step 2: MP4Box mux
            var box = [Bin.mp4box, "-brand", "mp42", "-ab", "isom",
                       "-new", "-tight", "-inter", "500"]
            box += ["-add", "\(tmpMp4)#video:forcesync:name="]

            // Add each audio track with correct language
            // In the temp MP4: track 1 = video, track 2,3... = audio
            for (ai, a) in audioStreams.enumerated() {
                let rawLang = a.tags?["language"] ?? "und"
                let lang3   = langMap[rawLang] ?? rawLang
                let trackID = ai + 2
                box += ["-add", "\(tmpMp4)#audio:trackID=\(trackID):lang=\(lang3):name="]
            }

            // Subtitles
            for (i, sub) in cleaned.enumerated() {
                let dis = i > 0 ? ":disable" : ""
                box += ["-add", "\(sub.path):lang=\(sub.lang):group=2:name=\(dis)"]
            }

            // Chapters
            if !chapters.isEmpty {
                let chapFile = "\(tmp)/chap.txt"
                var lines: [String] = []
                for c in chapters {
                    let s     = Double(c.start_time) ?? 0
                    let title = c.tags?["title"] ?? "Chapter \(c.id)"
                    let h     = Int(s / 3600)
                    let m     = Int((s.truncatingRemainder(dividingBy: 3600)) / 60)
                    let sec   = s.truncatingRemainder(dividingBy: 60)
                    lines.append(String(format: "%02d:%02d:%06.3f %@", h, m, sec, title))
                }
                try? lines.joined(separator: "\n")
                    .write(toFile: chapFile, atomically: true, encoding: .utf8)
                box += ["-chap", chapFile]
            }

            box += ["-ipod", outFile]
            runArgs(box)
        }

        // ──────────────────────────────────────────────────────
        // MKV MODE — 2-pass strategy
        //
        // Pass 1: Video + Audio (with lang) + Subtitles (with lang) → stage1.mkv
        // Pass 2: stage1.mkv + chapters from source + font attachments → final.mkv
        //
        // Key flags:
        //   -map_metadata:g -1  → clears only GLOBAL metadata (encoder, title…)
        //                         does NOT touch stream-level language tags
        //   -map_chapters 1     → copies chapter titles from input index 1 (source)
        // ──────────────────────────────────────────────────────
        else {
            // Extract fonts before pass 1
            var fonts: [FontEntry] = []
            if hasAss && !convertSRT && !attStreams.isEmpty {
                let fontDir = "\(tmp)/fonts"
                try? FileManager.default.createDirectory(atPath: fontDir,
                                                          withIntermediateDirectories: true)
                // -dump_attachment:t "" is an INPUT option → must precede -i
                // cwd = fontDir so files are written there using their filename tag
                runArgs([Bin.ffmpeg,
                         "-dump_attachment:t", "",
                         "-i", input,
                         "-t", "0", "-f", "null", "-"],
                        workDir: fontDir)

                for att in attStreams {
                    let fname = att.tags?["filename"] ?? ""
                    let mtype = att.tags?["mimetype"] ?? "application/x-truetype-font"
                    guard !fname.isEmpty else { continue }
                    let fpath = "\(fontDir)/\(fname)"
                    if nonEmpty(fpath) {
                        fonts.append(FontEntry(path: fpath, filename: fname, mimetype: mtype))
                    }
                }
            }

            // Pass 1: Video + Audio (each stream individually) + Subtitles
            let stage1 = "\(tmp)/stage1.mkv"
            var cmd1   = [Bin.ffmpeg, "-y", "-i", input]
            for sub in cleaned { cmd1 += ["-i", sub.path] }

            cmd1 += ["-map", "0:v:0"]

            // Map each audio stream individually so lang codes survive
            for a in audioStreams { cmd1 += ["-map", "0:\(a.index)"] }

            // Map each subtitle
            for i in 0..<cleaned.count { cmd1 += ["-map", "\(i + 1):0"] }

            // Audio language metadata (stream-level)
            for (ai, a) in audioStreams.enumerated() {
                let lang = a.tags?["language"] ?? "und"
                cmd1 += ["-metadata:s:a:\(ai)", "language=\(lang)"]
            }

            // Subtitle codec + language metadata
            for (i, sub) in cleaned.enumerated() {
                let codec = sub.codec == "ass" ? "copy" : "subrip"
                cmd1 += ["-c:s:\(i)", codec,
                         "-metadata:s:s:\(i)", "language=\(sub.lang)"]
            }

            cmd1 += ["-c:v", "copy", "-c:a", "copy"]
            cmd1 += ["-map_metadata", "-1", "-map_chapters", "-1"]
            cmd1.append(stage1)
            runArgs(cmd1)

            // Pass 2: stage1 + chapters + fonts
            var cmd2 = [Bin.ffmpeg, "-y", "-i", stage1, "-i", input]
            cmd2 += ["-map", "0"]        // all streams from stage1 (lang preserved)
            cmd2 += ["-c", "copy"]
            // -map_metadata:g -1 clears only global metadata, NOT stream lang codes
            cmd2 += ["-map_metadata:g", "-1"]
            cmd2 += ["-map_chapters", "1"]   // chapters from source (input index 1)

            for (idx, font) in fonts.enumerated() {
                cmd2 += ["-attach", font.path,
                         "-metadata:s:t:\(idx)", "mimetype=\(font.mimetype)",
                         "-metadata:s:t:\(idx)", "filename=\(font.filename)"]
            }

            cmd2.append(outFile)
            runArgs(cmd2)
        }

        // Cleanup
        try? FileManager.default.removeItem(atPath: tmp)
    }

    // MARK: - Helpers

    private static func probe(_ path: String) -> ProbeResult? {
        let args = [Bin.ffprobe, "-v", "quiet", "-print_format", "json",
                    "-show_streams", "-show_chapters", path]
        let proc = Process()
        proc.executableURL  = URL(fileURLWithPath: args[0])
        proc.arguments      = Array(args.dropFirst())
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError  = Pipe()
        try? proc.run()
        proc.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return try? JSONDecoder().decode(ProbeResult.self, from: data)
    }

    @discardableResult
    private static func run(_ args: String...) -> Int32 {
        runArgs(args)
    }

    @discardableResult
    private static func runArgs(_ args: [String], workDir: String? = nil) -> Int32 {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: args[0])
        proc.arguments     = Array(args.dropFirst())
        if let wd = workDir {
            proc.currentDirectoryURL = URL(fileURLWithPath: wd)
        }
        proc.standardOutput = FileHandle.nullDevice
        proc.standardError  = FileHandle.nullDevice
        try? proc.run()
        proc.waitUntilExit()
        return proc.terminationStatus
    }

    private static func srtToVtt(_ srt: String, _ vtt: String) {
        guard let content = try? String(contentsOfFile: srt, encoding: .utf8) else { return }
        let vttContent = "WEBVTT\n\n" + content.replacingOccurrences(of: ",", with: ".")
        try? vttContent.write(toFile: vtt, atomically: true, encoding: .utf8)
    }

    private static func nonEmpty(_ path: String) -> Bool {
        let size = (try? FileManager.default.attributesOfItem(atPath: path))?[.size] as? Int ?? 0
        return size > 0
    }

    private static func langFromPath(_ path: String) -> String {
        let name = (path as NSString).lastPathComponent.lowercased()
        guard let regex = try? NSRegularExpression(pattern: "\\.([a-z]{2,3})\\.(srt|ass)$") else {
            return "und"
        }
        let range = NSRange(name.startIndex..., in: name)
        if let m = regex.firstMatch(in: name, range: range),
           let r = Range(m.range(at: 1), in: name) {
            return String(name[r])
        }
        return "und"
    }
}
