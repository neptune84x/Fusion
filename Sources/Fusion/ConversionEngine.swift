import Foundation

// MARK: - ffprobe JSON models

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

// MARK: - Internal work structs

private struct SubEntry {
    var path: String
    var lang: String   // 3-letter ISO-639-2
    var codec: String  // "srt" | "ass" | "vtt"
}

private struct FontEntry {
    var path: String
    var filename: String
    var mimetype: String
}

// MARK: - Binary locator

enum Bin {
    static var ffmpeg:  String { locate("ffmpeg")  }
    static var ffprobe: String { locate("ffprobe") }
    static var mp4box:  String { locate("mp4box")  }

    private static func locate(_ name: String) -> String {
        if let url = Bundle.main.resourceURL {
            let p = url.appendingPathComponent(name).path
            if FileManager.default.isExecutableFile(atPath: p) { return p }
        }
        return name
    }
}

// MARK: - Engine

final class ConversionEngine {

    // ISO 639-1 → 639-2/B mapping
    private static let langMap: [String: String] = [
        "tr":"tur", "en":"eng", "ru":"rus", "jp":"jpn", "de":"ger",
        "fr":"fra", "es":"spa", "it":"ita", "pt":"por", "ar":"ara"
    ]

    // MARK: Entry point (called on a background thread by the UI)

