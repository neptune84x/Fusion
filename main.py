import sys, os, subprocess, json, glob, re, shutil
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
        QWidget, QLabel, QProgressBar, QScrollArea,
        QFrame, QPushButton, QFileDialog, QMenu, QMessageBox,
        QDialog, QCheckBox, QComboBox, QFormLayout, QGroupBox,
        QSizePolicy, QSpacerItem, QAbstractScrollArea
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPoint, QSize, QMimeData
    from PyQt6.QtGui import (
        QPainter, QColor, QBrush, QAction, QKeySequence,
        QPen, QFont, QFontDatabase, QPalette, QDragEnterEvent, QDropEvent
    )
except ImportError:
    sys.exit(1)

# ── Renk sabitleri (macOS Subler paleti) ─────────────────────────────
C_BG          = "#ffffff"
C_TOOLBAR_BG  = "#f6f6f6"
C_TOOLBAR_BORDER = "#d0d0d0"
C_LIST_ODD    = "#f5f5f7"
C_LIST_EVEN   = "#ffffff"
C_SELECT_BG   = "#0063da"
C_SELECT_TXT  = "#ffffff"
C_NORMAL_TXT  = "#1d1d1f"
C_SECONDARY   = "#6e6e73"
C_FOOTER_BG   = "#f0f0f0"
C_FOOTER_BORDER = "#d0d0d0"
C_PROGRESS_BG = "#d8d8d8"
C_PROGRESS_FG = "#0063da"
C_DONE_GREEN  = "#34c759"
C_WORKING_ORG = "#ff9500"
C_WAITING     = "#aeaeb2"
C_SEP         = "#d1d1d6"


# ══════════════════════════════════════════════════════════════════════
# İŞLEME THREAD (orijinal mantık aynen korundu)
# ══════════════════════════════════════════════════════════════════════
class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)

    def __init__(self, input_file, widget, load_external=True, output_format="mkv"):
        super().__init__()
        self.input_file   = input_file
        self.widget       = widget
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
            ffmpeg = self.get_bin('ffmpeg')
            subprocess.run([ffmpeg, '-y', '-i', ass_path, srt_output_path], capture_output=True)

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

        base_path = os.path.splitext(self.input_file)[0]
        temp_dir  = base_path + ".fusiontemp"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        output_ext  = "mp4" if self.output_format == "mp4_vtt" else "mkv"
        output_file = f"{base_path}_Fusion.{output_ext}"

        try:
            probe_cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json',
                         '-show_streams', '-show_chapters', self.input_file]
            info = json.loads(subprocess.check_output(probe_cmd))
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
                is_disabled = ":disable" if i > 0 else ""
                box_cmd.extend(["-add", f"{c['path']}:lang={c['lang']}:group=2:name={is_disabled}"])
            if chaps:
                chapters_txt = os.path.join(temp_dir, "chapters.txt")
                with open(chapters_txt, "w", encoding="utf-8") as f:
                    for c in chaps:
                        start = float(c.get('start_time', 0))
                        hrs   = int(start // 3600)
                        mins  = int((start % 3600) // 60)
                        secs  = start % 60
                        title = c.get('tags', {}).get('title') or f"Chapter {c.get('id', 0)}"
                        f.write(f"{hrs:02d}:{mins:02d}:{secs:06.3f} {title}\n")
                box_cmd.extend(["-chap", chapters_txt])
            box_cmd.extend(["-ipod", output_file])
            subprocess.run(box_cmd, capture_output=True)
        else:
            mkv_metadata = os.path.join(temp_dir, "mkv_meta.txt")
            with open(mkv_metadata, "w", encoding="utf-8") as f:
                f.write(";FFMETADATA1\n")
                for c in chaps:
                    f.write("\n[CHAPTER]\nTIMEBASE=1/1000\n")
                    f.write(f"START={int(float(c['start_time'])*1000)}\n")
                    f.write(f"END={int(float(c['end_time'])*1000)}\n")
                    title = c.get('tags', {}).get('title') or f"Chapter {c.get('id', 0)}"
                    f.write(f"title={title}\n")

            cmd = [ffmpeg, '-y', '-i', self.input_file]
            for c in cleaned_list: cmd.extend(['-i', c['path']])
            cmd.extend(['-i', mkv_metadata])
            cmd.extend(['-map', '0:v:0', '-map', '0:a?'])
            for i, c in enumerate(cleaned_list):
                cmd.extend(['-map', f'{i+1}:0',
                             f"-c:s:{i}", "subrip",
                             f"-metadata:s:s:{i}", f"language={c['lang']}"])
            cmd.extend([
                '-c:v', 'copy', '-c:a', 'copy',
                '-map_metadata', '-1',
                '-map_metadata', f'{len(cleaned_list)+1}',
                output_file
            ])
            subprocess.run(cmd, capture_output=True)

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        self.finished_signal.emit(self)


# ══════════════════════════════════════════════════════════════════════
# TOOLBAR BUTTON — Subler'daki gibi ikon + metin, dikey
# ══════════════════════════════════════════════════════════════════════
class ToolbarButton(QPushButton):
    """Subler toolbar butonu: büyük SF-benzeri ikon üstte, küçük etiket altta."""
    def __init__(self, icon_char, label, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 52)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: rgba(0,0,0,0.07);
            }
            QPushButton:pressed {
                background: rgba(0,0,0,0.13);
            }
            QPushButton:disabled {
                opacity: 0.38;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 4)
        layout.setSpacing(1)

        self._icon_lbl = QLabel(icon_char)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("font-size: 20px; color: #1d1d1f; background: transparent;")

        self._text_lbl = QLabel(label)
        self._text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_lbl.setStyleSheet(
            "font-size: 10px; color: #1d1d1f; font-weight: 400; background: transparent;"
        )

        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._text_lbl)

    def set_enabled_style(self, enabled: bool):
        color = "#1d1d1f" if enabled else "#b0b0b5"
        self._icon_lbl.setStyleSheet(f"font-size: 20px; color: {color}; background: transparent;")
        self._text_lbl.setStyleSheet(
            f"font-size: 10px; color: {color}; font-weight: 400; background: transparent;"
        )


