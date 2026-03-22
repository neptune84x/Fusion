import sys, os, subprocess, json, glob, re, shutil

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
        QWidget, QLabel, QProgressBar, QScrollArea, QFrame,
        QPushButton, QFileDialog, QMenu, QMessageBox,
        QDialog, QCheckBox, QComboBox, QSizePolicy, QAbstractScrollArea
    )
    from PyQt6.QtCore    import Qt, QThread, pyqtSignal, QRect, QPoint, QSize
    from PyQt6.QtGui     import (
        QPainter, QColor, QBrush, QPen, QAction,
        QKeySequence, QFont, QPalette
    )
except ImportError:
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════
# RENK PALETİ  (ekran görüntüsünden alınan değerler)
# ═══════════════════════════════════════════════════════════════════════
BG_WHITE        = "#ffffff"
BG_TOOLBAR      = "#f5f5f5"       # toolbar arka plan
BG_SETTINGS     = "#ffffff"       # settings pencere arka planı
BORDER_TOOLBAR  = "#d0d0d0"
BORDER_FOOTER   = "#c8c8c8"
BG_FOOTER       = "#ececec"

ZEBRA_ODD       = "#f0f0f2"
ZEBRA_EVEN      = "#ffffff"

SEL_BG          = "#1560d4"       # macOS seçim mavisi
SEL_TXT         = "#ffffff"

TXT_PRIMARY     = "#1d1d1f"
TXT_SECONDARY   = "#6e6e73"
TXT_BOLD        = "#000000"

DOT_WAITING     = "#b0b0b8"
DOT_WORKING     = "#ff9500"
DOT_DONE        = "#30d158"

PROGRESS_BG     = "#d0d0d0"
PROGRESS_FG     = "#1560d4"

SECTION_BOLD    = "#000000"       # "Add item:" "Output Format:" gibi başlıklar