    static func process(item: QueueItem,
                        prefs: Preferences,
                        completion: @escaping () -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            convert(item: item, prefs: prefs)
            DispatchQueue.main.async { completion() }
        }
    }

    // MARK: - Main conversion

    private static func convert(item: QueueItem, prefs: Preferences) {
        let input      = item.url.path
        let base       = (input as NSString).deletingPathExtension
        let fmt        = prefs.outputFormat          // "mkv" | "mp4"
        let convertSRT = prefs.convertToSRT
        let loadExt    = prefs.loadExternalSubs
        let outFile    = "\(base)_Fusion.\(fmt == "mp4" ? "mp4" : "mkv")"

        // .fusiontemp dir — hidden from Finder
        let tmp = base + ".fusiontemp"
        try? FileManager.default.removeItem(atPath: tmp)
        try? FileManager.default.createDirectory(atPath: tmp,
                                                  withIntermediateDirectories: true,
                                                  attributes: nil)
        shell("chflags", "hidden", tmp)

        // ── Probe ────────────────────────────────────────────
        guard let info = probe(input) else {
            try? FileManager.default.removeItem(atPath: tmp)
            return
        }

        let allStreams   = info.streams
        let chapters    = info.chapters
        let videoStream = allStreams.first { $0.codec_type == "video" }
        let audioStreams = allStreams.filter { $0.codec_type == "audio" }
        let subStreams   = allStreams.filter { $0.codec_type == "subtitle" }
        let attStreams   = allStreams.filter { $0.codec_type == "attachment" }
        let isHEVC      = videoStream?.codec_name == "hevc"

        // Check for Dolby Vision — preserve codec_name for tag decisions
        // If source has Dolby Vision, we must NOT add -tag:v hvc1 for MP4
        // (hvc1 forces re-tag that breaks DoVi compatibility)
        let hasDoVi: Bool = {
            // DoVi streams are either: codec_name == "dvhe"/"dvh1"
            // or a side-data profile in hevc video with DOVI config
            for s in allStreams {
                if let cn = s.codec_name, cn.hasPrefix("dv") { return true }
                // Check for DoVi as a secondary video stream (profile 7/8)
                if s.codec_type == "video",
                   let cn = s.codec_name,
                   (cn == "hevc" || cn == "h265") {
                    // tags may contain "DOVI" indicator
                    if let tags = s.tags {
                        for (k, v) in tags {
                            if k.lowercased().contains("dovi") ||
                               v.lowercased().contains("dovi") { return true }
                        }
                    }
                }
            }
            return false
        }()

        // ── Build subtitle list ───────────────────────────────
        var cleaned: [SubEntry] = []

        for (i, sub) in subStreams.enumerated() {
            let rawLang = sub.tags?["language"] ?? "und"
            let lang3   = langMap[rawLang] ?? rawLang
            let codec   = sub.codec_name ?? ""

            if fmt == "mp4" {
                let srtP = "\(tmp)/int_\(i).srt"
                let vttP = "\(tmp)/int_\(i).vtt"
                shell(Bin.ffmpeg, "-y", "-i", input,
                      "-map", "0:\(sub.index)", "-f", "srt", srtP)
                if nonEmpty(srtP) {
                    srtToVtt(srtP, vttP)
                    if nonEmpty(vttP) {
                        cleaned.append(SubEntry(path: vttP, lang: lang3, codec: "vtt"))
                    }
                }
            } else {
                // MKV mode
                if !convertSRT && (codec == "ass" || codec == "ssa") {
                    let assP = "\(tmp)/int_\(i).ass"
                    shell(Bin.ffmpeg, "-y", "-i", input,
                          "-map", "0:\(sub.index)", assP)
                    if nonEmpty(assP) {
                        cleaned.append(SubEntry(path: assP, lang: lang3, codec: "ass"))
                    }
                } else {
                    let srtP = "\(tmp)/int_\(i).srt"
                    // ffmpeg handles ASS→SRT conversion natively (no manual parsing)
                    shell(Bin.ffmpeg, "-y", "-i", input,
                          "-map", "0:\(sub.index)", "-f", "srt", srtP)
                    if nonEmpty(srtP) {
                        cleaned.append(SubEntry(path: srtP, lang: lang3, codec: "srt"))
                    }
                }
            }
        }

        // ── External subtitles ────────────────────────────────
        if loadExt {
            let dir  = (base as NSString).deletingLastPathComponent
            let stem = (base as NSString).lastPathComponent
            if let files = try? FileManager.default.contentsOfDirectory(atPath: dir) {
                let extFiles = files
                    .filter {
                        let lc = $0.lowercased()
                        return $0.hasPrefix(stem)
                            && (lc.hasSuffix(".srt") || lc.hasSuffix(".ass"))
                            && "\(dir)/\($0)" != input
                    }
                    .sorted()

                for fname in extFiles {
                    let fp    = "\(dir)/\(fname)"
                    let isAss = fname.lowercased().hasSuffix(".ass")
                    let lang  = langFromPath(fp)
                    let lang3 = langMap[lang] ?? lang
                    let idx   = cleaned.count

                    if fmt == "mp4" {
                        let srtP = "\(tmp)/ext_\(idx).srt"
                        let vttP = "\(tmp)/ext_\(idx).vtt"
                        if isAss { shell(Bin.ffmpeg, "-y", "-i", fp, srtP) }
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
                            if isAss { shell(Bin.ffmpeg, "-y", "-i", fp, srtP) }
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

        // ════════════════════════════════════════════════════════
        // MP4 MODE
        // ════════════════════════════════════════════════════════
        if fmt == "mp4" {
            let tmpMp4 = "\(tmp)/video_pure.mp4"

            // ── Extract video + EVERY audio stream individually ──────
            // FIX: "0:a?" maps only the first audio track in some ffmpeg builds.
            // Mapping each stream by index guarantees all tracks are included.
            var cmd: [String] = [Bin.ffmpeg, "-y", "-i", input, "-map", "0:v:0"]
            for a in audioStreams {
                cmd += ["-map", "0:\(a.index)"]
            }
            cmd += ["-c", "copy", "-sn", "-map_metadata", "-1", "-movflags", "+faststart"]

            // DoVi fix: if source has Dolby Vision, do NOT re-tag with hvc1
            // hvc1 tagging breaks DoVi metadata (profile 5/8 cross-compatibility)
            if isHEVC && !hasDoVi {
                cmd += ["-tag:v", "hvc1"]
            }
            cmd.append(tmpMp4)
            shellArgs(cmd)

            // ── MP4Box mux ────────────────────────────────────────────
            var box: [String] = [
                Bin.mp4box, "-brand", "mp42", "-ab", "isom",
                "-new", "-tight", "-inter", "500"
            ]
            box += ["-add", "\(tmpMp4)#video:forcesync:name="]

            // Add each audio track with correct language.
            // In the temp MP4: track 1 = video, tracks 2,3,... = audio (in order).
            for (ai, a) in audioStreams.enumerated() {
                let rawLang = a.tags?["language"] ?? "und"
                let lang3   = langMap[rawLang] ?? rawLang
                let trackID = ai + 2   // 1-based; track 1 is video
                box += ["-add", "\(tmpMp4)#audio:trackID=\(trackID):lang=\(lang3):name="]
            }

            // Subtitles
            for (i, sub) in cleaned.enumerated() {
                let dis = i > 0 ? ":disable" : ""
                box += ["-add", "\(sub.path):lang=\(sub.lang):group=2:name=\(dis)"]
            }

            // Chapters
            if !chapters.isEmpty {
                let chapFile = "\(tmp)/chapters.txt"
                var lines: [String] = []
                for c in chapters {
                    let s     = Double(c.start_time) ?? 0
                    let title = c.tags?["title"] ?? "Chapter \(c.id)"
                    let h = Int(s / 3600)
                    let m = Int((s.truncatingRemainder(dividingBy: 3600)) / 60)
                    let sec = s.truncatingRemainder(dividingBy: 60)
                    lines.append(String(format: "%02d:%02d:%06.3f %@", h, m, sec, title))
                }
                try? lines.joined(separator: "\n")
                         .write(toFile: chapFile, atomically: true, encoding: .utf8)
                box += ["-chap", chapFile]
            }

            box += ["-ipod", outFile]
            shellArgs(box)
        }

        // ════════════════════════════════════════════════════════
        // MKV MODE — 2-pass strategy
        //
        // WHY 2 PASSES:
        //   Pass 1 builds video+audio+subtitles with correct stream-level
        //   language codes.  We cannot add -attach in the same pass that
        //   also uses -map_metadata because ffmpeg reorders streams in a
        //   way that corrupts attachment indices.
        //
        //   Pass 2 reads the clean stage1.mkv, adds chapter names from
        //   the original source, and attaches font files.
        //
        // KEY FLAGS:
        //   -map_metadata:g -1  → clears ONLY global metadata (title, encoder…)
        //                         does NOT touch stream-level language tags
        //   -map_chapters N     → copies chapter names from input N
        // ════════════════════════════════════════════════════════
        else {

            // ── Pass 0: Extract fonts ─────────────────────────────────
            var fonts: [FontEntry] = []
            if hasAss && !convertSRT && !attStreams.isEmpty {
                let fontDir = "\(tmp)/fonts"
                try? FileManager.default.createDirectory(atPath: fontDir,
                                                          withIntermediateDirectories: true,
                                                          attributes: nil)
                // -dump_attachment:t "" is an INPUT option → must come before -i
                // Running with cwd=fontDir makes ffmpeg write files there
                // using the filename tag stored in each attachment stream.
                shellArgs([Bin.ffmpeg,
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

            // ── Pass 1: Video + Audio (each stream, with lang) + Subtitles ──
            let stage1 = "\(tmp)/stage1.mkv"
            var cmd1: [String] = [Bin.ffmpeg, "-y", "-i", input]
            for sub in cleaned { cmd1 += ["-i", sub.path] }

            // Map video
            cmd1 += ["-map", "0:v:0"]

            // FIX: map each audio stream individually to preserve ALL tracks
            // and to allow setting language metadata per-stream.
            // "0:a?" can silently drop tracks in some ffmpeg builds.
            for a in audioStreams {
                cmd1 += ["-map", "0:\(a.index)"]
            }

            // Map each subtitle input
            for i in 0..<cleaned.count {
                cmd1 += ["-map", "\(i + 1):0"]
            }

            // FIX: set language for every audio stream individually
            for (ai, a) in audioStreams.enumerated() {
                let lang = a.tags?["language"] ?? "und"
                cmd1 += ["-metadata:s:a:\(ai)", "language=\(lang)"]
            }

            // Subtitle codec + language
            for (i, sub) in cleaned.enumerated() {
                let codec = sub.codec == "ass" ? "copy" : "subrip"
                cmd1 += ["-c:s:\(i)", codec,
                         "-metadata:s:s:\(i)", "language=\(sub.lang)"]
            }

            cmd1 += ["-c:v", "copy", "-c:a", "copy"]
            cmd1 += ["-map_metadata", "-1", "-map_chapters", "-1"]
            cmd1.append(stage1)
            shellArgs(cmd1)

            // ── Pass 2: stage1 + chapters (from source) + fonts ──────────
            var cmd2: [String] = [Bin.ffmpeg, "-y",
                                   "-i", stage1,    // input 0
                                   "-i", input]     // input 1 (chapters source)
            cmd2 += ["-map", "0"]      // all streams from stage1
            cmd2 += ["-c", "copy"]

            // -map_metadata:g -1 removes only global metadata (encoder tag etc.)
            // Stream-level language tags set in Pass 1 are PRESERVED.
            cmd2 += ["-map_metadata:g", "-1"]

            // Copy chapter names from the original source (input index 1)
            cmd2 += ["-map_chapters", "1"]

            // Attach fonts (output option, must come after all -map flags)
            for (idx, font) in fonts.enumerated() {
                cmd2 += ["-attach", font.path,
                         "-metadata:s:t:\(idx)", "mimetype=\(font.mimetype)",
                         "-metadata:s:t:\(idx)", "filename=\(font.filename)"]
            }

            cmd2.append(outFile)
            shellArgs(cmd2)
        }

        // Cleanup
        try? FileManager.default.removeItem(atPath: tmp)
    }

    // MARK: - Helpers

    private static func probe(_ path: String) -> ProbeResult? {
        let args = [Bin.ffprobe, "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams", "-show_chapters", path]
        let proc = Process()
        proc.executableURL  = URL(fileURLWithPath: args[0])
        proc.arguments      = Array(args.dropFirst())
        let pipe            = Pipe()
        proc.standardOutput = pipe
        proc.standardError  = Pipe()
        try? proc.run()
        proc.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return try? JSONDecoder().decode(ProbeResult.self, from: data)
    }

    @discardableResult
    private static func shell(_ args: String...) -> Int32 {
        shellArgs(args)
    }

    @discardableResult
    private static func shellArgs(_ args: [String], workDir: String? = nil) -> Int32 {
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
        let out = "WEBVTT\n\n" + content.replacingOccurrences(of: ",", with: ".")
        try? out.write(toFile: vtt, atomically: true, encoding: .utf8)
    }

    private static func nonEmpty(_ path: String) -> Bool {
        let size = (try? FileManager.default.attributesOfItem(atPath: path))?[.size] as? Int ?? 0
        return size > 0
    }

    private static func langFromPath(_ path: String) -> String {
        let name = (path as NSString).lastPathComponent.lowercased()
        if let regex = try? NSRegularExpression(pattern: "\\.([a-z]{2,3})\\.(srt|ass)$") {
            let rng = NSRange(name.startIndex..., in: name)
            if let m = regex.firstMatch(in: name, range: rng),
               let r = Range(m.range(at: 1), in: name) {
                return String(name[r])
            }
        }
        return "und"
    }
}