# ══════════════════════════════════════════════════════════════════════
# FILE ROW WIDGET — Subler'daki liste satırı
# ══════════════════════════════════════════════════════════════════════
class FileWidget(QFrame):
    def __init__(self, filename, parent_list):
        super().__init__()
        self.parent_list = parent_list
        self.is_selected = False
        self.status      = "waiting"
        self.setFixedHeight(22)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        # ── durum göstergesi ─────────────────────────────────────
        self._status_dot = QLabel("●")
        self._status_dot.setFixedWidth(14)
        self._status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_dot.setStyleSheet(f"color: {C_WAITING}; font-size: 8px;")

        # ── dosya adı ─────────────────────────────────────────────
        self._name = QLabel(filename)
        self._name.setStyleSheet(f"color: {C_NORMAL_TXT}; font-size: 12px;")

        layout.addWidget(self._status_dot)
        layout.addWidget(self._name)
        layout.addStretch()

        self._update_style()

    # ── durum ────────────────────────────────────────────────────
    def set_status(self, mode):
        self.status = mode
        dot_color = {
            "working": C_WORKING_ORG,
            "done":    C_DONE_GREEN,
            "waiting": C_WAITING,
        }.get(mode, C_WAITING)
        self._status_dot.setStyleSheet(f"color: {dot_color}; font-size: 8px;")
        self._update_style()

    # ── seçim ────────────────────────────────────────────────────
    def _update_style(self):
        if self.is_selected:
            self.setStyleSheet(
                f"background-color: {C_SELECT_BG}; border-radius: 3px;"
            )
            self._name.setStyleSheet(f"color: {C_SELECT_TXT}; font-size: 12px;")
            self._status_dot.setStyleSheet(
                f"color: rgba(255,255,255,0.7); font-size: 8px;"
            )
        else:
            self.setStyleSheet("background-color: transparent; border-radius: 3px;")
            self._name.setStyleSheet(f"color: {C_NORMAL_TXT}; font-size: 12px;")
            dot_color = {
                "working": C_WORKING_ORG,
                "done":    C_DONE_GREEN,
                "waiting": C_WAITING,
            }.get(self.status, C_WAITING)
            self._status_dot.setStyleSheet(f"color: {dot_color}; font-size: 8px;")

    def set_selected(self, sel: bool):
        self.is_selected = sel
        self._update_style()


