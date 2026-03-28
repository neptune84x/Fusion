"""
Fusion — Subler-inspired macOS video queue processor
"""
import sys, os, subprocess, json, glob, re, shutil, math

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
        QWidget, QLabel, QProgressBar, QScrollArea, QFrame,
        QPushButton, QFileDialog, QMenu, QMessageBox,
        QDialog, QCheckBox, QComboBox, QSizePolicy, QAbstractItemView
    )
    from PyQt6.QtCore  import (Qt, QThread, pyqtSignal, QRect, QPoint,
                               QSize, QSettings, QRectF, QPointF, QEvent)
    from PyQt6.QtGui   import (QPainter, QColor, QBrush, QPen, QAction,
                               QKeySequence, QFont, QPainterPath)
except ImportError:
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# RENKLER & TEMALAR
# ═══════════════════════════════════════════════════════════════
BG_WIN         = "#ffffff"
BG_TOOLBAR     = "#f5f5f5"
BORDER_TOOLBAR = "#d0d0d0"
BG_FOOTER      = "#ececec"
BORDER_FOOTER  = "#c8c8c8"
ZEBRA_ODD      = "#efefef"
ZEBRA_EVEN     = "#ffffff"
SEL_BG         = "#1560d4"
SEL_TXT        = "#ffffff"
TXT_PRIMARY    = "#1d1d1f"
TXT_SECONDARY  = "#6e6e73"
DOT_WAITING    = "#b0b0b8"
DOT_WORKING    = "#ff9500"
DOT_DONE       = "#30d158"
PROG_BG        = "#d0d0d0"
PROG_FG        = "#1560d4"
SECT_LINE      = "#d8d8dc"
SETTINGS_BG    = "#f5f5f7"

ORG = "FusionApp"
APP = "Fusion"

DEFAULTS = {"output_format": "mkv", "convert_srt": True, "load_ext_subs": True}

def load_prefs():
    s = QSettings(ORG, APP)
    d = {}
    for k, v in DEFAULTS.items():
        d[k] = s.value(k, v, type=type(v))
    return d

def save_prefs(d):
    s = QSettings(ORG, APP)
    for k, v in d.items():
        s.setValue(k, v)