# ═══════════════════════════════════════════════════════════════════════
# İŞLEME THREAD  (orijinal mantık değiştirilmedi)
# ═══════════════════════════════════════════════════════════════════════
class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)

    def __init__(self, input_file, widget, load_external=True, output_format="mkv"):
        super().__init__()
        self.input_file    = input_file
        self.widget        = widget
        self.load_external = load_external
        self.output_format = output_format

    def get_bin(self, name):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, "internal", name)
        return name

    def clean_and_force_srt_italics(self, text):
        if not text: return ""
        text = text.replace(r'\N', '\n').replace(r'\\N', '\n')
        text = re.sub(r'\{\\i1\}|\\i1|<i>|<I>', '', text)
        text = re.sub(r'\{\\i0\}|\\i0|</i>| </I>', '', text)
        text = re.sub(r'\{[^\}]*\}', '', text)
        return f"<i>{text.strip()}</i>"

    def process_ass_to_srt_with_italics(self, ass_path, srt_output_path):
        try:
            with open(ass_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
            srt_content = []; counter = 1
            for line in lines:
                if line.startswith("Dialogue:"):
                    parts = line.split(',', 9)
                    if len(parts) >= 10:
                        start_time = parts[1].replace('.', ',') + "0"
                        end_time   = parts[2].replace('.', ',') + "0"
                        text = parts[9].strip()
                        if "italic" in parts[3].lower() or "{\\i1}" in text:
                            text = self.clean_and_force_srt_italics(text)
                        else:
                            text = text.replace(r'\N', '\n').replace(r'\\N', '\n')
                            text = re.sub(r'\{[^\}]*\}', '', text).strip()
                        if text:
                            srt_content.append(
                                f"{counter}\n0{start_time[:-1]} --> 0{end_time[:-1]}\n{text}\n\n"
                            )
                            counter += 1
            with open(srt_output_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(srt_content)
        except:
            subprocess.run(
                [self.get_bin('ffmpeg'), '-y', '-i', ass_path, srt_output_path],
                capture_output=True
            )

    def convert_to_webvtt(self, srt_path, vtt_path):
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n")
                for line in lines:
                    f.write(line.replace(',', '.'))
            return True
        except:
            return False

    def run(self):
        ffmpeg  = self.get_bin('ffmpeg')
        ffprobe = self.get_bin('ffprobe')
        mp4box  = self.get_bin('mp4box')

        base_path   = os.path.splitext(self.input_file)[0]
        temp_dir    = base_path + ".fusiontemp"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        output_ext  = "mp4" if self.output_format == "mp4_vtt" else "mkv"
        output_file = f"{base_path}_Fusion.{output_ext}"

        try:
            info = json.loads(subprocess.check_output(
                [ffprobe, '-v', 'quiet', '-print_format', 'json',
                 '-show_streams', '-show_chapters', self.input_file]
            ))
        except:
            info = {}

        chaps        = info.get('chapters', [])
        video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
        has_audio    = any(s.get('codec_type') == 'audio' for s in info.get('streams', []))
        is_hevc      = video_stream and video_stream.get('codec_name') == 'hevc'
        internal_subs = [s for s in info.get('streams', []) if s.get('codec_type') == 'subtitle']
        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger",
                 "fr":"fra","es":"spa","it":"ita","pt":"por","ar":"ara"}

        cleaned_list = []
        for i, sub in enumerate(internal_subs):
            lang     = sub.get('tags', {}).get('language', 'und')
            temp_srt = os.path.join(temp_dir, f"int_{i}.srt")
            subprocess.run(
                [ffmpeg, '-y', '-i', self.input_file,
                 '-map', f"0:{sub['index']}", '-f', 'srt', temp_srt],
                capture_output=True
            )
            if os.path.exists(temp_srt) and os.path.getsize(temp_srt) > 0:
                final_sub = temp_srt
                if self.output_format == "mp4_vtt":
                    temp_vtt = temp_srt.replace('.srt', '.vtt')
                    self.convert_to_webvtt(temp_srt, temp_vtt)
                    final_sub = temp_vtt
                cleaned_list.append({'path': final_sub, 'lang': l_map.get(lang, lang)})

        if self.load_external:
            for f in sorted(glob.glob(base_path + "*.*")):
                if f.lower().endswith(('.srt', '.ass')) and f != self.input_file:
                    temp_srt = os.path.join(temp_dir, f"ext_{len(cleaned_list)}.srt")
                    if f.lower().endswith('.ass'):
                        self.process_ass_to_srt_with_italics(f, temp_srt)
                    else:
                        shutil.copy2(f, temp_srt)
                    if os.path.exists(temp_srt) and os.path.getsize(temp_srt) > 0:
                        final_sub = temp_srt
                        if self.output_format == "mp4_vtt":
                            temp_vtt = temp_srt.replace('.srt', '.vtt')
                            self.convert_to_webvtt(temp_srt, temp_vtt)
                            final_sub = temp_vtt
                        match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', f.lower())
                        lang = match.group(1) if match else "und"
                        cleaned_list.append({'path': final_sub, 'lang': l_map.get(lang, lang)})

        if self.output_format == "mp4_vtt":
            temp_mp4 = os.path.join(temp_dir, "video_pure.mp4")
            ff_cmd   = [ffmpeg, '-y', '-i', self.input_file, '-map', '0:v:0']
            if has_audio: ff_cmd.extend(['-map', '0:a?'])
            ff_cmd.extend(['-c', 'copy', '-sn', '-map_metadata', '-1', '-movflags', '+faststart'])
            if is_hevc: ff_cmd.extend(['-tag:v', 'hvc1'])
            ff_cmd.append(temp_mp4)
            subprocess.run(ff_cmd, capture_output=True)

            box_cmd = [mp4box, "-brand", "mp42", "-ab", "isom", "-new", "-tight", "-inter", "500"]
            box_cmd.extend(["-add", f"{temp_mp4}#video:forcesync:name="])
            if has_audio: box_cmd.extend(["-add", f"{temp_mp4}#audio:name="])
            for i, c in enumerate(cleaned_list):
                dis = ":disable" if i > 0 else ""
                box_cmd.extend(["-add", f"{c['path']}:lang={c['lang']}:group=2:name={dis}"])
            if chaps:
                chapters_txt = os.path.join(temp_dir, "chapters.txt")
                with open(chapters_txt, "w", encoding="utf-8") as f:
                    for c in chaps:
                        s = float(c.get('start_time', 0))
                        title = c.get('tags', {}).get('title') or f"Chapter {c.get('id', 0)}"
                        f.write(f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{s%60:06.3f} {title}\n")
                box_cmd.extend(["-chap", chapters_txt])
            box_cmd.extend(["-ipod", output_file])
            subprocess.run(box_cmd, capture_output=True)
        else:
            mkv_meta = os.path.join(temp_dir, "mkv_meta.txt")
            with open(mkv_meta, "w", encoding="utf-8") as f:
                f.write(";FFMETADATA1\n")
                for c in chaps:
                    f.write("\n[CHAPTER]\nTIMEBASE=1/1000\n")
                    f.write(f"START={int(float(c['start_time'])*1000)}\n")
                    f.write(f"END={int(float(c['end_time'])*1000)}\n")
                    title = c.get('tags', {}).get('title') or f"Chapter {c.get('id', 0)}"
                    f.write(f"title={title}\n")

            cmd = [ffmpeg, '-y', '-i', self.input_file]
            for c in cleaned_list: cmd.extend(['-i', c['path']])
            cmd.extend(['-i', mkv_meta, '-map', '0:v:0', '-map', '0:a?'])
            for i, c in enumerate(cleaned_list):
                cmd.extend(['-map', f'{i+1}:0',
                             f"-c:s:{i}", "subrip",
                             f"-metadata:s:s:{i}", f"language={c['lang']}"])
            cmd.extend(['-c:v', 'copy', '-c:a', 'copy',
                        '-map_metadata', '-1',
                        '-map_metadata', f'{len(cleaned_list)+1}',
                        output_file])
            subprocess.run(cmd, capture_output=True)

        shutil.rmtree(temp_dir, ignore_errors=True)
        self.finished_signal.emit(self)


# ═══════════════════════════════════════════════════════════════════════
# TOOLBAR BUTTON  —  Subler ekran görüntüsüne birebir
#   • Büyük filled ikon  (▶  ⚙  ＋)
#   • Altında küçük etiket
#   • hover: hafif gri arka plan  /  pressed: daha koyu
# ═══════════════════════════════════════════════════════════════════════
class ToolbarButton(QPushButton):
    def __init__(self, icon_text: str, label: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 62)
        self.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                border-radius: 7px;
            }
            QPushButton:hover   { background: rgba(0,0,0,0.06); }
            QPushButton:pressed { background: rgba(0,0,0,0.12); }
            QPushButton:disabled { }
        """)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 7, 0, 5)
        vl.setSpacing(2)

        self._ico = QLabel(icon_text)
        self._ico.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        f_ico = QFont()
        f_ico.setPointSize(22)
        self._ico.setFont(f_ico)
        self._ico.setStyleSheet(f"color: {TXT_PRIMARY}; background: transparent;")

        self._lbl = QLabel(label)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        f_lbl = QFont()
        f_lbl.setPointSize(10)
        self._lbl.setFont(f_lbl)
        self._lbl.setStyleSheet(f"color: {TXT_PRIMARY}; background: transparent;")

        vl.addWidget(self._ico)
        vl.addWidget(self._lbl)


# ═══════════════════════════════════════════════════════════════════════
# FILE ROW  —  zebra listesindeki tek satır
# ═══════════════════════════════════════════════════════════════════════
class FileWidget(QFrame):
    ROW_H = 22

    def __init__(self, filename: str, queue_widget):
        super().__init__()
        self.queue_widget = queue_widget
        self.is_selected  = False
        self.status       = "waiting"
        self.setFixedHeight(self.ROW_H)
        self.setFrameShape(QFrame.Shape.NoFrame)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(10, 0, 10, 0)
        hl.setSpacing(7)

        # durum noktası
        self._dot = QLabel("●")
        self._dot.setFixedWidth(12)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(); f.setPointSize(7)
        self._dot.setFont(f)

        # dosya adı
        self._name = QLabel(filename)
        f2 = QFont(); f2.setPointSize(12)
        self._name.setFont(f2)

        hl.addWidget(self._dot)
        hl.addWidget(self._name)
        hl.addStretch()

        self._refresh()

    def set_status(self, mode: str):
        self.status = mode
        self._refresh()

    def set_selected(self, v: bool):
        self.is_selected = v
        self._refresh()

    def _refresh(self):
        dot_color = {
            "waiting": DOT_WAITING,
            "working": DOT_WORKING,
            "done":    DOT_DONE,
        }.get(self.status, DOT_WAITING)

        if self.is_selected:
            self.setStyleSheet(
                f"background: {SEL_BG}; border-radius: 4px;"
            )
            self._name.setStyleSheet(f"color: {SEL_TXT};")
            self._dot.setStyleSheet(f"color: rgba(255,255,255,0.65);")
        else:
            self.setStyleSheet("background: transparent;")
            self._name.setStyleSheet(f"color: {TXT_PRIMARY};")
            self._dot.setStyleSheet(f"color: {dot_color};")


# ═══════════════════════════════════════════════════════════════════════
# QUEUE LIST  —  zebra, rubber-band seçimi, drag-drop, sağ tık
# ═══════════════════════════════════════════════════════════════════════
class QueueList(QWidget):
    files_dropped = pyqtSignal(list)
    ROW_H = FileWidget.ROW_H

    def __init__(self, main_win):
        super().__init__()
        self.main_win  = main_win
        self.items     = []
        self._sel_start = None
        self._sel_rect  = QRect()

        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self.setMinimumHeight(200)
        self.setStyleSheet(f"background: {BG_WHITE};")

        self._vl = QVBoxLayout(self)
        self._vl.setContentsMargins(0, 0, 0, 0)
        self._vl.setSpacing(0)
        self._vl.setAlignment(Qt.AlignmentFlag.AlignTop)

    # zebra şerit
    def paintEvent(self, event):
        p = QPainter(self)
        for i in range(self.height() // self.ROW_H + 2):
            c = QColor(ZEBRA_ODD) if i % 2 == 1 else QColor(ZEBRA_EVEN)
            p.fillRect(0, i * self.ROW_H, self.width(), self.ROW_H, c)
        if not self._sel_rect.isNull():
            p.setPen(QPen(QColor(21, 96, 212, 180), 1))
            p.setBrush(QBrush(QColor(21, 96, 212, 35)))
            p.drawRect(self._sel_rect)

    # fare
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._sel_start = e.pos()
            if not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
                for it in self.items: it.set_selected(False)
            self.update()

    def mouseMoveEvent(self, e):
        if self._sel_start:
            self._sel_rect = QRect(self._sel_start, e.pos()).normalized()
            for it in self.items:
                it.set_selected(self._sel_rect.intersects(it.geometry()))
            self.update()

    def mouseReleaseEvent(self, e):
        self._sel_start = None
        self._sel_rect  = QRect()
        self.update()

    # drag-drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        self.files_dropped.emit([u.toLocalFile() for u in e.mimeData().urls()])

    # sağ tık
    def _ctx_menu(self, pos):
        m = QMenu(self)
        a_rem = QAction("Remove Selected", self)
        a_rem.setEnabled(any(i.is_selected for i in self.items))
        a_rem.triggered.connect(self.main_win.remove_selected)
        a_clr = QAction("Clear Completed", self)
        a_clr.setEnabled(any(i.status == "done" for i in self.items))
        a_clr.triggered.connect(self.main_win.remove_completed)
        m.addAction(a_rem); m.addAction(a_clr)
        m.exec(self.mapToGlobal(pos))


# ═══════════════════════════════════════════════════════════════════════
# SETTINGS WINDOW  —  ayrı pencere, trafik ışıkları, beyaz arka plan
#   Ekran görüntüsündeki sıra ve içerik birebir kopyalandı.
# ═══════════════════════════════════════════════════════════════════════
class SettingsWindow(QDialog):

    # ── yardımcı: bölüm başlığı ──────────────────────────────────
    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        f = QFont(); f.setPointSize(12); f.setBold(True)
        lbl.setFont(f)
        lbl.setStyleSheet(f"color: {SECTION_BOLD};")
        return lbl

    # ── yardımcı: normal checkbox ────────────────────────────────
    @staticmethod
    def _cb(text: str, checked=False) -> QCheckBox:
        c = QCheckBox(text)
        f = QFont(); f.setPointSize(12)
        c.setFont(f)
        c.setChecked(checked)
        return c

    # ── yardımcı: combo box ──────────────────────────────────────
    @staticmethod
    def _combo(items: list) -> QComboBox:
        c = QComboBox()
        c.addItems(items)
        f = QFont(); f.setPointSize(12)
        c.setFont(f)
        c.setMinimumWidth(140)
        c.setStyleSheet("""
            QComboBox {
                border: 1px solid #b0b0b8;
                border-radius: 5px;
                padding: 1px 6px 1px 6px;
                background: white;
                min-height: 22px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        return c

    # ── yardımcı: bold label (Language: Color Space: vb.) ────────
    @staticmethod
    def _bold_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        f = QFont(); f.setPointSize(12); f.setBold(True)
        lbl.setFont(f)
        lbl.setStyleSheet(f"color: {TXT_PRIMARY};")
        return lbl

    # ── yardımcı: satır (label + combo) ─────────────────────────
    @staticmethod
    def _row(label_widget: QWidget, combo_widget: QWidget,
             indent: int = 0) -> QHBoxLayout:
        hl = QHBoxLayout()
        hl.setContentsMargins(indent, 0, 0, 0)
        hl.setSpacing(8)
        hl.addWidget(label_widget)
        hl.addWidget(combo_widget)
        hl.addStretch()
        return hl

    # ── yardımcı: yatay ayırıcı çizgi ───────────────────────────
    @staticmethod
    def _sep() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background: #d8d8dc; border: none;")
        return line

    # ─────────────────────────────────────────────────────────────
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.setWindowTitle("Settings")
        self.setFixedWidth(420)
        self.setStyleSheet(f"background: {BG_SETTINGS};")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(6)

        # ── Add item: ─────────────────────────────────────────────
        root.addWidget(self._section_label("Add item:"))
        self.cb_clear_meta   = self._cb("Clear existing metadata", True)
        root.addWidget(self.cb_clear_meta)

        root.addSpacing(4)
        root.addWidget(self._sep())
        root.addSpacing(4)

        # ── Output Format: ────────────────────────────────────────
        root.addWidget(self._section_label("Output Format:"))
        self.combo_fmt = self._combo(["Matroska (SubRip)", "Apple MP4 (WebVTT)"])
        idx = 0 if self.mw.output_format == "mkv" else 1
        self.combo_fmt.setCurrentIndex(idx)
        self.combo_fmt.setMinimumWidth(200)
        self.combo_fmt.currentIndexChanged.connect(self._on_fmt)
        fmt_row = QHBoxLayout(); fmt_row.addWidget(self.combo_fmt); fmt_row.addStretch()
        root.addLayout(fmt_row)

        root.addSpacing(4)

        # ── Artwork: ──────────────────────────────────────────────
        self.combo_art_type = self._combo(["Season", "Movie", "Episode"])
        self.combo_art_qual = self._combo(["Standard", "High"])
        art_hl = QHBoxLayout(); art_hl.setSpacing(8)
        art_hl.addWidget(self._bold_lbl("Artwork:"))
        art_hl.addWidget(self.combo_art_type)
        art_hl.addWidget(self.combo_art_qual)
        art_hl.addStretch()
        root.addLayout(art_hl)

        root.addSpacing(4)
        root.addWidget(self._sep())
        root.addSpacing(4)

        # ── Checkbox grubu (Subler ekranındaki sırayla) ───────────
        self.cb_ext_subs     = self._cb("Load external subtitles",   True)
        self.cb_clear_names  = self._cb("Clear tracks names",        True)
        self.cb_prettify     = self._cb("Prettify audio track names", True)
        self.cb_rename_chap  = self._cb("Rename chapters titles",    False)
        self.cb_complete_lng = self._cb("Complete tracks language",  False)

        self.cb_ext_subs.toggled.connect(
            lambda v: setattr(self.mw, 'load_external_subs', v)
        )

        for cb in [self.cb_ext_subs, self.cb_clear_names,
                   self.cb_prettify, self.cb_rename_chap, self.cb_complete_lng]:
            root.addWidget(cb)

        # Language: (Complete tracks language altında, girintili)
        self.combo_lang_complete = self._combo(
            ["Turkish","English","French","German","Spanish",
             "Italian","Russian","Japanese","Portuguese","Arabic"]
        )
        root.addLayout(self._row(self._bold_lbl("Language:"),
                                  self.combo_lang_complete, indent=22))

        # Enable audio track with language
        self.cb_audio_lang = self._cb("Enable audio track with language", False)
        root.addWidget(self.cb_audio_lang)
        self.combo_lang_audio = self._combo(
            ["English","Turkish","French","German","Spanish",
             "Italian","Russian","Japanese","Portuguese","Arabic"]
        )
        root.addLayout(self._row(self._bold_lbl("Language:"),
                                  self.combo_lang_audio, indent=22))

        # Enable subtitles track with language
        self.cb_sub_lang = self._cb("Enable subtitles track with language", False)
        root.addWidget(self.cb_sub_lang)
        self.combo_lang_sub = self._combo(
            ["English","Turkish","French","German","Spanish",
             "Italian","Russian","Japanese","Portuguese","Arabic"]
        )
        root.addLayout(self._row(self._bold_lbl("Language:"),
                                  self.combo_lang_sub, indent=22))

        # Apply color space
        self.cb_color_space = self._cb("Apply color space", False)
        root.addWidget(self.cb_color_space)
        self.combo_cs = self._combo(["Implicit","BT.709","BT.2020","Display P3"])
        root.addLayout(self._row(self._bold_lbl("Color Space:"),
                                  self.combo_cs, indent=22))

        # Optimize / Send to TV
        self.cb_optimize = self._cb("Optimize", True)
        self.cb_send_tv  = self._cb("Send to TV", False)
        root.addWidget(self.cb_optimize)
        root.addWidget(self.cb_send_tv)

        root.addSpacing(4)
        root.addWidget(self._sep())
        root.addSpacing(4)

        # ── Global options: ───────────────────────────────────────
        root.addWidget(self._section_label("Global options:"))
        self.cb_autostart = self._cb("Auto-Start the queue",         False)
        self.cb_notify    = self._cb("Show Notification When Done",  True)
        root.addWidget(self.cb_autostart)
        root.addWidget(self.cb_notify)

        root.addStretch()
        self.adjustSize()

    def _on_fmt(self, idx: int):
        self.mw.output_format = "mkv" if idx == 0 else "mp4_vtt"


# ═══════════════════════════════════════════════════════════════════════
# ANA PENCERE
# ═══════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue")
        self.resize(560, 420)
        self.setMinimumSize(480, 300)
        self.setAcceptDrops(True)

        self.load_external_subs = True
        self.output_format      = "mkv"
        self.threads            = []
        self.active_queue       = []
        self._settings_win      = None

        self._build_ui()
        self._build_menu()

    # ── UI ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── TOOLBAR ──────────────────────────────────────────────
        tb = QWidget()
        tb.setFixedHeight(70)
        tb.setStyleSheet(
            f"background: {BG_TOOLBAR};"
            f"border-bottom: 1px solid {BORDER_TOOLBAR};"
        )
        tb_hl = QHBoxLayout(tb)
        tb_hl.setContentsMargins(6, 0, 6, 0)
        tb_hl.setSpacing(0)

        self.btn_start    = ToolbarButton("▶", "Start")
        self.btn_settings = ToolbarButton("⚙", "Settings")
        self.btn_add      = ToolbarButton("＋", "Add Item")

        # Subler düzeni: Start | Settings | <stretch> | Add Item
        tb_hl.addWidget(self.btn_start)
        tb_hl.addWidget(self.btn_settings)
        tb_hl.addStretch()
        tb_hl.addWidget(self.btn_add)

        self.btn_start.clicked.connect(self.start_processing)
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_add.clicked.connect(self.open_files)

        # ── SCROLL + QUEUE ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background: {BG_WHITE};")

        self._queue = QueueList(self)
        self._queue.files_dropped.connect(self.add_to_list)
        scroll.setWidget(self._queue)

        # ── FOOTER ───────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(24)
        footer.setStyleSheet(
            f"background: {BG_FOOTER};"
            f"border-top: 1px solid {BORDER_FOOTER};"
        )
        f_hl = QHBoxLayout(footer)
        f_hl.setContentsMargins(10, 0, 10, 0)
        f_hl.setSpacing(0)

        self._status_lbl = QLabel("0 items in queue.")
        f_status = QFont(); f_status.setPointSize(11)
        self._status_lbl.setFont(f_status)
        self._status_lbl.setStyleSheet(f"color: {TXT_SECONDARY};")

        self._progress = QProgressBar()
        self._progress.setFixedSize(130, 5)
        self._progress.setTextVisible(False)
        self._progress.setValue(0)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background: {PROGRESS_BG};
                border-radius: 2px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {PROGRESS_FG};
                border-radius: 2px;
            }}
        """)

        f_hl.addWidget(self._status_lbl)
        f_hl.addStretch()
        f_hl.addWidget(self._progress)

        root.addWidget(tb)
        root.addWidget(scroll)
        root.addWidget(footer)

        cw = QWidget()
        cw.setLayout(root)
        cw.setStyleSheet(f"background: {BG_WHITE};")
        self.setCentralWidget(cw)

    # ── MENÜ ─────────────────────────────────────────────────────
    def _build_menu(self):
        mb = self.menuBar()

        app_m = mb.addMenu("Fusion")
        a_about = QAction("About Fusion", self)
        a_about.triggered.connect(self._show_about)
        a_quit  = QAction("Quit Fusion", self)
        a_quit.setShortcut(QKeySequence("Ctrl+Q"))
        a_quit.triggered.connect(self.close)
        app_m.addAction(a_about)
        app_m.addSeparator()
        app_m.addAction(a_quit)

        file_m = mb.addMenu("File")
        a_add  = QAction("Add to Queue…", self)
        a_add.setShortcut(QKeySequence("Ctrl+O"))
        a_add.triggered.connect(self.open_files)
        a_rem  = QAction("Remove Selected", self)
        a_rem.setShortcut(QKeySequence("Backspace"))
        a_rem.triggered.connect(self.remove_selected)
        a_clr  = QAction("Clear Completed", self)
        a_clr.triggered.connect(self.remove_completed)
        file_m.addAction(a_add)
        file_m.addSeparator()
        file_m.addAction(a_rem)
        file_m.addAction(a_clr)

        queue_m = mb.addMenu("Queue")
        a_start = QAction("Start", self)
        a_start.setShortcut(QKeySequence("Ctrl+Return"))
        a_start.triggered.connect(self.start_processing)
        queue_m.addAction(a_start)

    # ── Settings ─────────────────────────────────────────────────
    def _open_settings(self):
        if self._settings_win is None or not self._settings_win.isVisible():
            self._settings_win = SettingsWindow(self)
            # Toolbar altına, Settings butonunun hizasına yerleştir
            gp = self.btn_settings.mapToGlobal(
                QPoint(0, self.btn_settings.height() + 2)
            )
            self._settings_win.move(gp)
        self._settings_win.show()
        self._settings_win.raise_()
        self._settings_win.activateWindow()

    # ── About ────────────────────────────────────────────────────
    def _show_about(self):
        QMessageBox.information(
            self, "About Fusion",
            "Fusion v0.2.0\n\n"
            "Universal macOS video converter.\n"
            "Subtitle muxing · Chapter preservation\n"
            "MKV & MP4 output\n\n"
            "Powered by ffmpeg · ffprobe · MP4Box"
        )

    # ── Dosya işlemleri ───────────────────────────────────────────
    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Videos", "",
            "Video Files (*.mkv *.mp4 *.avi *.mov *.ts *.m2ts);;All Files (*)"
        )
        if paths: self.add_to_list(paths)

    def add_to_list(self, paths: list):
        for p in paths:
            w = FileWidget(os.path.basename(p), self._queue)
            w.full_path = p
            self._queue._vl.addWidget(w)
            self._queue.items.append(w)
        self._refresh_status()

    def remove_completed(self):
        for it in [i for i in self._queue.items if i.status == "done"]:
            self._queue.items.remove(it); it.setParent(None)
        self._refresh_status()

    def remove_selected(self):
        for it in [i for i in self._queue.items if i.is_selected]:
            self._queue.items.remove(it); it.setParent(None)
        self._refresh_status()

    def _refresh_status(self):
        n = len(self._queue.items)
        self._status_lbl.setText(
            f"{n} item{'s' if n != 1 else ''} in queue."
        )

    # ── İşleme ───────────────────────────────────────────────────
    def start_processing(self):
        self.active_queue = [i for i in self._queue.items if i.status == "waiting"]
        if self.active_queue:
            self._progress.setValue(0)
            self._process_next()

    def _process_next(self):
        if not self.active_queue:
            self._status_lbl.setText("Completed.")
            return
        item = self.active_queue.pop(0)
        item.set_status("working")
        t = ConversionThread(
            item.full_path, item,
            self.load_external_subs,
            self.output_format
        )
        t.finished_signal.connect(self._on_done)
        self.threads.append(t)
        t.start()

    def _on_done(self, t):
        t.widget.set_status("done")
        done  = sum(1 for i in self._queue.items if i.status == "done")
        total = len(self._queue.items)
        if total > 0:
            self._progress.setValue(int(done / total * 100))
        self._process_next()

    # ── Drag-drop (pencere seviyesi) ─────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_to_list([u.toLocalFile() for u in e.mimeData().urls()])


# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macos")
    f = QFont(".AppleSystemUIFont", 13)
    app.setFont(f)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