# ══════════════════════════════════════════════════════════════════════
# QUEUE LIST — zebra şeritli, sürükle-bırak, sağ tık menüsü
# ══════════════════════════════════════════════════════════════════════
class QueueListWidget(QWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self, main_window):
        super().__init__()
        self.main_window  = main_window
        self.items        = []
        self.sel_start    = None
        self.sel_rect     = QRect()
        self._row_h       = 22

        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setMinimumHeight(300)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    # ── zebra boyama ─────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        for i in range(self.height() // self._row_h + 1):
            color = QColor(C_LIST_ODD) if i % 2 == 1 else QColor(C_LIST_EVEN)
            painter.fillRect(0, i * self._row_h, self.width(), self._row_h, color)
        # rubber-band seçim dikdörtgeni
        if not self.sel_rect.isNull():
            painter.setPen(QPen(QColor(0, 99, 218, 160), 1))
            painter.setBrush(QBrush(QColor(0, 99, 218, 40)))
            painter.drawRect(self.sel_rect)

    # ── fare seçimi ──────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.sel_start = event.pos()
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                for item in self.items:
                    item.set_selected(False)
            self.update()

    def mouseMoveEvent(self, event):
        if self.sel_start:
            self.sel_rect = QRect(self.sel_start, event.pos()).normalized()
            for item in self.items:
                item.set_selected(self.sel_rect.intersects(item.geometry()))
            self.update()

    def mouseReleaseEvent(self, event):
        self.sel_start = None
        self.sel_rect  = QRect()
        self.update()

    # ── sürükle-bırak ────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        self.files_dropped.emit(paths)

    # ── sağ tık menüsü ───────────────────────────────────────────
    def _context_menu(self, pos):
        menu = QMenu(self)
        has_sel  = any(i.is_selected for i in self.items)
        has_done = any(i.status == "done" for i in self.items)

        act_rem = QAction("Remove Selected", self)
        act_rem.setEnabled(has_sel)
        act_rem.triggered.connect(self.main_window.remove_selected)

        act_clr = QAction("Clear Completed", self)
        act_clr.setEnabled(has_done)
        act_clr.triggered.connect(self.main_window.remove_completed)

        menu.addAction(act_rem)
        menu.addAction(act_clr)
        menu.exec(self.mapToGlobal(pos))