# ═══════════════════════════════════════════════════════════════
# İŞLEME MOTORU (CONVERSION THREAD)
# ═══════════════════════════════════════════════════════════════
class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)

    def __init__(self, input_file, widget, prefs):
        super().__init__()
        self.input_file = input_file
        self.widget     = widget
        self.prefs      = prefs

    def get_bin(self, name):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, "internal", name)
        return name

    def run_ff(self, *args):
        subprocess.run(list(args), capture_output=True)

    def clean_italics(self, text):
        if not text: return ""
        text = text.replace(r'\N', '\n').replace(r'\\N', '\n')
        text = re.sub(r'\{\\i1\}|\\i1|<i>|<I>', '', text)
        text = re.sub(r'\{\\i0\}|\\i0|</i>|</I>', '', text)
        text = re.sub(r'\{[^\}]*\}', '', text)
        return f"<i>{text.strip()}</i>"

    def ass_to_srt(self, ass_path, srt_path):
        try:
            with open(ass_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
            out = []
            n = 1
            for line in lines:
                if not line.startswith("Dialogue:"): continue
                parts = line.split(',', 9)
                if len(parts) < 10: continue
                s_t = parts[1].replace('.', ',') + "0"
                e_t = parts[2].replace('.', ',') + "0"
                txt = parts[9].strip()
                if "italic" in parts[3].lower() or "{\\i1}" in txt:
                    txt = self.clean_italics(txt)
                else:
                    txt = txt.replace(r'\N', '\n').replace(r'\\N', '\n')
                    txt = re.sub(r'\{[^\}]*\}', '', txt).strip()
                if txt:
                    out.append(f"{n}\n0{s_t[:-1]} --> 0{e_t[:-1]}\n{txt}\n\n")
                    n += 1
            with open(srt_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(out)
        except:
            self.run_ff(self.get_bin('ffmpeg'), '-y', '-i', ass_path, srt_path)

    def to_vtt(self, srt_path, vtt_path):
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n" + content.replace(',', '.'))
            return True
        except:
            return False

    def run(self):
        ffmpeg  = self.get_bin('ffmpeg')
        ffprobe = self.get_bin('ffprobe')
        mp4box  = self.get_bin('mp4box')
        prefs   = self.prefs

        base = os.path.splitext(self.input_file)[0]
        tmp  = base + ".fusiontemp"
        if os.path.exists(tmp): shutil.rmtree(tmp)
        os.makedirs(tmp, exist_ok=True)
        
        fmt         = prefs["output_format"]
        convert_srt = prefs["convert_srt"]
        load_ext    = prefs["load_ext_subs"]
        out_file    = f"{base}_Fusion.{'mp4' if fmt == 'mp4' else 'mkv'}"

        try:
            info = json.loads(subprocess.check_output([
                ffprobe, '-v', 'quiet', '-print_format', 'json', 
                '-show_streams', '-show_chapters', self.input_file
            ]))
        except: info = {}

        streams   = info.get('streams', [])
        chaps     = info.get('chapters', [])
        vstream   = next((s for s in streams if s.get('codec_type') == 'video'), None)
        has_audio = any(s.get('codec_type') == 'audio' for s in streams)
        is_hevc   = vstream and vstream.get('codec_name') == 'hevc'
        int_subs  = [s for s in streams if s.get('codec_type') == 'subtitle']

        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger",
                 "fr":"fra","es":"spa","it":"ita","pt":"por","ar":"ara"}

        cleaned = []

        # 1. Dahili Altyazıları Hazırla
        for i, sub in enumerate(int_subs):
            lang  = sub.get('tags', {}).get('language', 'und')
            codec = sub.get('codec_name', '')
            if fmt == "mp4":
                p = os.path.join(tmp, f"int_{i}.srt")
                self.run_ff(ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", '-f', 'srt', p)
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    vp = p.replace('.srt', '.vtt')
                    if self.to_vtt(p, vp):
                        cleaned.append({'path': vp, 'lang': l_map.get(lang, lang), 'codec': 'vtt'})
            else:
                if not convert_srt and codec in ('ass', 'ssa', 'ass '):
                    p = os.path.join(tmp, f"int_{i}.ass")
                    self.run_ff(ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", p)
                    if os.path.exists(p) and os.path.getsize(p) > 0:
                        cleaned.append({'path': p, 'lang': l_map.get(lang, lang), 'codec': 'ass'})
                else:
                    p = os.path.join(tmp, f"int_{i}.srt")
                    self.run_ff(ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", '-f', 'srt', p)
                    if os.path.exists(p) and os.path.getsize(p) > 0:
                        cleaned.append({'path': p, 'lang': l_map.get(lang, lang), 'codec': 'srt'})

        # 2. Harici Altyazıları Hazırla
        if load_ext:
            for fp in sorted(glob.glob(base + "*.*")):
                if not fp.lower().endswith(('.srt', '.ass')): continue
                if fp == self.input_file: continue
                is_ass = fp.lower().endswith('.ass')
                m = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', fp.lower())
                lang = m.group(1) if m else "und"
                
                if fmt == "mp4":
                    p = os.path.join(tmp, f"ext_{len(cleaned)}.srt")
                    if is_ass: self.ass_to_srt(fp, p)
                    else: shutil.copy2(fp, p)
                    vp = p.replace('.srt', '.vtt')
                    if self.to_vtt(p, vp):
                        cleaned.append({'path': vp, 'lang': l_map.get(lang, lang), 'codec': 'vtt'})
                else:
                    if is_ass and not convert_srt:
                        p = os.path.join(tmp, f"ext_{len(cleaned)}.ass")
                        shutil.copy2(fp, p)
                        cleaned.append({'path': p, 'lang': l_map.get(lang, lang), 'codec': 'ass'})
                    else:
                        p = os.path.join(tmp, f"ext_{len(cleaned)}.srt")
                        if is_ass: self.ass_to_srt(fp, p)
                        else: shutil.copy2(fp, p)
                        cleaned.append({'path': p, 'lang': l_map.get(lang, lang), 'codec': 'srt'})

        # 3. Muxing
        if fmt == "mp4":
            tmp_mp4 = os.path.join(tmp, "video_pure.mp4")
            cmd = [ffmpeg, '-y', '-i', self.input_file, '-map', '0:v:0']
            if has_audio: cmd.extend(['-map', '0:a?'])
            cmd.extend(['-c', 'copy', '-sn', '-map_metadata', '-1', '-movflags', '+faststart'])
            if is_hevc: cmd.extend(['-tag:v', 'hvc1'])
            cmd.append(tmp_mp4)
            subprocess.run(cmd, capture_output=True)

            box = [mp4box, "-brand", "mp42", "-ab", "isom", "-new", "-tight", "-inter", "500"]
            box.extend(["-add", f"{tmp_mp4}#video:forcesync:name="])
            if has_audio: box.extend(["-add", f"{tmp_mp4}#audio:name="])
            for i, c in enumerate(cleaned):
                dis = ":disable" if i > 0 else ""
                box.extend(["-add", f"{c['path']}:lang={c['lang']}:group=2:name={dis}"])
            if chaps:
                chap_f = os.path.join(tmp, "chaps.txt")
                with open(chap_f, "w", encoding="utf-8") as f:
                    for c in chaps:
                        s = float(c.get('start_time', 0))
                        t = (c.get('tags') or {}).get('title', f"Chapter {c.get('id',0)}")
                        f.write(f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{s%60:06.3f} {t}\n")
                box.extend(["-chap", chap_f])
            box.extend(["-ipod", out_file])
            subprocess.run(box, capture_output=True)

        else: # MKV Modu - STRATEJİYE UYGUN FONT DÜZELTMESİ
            cmd = [ffmpeg, '-y', '-i', self.input_file]
            for c in cleaned:
                cmd.extend(['-i', c['path']])
            
            # Ana haritalama: Video, Audio ve Orijinal Fontlar (t?)
            cmd.extend(['-map', '0:v:0', '-map', '0:a?', '-map', '0:t?'])
            
            # Altyazıları haritalama
            for i, c in enumerate(cleaned):
                cmd.extend(['-map', f'{i+1}:0'])
                codec = 'copy' if c['codec'] == 'ass' else 'subrip'
                cmd.extend([f'-c:s:{i}', codec])
                cmd.extend([f'-metadata:s:s:{i}', f"language={c['lang']}"])

            cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:t', 'copy'])
            cmd.extend(['-map_metadata', '0', '-map_chapters', '0'])
            cmd.append(out_file)
            subprocess.run(cmd, capture_output=True)

        shutil.rmtree(tmp, ignore_errors=True)
        self.finished_signal.emit(self)

# ═══════════════════════════════════════════════════════════════
# UI: ICON BUTTON
# ═══════════════════════════════════════════════════════════════
class IconButton(QPushButton):
    def __init__(self, icon_type, label, parent=None):
        super().__init__(parent)
        self._type  = icon_type
        self._label = label
        self._hover = self._press = False
        self.setFixedSize(72, 64)
        self.setFlat(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def enterEvent(self, e): self._hover = True; self.update()
    def leaveEvent(self, e): self._hover = False; self.update()
    def mousePressEvent(self, e): self._press = True; self.update(); super().mousePressEvent(e)
    def mouseReleaseEvent(self, e): self._press = False; self.update(); super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W/2, 24
        
        alpha = 30 if self._press else (15 if self._hover else 0)
        p.setBrush(QBrush(QColor(0, 0, 0, alpha)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 22, 22)
        
        ink = QColor(TXT_PRIMARY)
        if self._type == "play":
            p.setBrush(QBrush(ink))
            path = QPainterPath()
            path.moveTo(cx - 5, cy - 8); path.lineTo(cx - 5, cy + 8); path.lineTo(cx + 9, cy); path.closeSubpath()
            p.drawPath(path)
        elif self._type == "gear":
            p.setPen(QPen(ink, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), 7, 7)
            for i in range(8):
                a = math.radians(i*45); p.drawLine(QPointF(cx+7*math.cos(a), cy+7*math.sin(a)), QPointF(cx+10*math.cos(a), cy+10*math.sin(a)))
        elif self._type == "tray_down":
            p.setPen(QPen(ink, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.Round, Qt.PenJoinStyle.Round))
            p.drawLine(cx-7, cy+3, cx, cy+9); p.drawLine(cx, cy+9, cx+7, cy+3)
            p.drawLine(cx, cy-8, cx, cy+9)

        f = QFont(); f.setPointSize(10); p.setFont(f); p.setPen(ink)
        p.drawText(QRect(0, H-18, W, 16), Qt.AlignmentFlag.AlignCenter, self._label)

# ═══════════════════════════════════════════════════════════════
# UI: FILE WIDGET
# ═══════════════════════════════════════════════════════════════
class FileWidget(QFrame):
    def __init__(self, filename, queue_w):
        super().__init__()
        self.queue_w = queue_w
        self.is_selected = False
        self.status = "waiting"
        self.setFixedHeight(24)
        hl = QHBoxLayout(self); hl.setContentsMargins(10, 0, 10, 0); hl.setSpacing(7)
        self._dot = QLabel("●"); self._dot.setFixedWidth(12)
        self._name = QLabel(filename)
        nf = QFont(); nf.setPointSize(12); self._name.setFont(nf)
        hl.addWidget(self._dot); hl.addWidget(self._name); hl.addStretch()
        self._refresh()

    def set_status(self, s): self.status = s; self._refresh()
    def set_selected(self, v): self.is_selected = v; self._refresh()
    def _refresh(self):
        dot_c = {"waiting":DOT_WAITING, "working":DOT_WORKING, "done":DOT_DONE}.get(self.status)
        if self.is_selected:
            self.setStyleSheet(f"background:{SEL_BG};")
            self._name.setStyleSheet(f"color:{SEL_TXT};")
            self._dot.setStyleSheet("color:rgba(255,255,255,180);")
        else:
            self.setStyleSheet("background:transparent;")
            self._name.setStyleSheet(f"color:{TXT_PRIMARY};")
            self._dot.setStyleSheet(f"color:{dot_c};")

# ═══════════════════════════════════════════════════════════════
# UI: QUEUE LIST
# ═══════════════════════════════════════════════════════════════
class QueueList(QWidget):
    files_dropped = pyqtSignal(list)
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win; self.items = []
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx)
        self._vl = QVBoxLayout(self); self._vl.setContentsMargins(0,0,0,0); self._vl.setSpacing(0); self._vl.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, _):
        p = QPainter(self)
        for i in range(self.height() // 24 + 1):
            p.fillRect(0, i*24, self.width(), 24, QColor(ZEBRA_ODD if i%2 else ZEBRA_EVEN))

    def _ctx(self, pos):
        m = QMenu(self); a1 = QAction("Remove Selected", self); a1.triggered.connect(self.main_win.remove_selected)
        a2 = QAction("Clear Completed", self); a2.triggered.connect(self.main_win.remove_completed)
        m.addAction(a1); m.addAction(a2); m.exec(self.mapToGlobal(pos))

    def mousePressEvent(self, e):
        for it in self.items: it.set_selected(False)
        w = self.childAt(e.pos())
        while w and not isinstance(w, FileWidget): w = w.parent()
        if w: w.set_selected(True)
        self.update()

    def dragEnterEvent(self, e): e.acceptProposedAction() if e.mimeData().hasUrls() else None
    def dropEvent(self, e): self.files_dropped.emit([u.toLocalFile() for u in e.mimeData().urls()])

# ═══════════════════════════════════════════════════════════════
# UI: SETTINGS POPUP
# ═══════════════════════════════════════════════════════════════
class SettingsPanel(QDialog):
    def __init__(self, mw):
        super().__init__(mw, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.mw = mw; self.prefs = dict(mw.prefs)
        self.setStyleSheet(f"background:{SETTINGS_BG}; border:1px solid {BORDER_TOOLBAR}; border-radius:8px;")
        self._build()

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(15, 12, 15, 12); v.setSpacing(10)
        lbl = QLabel("Output Format:"); lbl.setStyleSheet("font-weight:bold; border:none;"); v.addWidget(lbl)
        self.cb_fmt = QComboBox(); self.cb_fmt.addItems(["mkv", "mp4"]); self.cb_fmt.setCurrentText(self.prefs["output_format"])
        v.addWidget(self.cb_fmt)
        self.chk_conv = QCheckBox("Convert to SRT"); self.chk_conv.setChecked(self.prefs["convert_srt"]); v.addWidget(self.chk_conv)
        self.chk_ext  = QCheckBox("Load External Subs"); self.chk_ext.setChecked(self.prefs["load_ext_subs"]); v.addWidget(self.chk_ext)
        btn = QPushButton("Done"); btn.clicked.connect(self._save); v.addWidget(btn)

    def _save(self):
        self.prefs.update({"output_format": self.cb_fmt.currentText(), "convert_srt": self.chk_conv.isChecked(), "load_ext_subs": self.chk_ext.isChecked()})
        save_prefs(self.prefs); self.mw.prefs = dict(self.prefs); self.close()

# ═══════════════════════════════════════════════════════════════
# UI: MAIN WINDOW
# ═══════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion"); self.resize(560, 420); self.prefs = load_prefs(); self.threads = []
        self._build_ui()

    def _build_ui(self):
        cw = QWidget(); self.setCentralWidget(cw); root = QVBoxLayout(cw); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        tb = QWidget(); tb.setFixedHeight(70); tb.setStyleSheet(f"background:{BG_TOOLBAR}; border-bottom:1px solid {BORDER_TOOLBAR};")
        th = QHBoxLayout(tb); th.setContentsMargins(15, 0, 10, 0)
        title = QLabel("Queue"); title.setStyleSheet("font-weight:bold; font-size:14px;"); th.addWidget(title); th.addStretch()
        self.btn_play = IconButton("play", "Start"); self.btn_set = IconButton("gear", "Settings"); self.btn_add = IconButton("tray_down", "Add")
        th.addWidget(self.btn_play); th.addWidget(self.btn_set); th.addWidget(self.btn_add)
        self.btn_add.clicked.connect(self.open_files); self.btn_play.clicked.connect(self.start_processing); self.btn_set.clicked.connect(self._toggle_settings)
        
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.Shape.NoFrame)
        self._queue = QueueList(self); self._queue.files_dropped.connect(self.add_to_list); sa.setWidget(self._queue)
        
        self._status = QLabel(" 0 items in queue"); self._status.setFixedHeight(24); self._status.setStyleSheet(f"background:{BG_FOOTER}; color:{TXT_SECONDARY}; border-top:1px solid {BORDER_FOOTER};")
        self._bar = QProgressBar(); self._bar.setFixedHeight(4); self._bar.setTextVisible(False); self._bar.setStyleSheet(f"QProgressBar{{background:{PROG_BG};border:none;}} QProgressBar::chunk{{background:{PROG_FG};}}")
        root.addWidget(tb); root.addWidget(sa); root.addWidget(self._bar); root.addWidget(self._status)

    def _toggle_settings(self):
        p = SettingsPanel(self); p.move(self.btn_set.mapToGlobal(QPoint(-70, 70))); p.exec()

    def open_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Select Videos"); self.add_to_list(fs)

    def add_to_list(self, fs):
        for f in fs:
            w = FileWidget(os.path.basename(f), self._queue); w.full_path = f
            self._queue.items.append(w); self._queue._vl.addWidget(w)
        self._status.setText(f" {len(self._queue.items)} items in queue")

    def remove_selected(self):
        for it in [i for i in self._queue.items if i.is_selected]: it.setParent(None); self._queue.items.remove(it)
        self._status.setText(f" {len(self._queue.items)} items in queue")

    def remove_completed(self):
        for it in [i for i in self._queue.items if i.status == "done"]: it.setParent(None); self._queue.items.remove(it)

    def start_processing(self):
        self.active = [i for i in self._queue.items if i.status == "waiting"]
        if self.active: self._next()

    def _next(self):
        if not self.active: return
        it = self.active.pop(0); it.set_status("working")
        t = ConversionThread(it.full_path, it, dict(self.prefs)); t.finished_signal.connect(self._done); self.threads.append(t); t.start()

    def _done(self, t):
        t.widget.set_status("done")
        dn = sum(1 for i in self._queue.items if i.status == "done")
        self._bar.setValue(int(dn / len(self._queue.items) * 100)); self._next()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("macos"); w = MainWindow(); w.show(); sys.exit(app.exec())