# ══════════════════════════════════════════════════════════════════════
# SETTINGS DIALOG — Subler ayarlar paneli (ekran görüntüsüne birebir)
# ══════════════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.setWindowTitle("Settings")
        self.setFixedWidth(380)
        self.setModal(False)
        self.setStyleSheet(f"""
            QDialog {{
                background: #f2f2f7;
            }}
            QLabel {{
                color: {C_NORMAL_TXT};
                font-size: 12px;
            }}
            QCheckBox {{
                color: {C_NORMAL_TXT};
                font-size: 12px;
                spacing: 6px;
            }}
            QComboBox {{
                font-size: 12px;
                color: {C_NORMAL_TXT};
                background: white;
                border: 1px solid #c7c7cc;
                border-radius: 5px;
                padding: 2px 8px;
                min-height: 22px;
            }}
            QGroupBox {{
                font-size: 11px;
                font-weight: 600;
                color: {C_SECONDARY};
                border: none;
                margin-top: 6px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 0px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(0)

        # ── Add item ─────────────────────────────────────────────
        grp_add = self._section("Add item:")
        self.cb_clear_meta  = QCheckBox("Clear existing metadata")
        self.cb_clear_meta.setChecked(True)
        grp_add.addWidget(self.cb_clear_meta)

        # ── Output Format (bizim temel ayarımız) ─────────────────
        grp_fmt = self._section("Output Format:")
        fmt_row = QHBoxLayout()
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItem("Matroska (SubRip)",    "mkv")
        self.combo_fmt.addItem("Apple MP4 (WebVTT)",   "mp4_vtt")
        idx = self.combo_fmt.findData(self.mw.output_format)
        if idx >= 0: self.combo_fmt.setCurrentIndex(idx)
        self.combo_fmt.currentIndexChanged.connect(self._on_fmt_change)
        fmt_row.addWidget(self.combo_fmt)
        fmt_row.addStretch()
        grp_fmt.addLayout(fmt_row)

        # ── Artwork ──────────────────────────────────────────────
        grp_art = self._section("Artwork:")
        art_row = QHBoxLayout()
        self.combo_art_type = QComboBox(); self.combo_art_type.addItems(["Season","Movie","Episode"])
        self.combo_art_qual = QComboBox(); self.combo_art_qual.addItems(["Standard","High"])
        art_row.addWidget(self.combo_art_type)
        art_row.addWidget(self.combo_art_qual)
        art_row.addStretch()
        grp_art.addLayout(art_row)

        # ── Checkboxes (Subler ekranından birebir) ────────────────
        grp_opt = self._section("")
        self.cb_ext_subs    = QCheckBox("Load external subtitles")
        self.cb_clear_names = QCheckBox("Clear tracks names")
        self.cb_prettify    = QCheckBox("Prettify audio track names")
        self.cb_rename_chap = QCheckBox("Rename chapters titles")
        self.cb_complete_lang = QCheckBox("Complete tracks language")

        self.cb_ext_subs.setChecked(self.mw.load_external_subs)
        self.cb_clear_names.setChecked(True)
        self.cb_prettify.setChecked(True)

        self.cb_ext_subs.toggled.connect(lambda v: setattr(self.mw, 'load_external_subs', v))

        for cb in [self.cb_ext_subs, self.cb_clear_names, self.cb_prettify,
                   self.cb_rename_chap, self.cb_complete_lang]:
            grp_opt.addWidget(cb)

        # Language row (Complete tracks language altında)
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(22, 0, 0, 0)
        lang_lbl = QLabel("Language:")
        lang_lbl.setStyleSheet(f"color: {C_NORMAL_TXT}; font-weight: 600; font-size: 12px;")
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["Turkish","English","French","German","Spanish","Italian","Russian","Japanese","Portuguese","Arabic"])
        lang_row.addWidget(lang_lbl)
        lang_row.addWidget(self.combo_lang)
        lang_row.addStretch()
        grp_opt.addLayout(lang_row)

        # Audio track language
        self.cb_audio_lang = QCheckBox("Enable audio track with language")
        grp_opt.addWidget(self.cb_audio_lang)
        audio_lang_row = QHBoxLayout()
        audio_lang_row.setContentsMargins(22, 0, 0, 0)
        al_lbl = QLabel("Language:")
        al_lbl.setStyleSheet(f"color: {C_NORMAL_TXT}; font-weight: 600; font-size: 12px;")
        self.combo_audio_lang = QComboBox()
        self.combo_audio_lang.addItems(["English","Turkish","French","German","Spanish","Italian","Russian","Japanese","Portuguese","Arabic"])
        audio_lang_row.addWidget(al_lbl)
        audio_lang_row.addWidget(self.combo_audio_lang)
        audio_lang_row.addStretch()
        grp_opt.addLayout(audio_lang_row)

        # Subtitle track language
        self.cb_sub_lang = QCheckBox("Enable subtitles track with language")
        grp_opt.addWidget(self.cb_sub_lang)
        sub_lang_row = QHBoxLayout()
        sub_lang_row.setContentsMargins(22, 0, 0, 0)
        sl_lbl = QLabel("Language:")
        sl_lbl.setStyleSheet(f"color: {C_NORMAL_TXT}; font-weight: 600; font-size: 12px;")
        self.combo_sub_lang = QComboBox()
        self.combo_sub_lang.addItems(["English","Turkish","French","German","Spanish","Italian","Russian","Japanese","Portuguese","Arabic"])
        sub_lang_row.addWidget(sl_lbl)
        sub_lang_row.addWidget(self.combo_sub_lang)
        sub_lang_row.addStretch()
        grp_opt.addLayout(sub_lang_row)

        # Color space
        self.cb_color_space = QCheckBox("Apply color space")
        grp_opt.addWidget(self.cb_color_space)
        cs_row = QHBoxLayout()
        cs_row.setContentsMargins(22, 0, 0, 0)
        cs_lbl = QLabel("Color Space:")
        cs_lbl.setStyleSheet(f"color: {C_NORMAL_TXT}; font-weight: 600; font-size: 12px;")
        self.combo_cs = QComboBox(); self.combo_cs.addItems(["Implicit","BT.709","BT.2020","Display P3"])
        cs_row.addWidget(cs_lbl); cs_row.addWidget(self.combo_cs); cs_row.addStretch()
        grp_opt.addLayout(cs_row)

        # Optimize
        self.cb_optimize = QCheckBox("Optimize")
        self.cb_optimize.setChecked(True)
        grp_opt.addWidget(self.cb_optimize)

        self.cb_send_tv = QCheckBox("Send to TV")
        grp_opt.addWidget(self.cb_send_tv)

        # ── Global options ────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C_SEP};"); grp_opt.addWidget(sep)

        grp_global = self._section("Global options:")
        self.cb_autostart  = QCheckBox("Auto-Start the queue")
        self.cb_notify     = QCheckBox("Show Notification When Done")
        self.cb_notify.setChecked(True)
        grp_global.addWidget(self.cb_autostart)
        grp_global.addWidget(self.cb_notify)

        # ── Tüm grupları root'a ekle ──────────────────────────────
        for grp in [grp_add, grp_fmt, grp_art, grp_opt, grp_global]:
            root.addLayout(grp)
            root.addSpacing(6)

        root.addStretch()

    def _section(self, title):
        vbox = QVBoxLayout()
        vbox.setSpacing(3)
        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color: {C_NORMAL_TXT}; font-weight: 700; font-size: 12px;")
            vbox.addWidget(lbl)
        return vbox

    def _on_fmt_change(self, idx):
        self.mw.output_format = self.combo_fmt.itemData(idx)


# ══════════════════════════════════════════════════════════════════════
# ANA PENCERE
# ══════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Queue")
        self.resize(560, 420)
        self.setMinimumSize(480, 320)
        self.setAcceptDrops(True)

        self.load_external_subs = True
        self.output_format      = "mkv"
        self.threads            = []
        self.active_queue       = []
        self._settings_dlg      = None

        self._build_ui()
        self._build_menu()

    # ── UI inşası ────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── TOOLBAR ──────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(58)
        toolbar.setStyleSheet(
            f"background: {C_TOOLBAR_BG};"
            f"border-bottom: 1px solid {C_TOOLBAR_BORDER};"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(0)

        # Subler toolbar sırası: Start | Settings | (spacer) | Add Item
        self.btn_start    = ToolbarButton("▶", "Start")
        self.btn_settings = ToolbarButton("⚙", "Settings")
        self.btn_add      = ToolbarButton("＋", "Add Item")

        tb_layout.addWidget(self.btn_start)
        tb_layout.addWidget(self.btn_settings)
        tb_layout.addStretch()
        tb_layout.addWidget(self.btn_add)

        self.btn_start.clicked.connect(self.start_processing)
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_add.clicked.connect(self.open_files)

        # ── SCROLL + LİSTE ────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: white;")

        self._queue = QueueListWidget(self)
        self._queue.files_dropped.connect(self.add_to_list)
        self._scroll.setWidget(self._queue)

        # ── FOOTER ────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(22)
        footer.setStyleSheet(
            f"background: {C_FOOTER_BG};"
            f"border-top: 1px solid {C_FOOTER_BORDER};"
        )
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(10, 0, 10, 0)
        f_layout.setSpacing(0)

        self._status_lbl = QLabel("0 items in queue.")
        self._status_lbl.setStyleSheet(f"font-size: 11px; color: {C_SECONDARY};")

        self._progress = QProgressBar()
        self._progress.setFixedWidth(120)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setValue(0)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background: {C_PROGRESS_BG};
                border-radius: 2px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {C_PROGRESS_FG};
                border-radius: 2px;
            }}
        """)

        f_layout.addWidget(self._status_lbl)
        f_layout.addStretch()
        f_layout.addWidget(self._progress)

        # ── BİRLEŞTİR ────────────────────────────────────────────
        root.addWidget(toolbar)
        root.addWidget(self._scroll)
        root.addWidget(footer)

        cw = QWidget()
        cw.setLayout(root)
        cw.setStyleSheet(f"background: {C_BG};")
        self.setCentralWidget(cw)

    # ── MENÜ ─────────────────────────────────────────────────────
    def _build_menu(self):
        mb = self.menuBar()

        # Fusion menüsü
        app_menu = mb.addMenu("Fusion")
        a_about = QAction("About Fusion", self)
        a_about.triggered.connect(self._show_about)
        a_quit  = QAction("Quit Fusion", self)
        a_quit.setShortcut(QKeySequence("Ctrl+Q"))
        a_quit.triggered.connect(self.close)
        app_menu.addAction(a_about)
        app_menu.addSeparator()
        app_menu.addAction(a_quit)

        # File menüsü
        file_menu = mb.addMenu("File")
        a_add = QAction("Add to Queue…", self)
        a_add.setShortcut(QKeySequence("Ctrl+O"))
        a_add.triggered.connect(self.open_files)
        a_rem = QAction("Remove Selected", self)
        a_rem.setShortcut(QKeySequence("Backspace"))
        a_rem.triggered.connect(self.remove_selected)
        a_clr = QAction("Clear Completed", self)
        a_clr.triggered.connect(self.remove_completed)
        file_menu.addAction(a_add)
        file_menu.addSeparator()
        file_menu.addAction(a_rem)
        file_menu.addAction(a_clr)

        # Queue menüsü
        queue_menu = mb.addMenu("Queue")
        a_start = QAction("Start", self)
        a_start.setShortcut(QKeySequence("Ctrl+Return"))
        a_start.triggered.connect(self.start_processing)
        queue_menu.addAction(a_start)

    # ── SETTINGS ─────────────────────────────────────────────────
    def _open_settings(self):
        if self._settings_dlg is None or not self._settings_dlg.isVisible():
            self._settings_dlg = SettingsDialog(self)
            # Toolbar'ın Settings butonuna yakın konumla
            btn_pos = self.btn_settings.mapToGlobal(
                QPoint(0, self.btn_settings.height() + 4)
            )
            self._settings_dlg.move(btn_pos)
        self._settings_dlg.show()
        self._settings_dlg.raise_()

    # ── ABOUT ────────────────────────────────────────────────────
    def _show_about(self):
        QMessageBox.information(
            self, "About Fusion",
            "Fusion v0.2.0\n\n"
            "Universal macOS video converter.\n"
            "Subtitle muxing, chapter preservation,\n"
            "MKV & MP4 output.\n\n"
            "Powered by ffmpeg, ffprobe, MP4Box."
        )

    # ── DOSYA İŞLEMLERİ ─────────────────────────────────────────
    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Videos",
            filter="Video Files (*.mkv *.mp4 *.avi *.mov *.ts *.m2ts);;All Files (*)"
        )
        if paths:
            self.add_to_list(paths)

    def add_to_list(self, paths):
        for p in paths:
            w = FileWidget(os.path.basename(p), self._queue)
            w.full_path = p
            self._queue._layout.addWidget(w)
            self._queue.items.append(w)
        self._update_status()

    def remove_completed(self):
        for item in [i for i in self._queue.items if i.status == "done"]:
            self._queue.items.remove(item)
            item.setParent(None)
        self._update_status()

    def remove_selected(self):
        for item in [i for i in self._queue.items if i.is_selected]:
            self._queue.items.remove(item)
            item.setParent(None)
        self._update_status()

    def _update_status(self):
        n = len(self._queue.items)
        self._status_lbl.setText(f"{n} item{'s' if n != 1 else ''} in queue.")

    # ── İŞLEME ──────────────────────────────────────────────────
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

    # ── SÜRÜKLE-BIRAK (pencere seviyesi) ─────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_to_list([u.toLocalFile() for u in event.mimeData().urls()])


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("macos")

    # macOS native font
    font = QFont(".AppleSystemUIFont", 13)
    app.setFont(font)

    w = MainWindow()
    w.show()
    sys.exit(app.exec())
