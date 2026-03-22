"""
Fusion — Subler-inspired macOS video queue processor
"""
import sys, os, subprocess, json, glob, re, shutil, math

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
        QWidget, QLabel, QProgressBar, QScrollArea, QFrame,
        QPushButton, QFileDialog, QMenu, QMessageBox,
        QDialog, QCheckBox, QComboBox, QSizePolicy, QSpacerItem,
        QAbstractScrollArea
    )
    from PyQt6.QtCore  import (Qt, QThread, pyqtSignal, QRect, QPoint,
                               QSize, QSettings, QRectF, QPointF)
    from PyQt6.QtGui   import (QPainter, QColor, QBrush, QPen, QAction,
                               QKeySequence, QFont, QPainterPath,
                               QLinearGradient, QRadialGradient,
                               QTransform, QPolygonF, QRegion)
except ImportError:
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# RENK PALETİ
# ═══════════════════════════════════════════════════════════════
BG_WIN         = "#ffffff"
BG_TOOLBAR     = "#f5f5f5"
BORDER_TOOLBAR = "#d0d0d0"
BG_FOOTER      = "#ececec"
BORDER_FOOTER  = "#c8c8c8"
ZEBRA_ODD      = "#f0f0f2"
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


# ═══════════════════════════════════════════════════════════════
# AYAR KAYIT
# ═══════════════════════════════════════════════════════════════
DEFAULTS = {
    "output_format":  "mkv",
    "convert_srt":    True,
    "load_ext_subs":  True,
    "clear_names":    True,
    "prettify_audio": True,
    "rename_chap":    False,
    "complete_lang":  False,
    "optimize":       True,
    "send_tv":        False,
    "autostart":      False,
    "notify_done":    True,
}

def load_prefs() -> dict:
    s = QSettings(ORG, APP)
    return {k: s.value(k, v, type=type(v)) for k, v in DEFAULTS.items()}

def save_prefs(d: dict):
    s = QSettings(ORG, APP)
    for k, v in d.items():
        s.setValue(k, v)


# ═══════════════════════════════════════════════════════════════
# İŞLEME THREAD
# ═══════════════════════════════════════════════════════════════
class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)

    def __init__(self, input_file, widget, prefs: dict):
        super().__init__()
        self.input_file = input_file
        self.widget     = widget
        self.prefs      = prefs

    def get_bin(self, name):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, "internal", name)
        return name

    # ── ASS → SRT dönüştürme ─────────────────────────────────
    def clean_and_force_srt_italics(self, text):
        if not text: return ""
        text = text.replace(r'\N', '\n').replace(r'\\N', '\n')
        text = re.sub(r'\{\\i1\}|\\i1|<i>|<I>', '', text)
        text = re.sub(r'\{\\i0\}|\\i0|</i>|</I>', '', text)
        text = re.sub(r'\{[^\}]*\}', '', text)
        return f"<i>{text.strip()}</i>"

    def process_ass_to_srt(self, ass_path, srt_path):
        try:
            with open(ass_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
            out = []; n = 1
            for line in lines:
                if not line.startswith("Dialogue:"): continue
                parts = line.split(',', 9)
                if len(parts) < 10: continue
                s = parts[1].replace('.', ',') + "0"
                e = parts[2].replace('.', ',') + "0"
                txt = parts[9].strip()
                if "italic" in parts[3].lower() or "{\\i1}" in txt:
                    txt = self.clean_and_force_srt_italics(txt)
                else:
                    txt = txt.replace(r'\N', '\n').replace(r'\\N', '\n')
                    txt = re.sub(r'\{[^\}]*\}', '', txt).strip()
                if txt:
                    out.append(f"{n}\n0{s[:-1]} --> 0{e[:-1]}\n{txt}\n\n")
                    n += 1
            with open(srt_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(out)
        except:
            subprocess.run(
                [self.get_bin('ffmpeg'), '-y', '-i', ass_path, srt_path],
                capture_output=True
            )

    def convert_to_webvtt(self, srt_path, vtt_path):
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

        base      = os.path.splitext(self.input_file)[0]
        tmp       = base + ".fusiontemp"
        if os.path.exists(tmp): shutil.rmtree(tmp)
        os.makedirs(tmp, exist_ok=True)

        fmt         = prefs["output_format"]
        convert_srt = prefs["convert_srt"]
        ext         = "mp4" if fmt == "mp4" else "mkv"
        out_file    = f"{base}_Fusion.{ext}"

        try:
            info = json.loads(subprocess.check_output(
                [ffprobe, '-v', 'quiet', '-print_format', 'json',
                 '-show_streams', '-show_chapters', self.input_file]
            ))
        except:
            info = {}

        chaps     = info.get('chapters', [])
        streams   = info.get('streams', [])
        vstream   = next((s for s in streams if s.get('codec_type') == 'video'), None)
        has_audio = any(s.get('codec_type') == 'audio' for s in streams)
        is_hevc   = vstream and vstream.get('codec_name') == 'hevc'
        int_subs  = [s for s in streams if s.get('codec_type') == 'subtitle']

        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger",
                 "fr":"fra","es":"spa","it":"ita","pt":"por","ar":"ara"}

        # ── İç altyazıları çıkar ───────────────────────────────
        cleaned = []
        for i, sub in enumerate(int_subs):
            lang     = sub.get('tags', {}).get('language', 'und')
            tmp_srt  = os.path.join(tmp, f"int_{i}.srt")
            codec    = sub.get('codec_name', '')

            if fmt == "mp4":
                subprocess.run(
                    [ffmpeg, '-y', '-i', self.input_file,
                     '-map', f"0:{sub['index']}", '-f', 'srt', tmp_srt],
                    capture_output=True
                )
                if os.path.exists(tmp_srt) and os.path.getsize(tmp_srt) > 0:
                    tmp_vtt = tmp_srt.replace('.srt', '.vtt')
                    self.convert_to_webvtt(tmp_srt, tmp_vtt)
                    cleaned.append({'path': tmp_vtt, 'lang': l_map.get(lang, lang)})
            else:
                # mkv modu: convert_srt kapalıysa ve ass ise dokunma
                if not convert_srt and codec in ('ass', 'ssa'):
                    tmp_ass = os.path.join(tmp, f"int_{i}.ass")
                    subprocess.run(
                        [ffmpeg, '-y', '-i', self.input_file,
                         '-map', f"0:{sub['index']}", tmp_ass],
                        capture_output=True
                    )
                    if os.path.exists(tmp_ass) and os.path.getsize(tmp_ass) > 0:
                        cleaned.append({'path': tmp_ass, 'lang': l_map.get(lang, lang),
                                        'codec': 'ass'})
                else:
                    subprocess.run(
                        [ffmpeg, '-y', '-i', self.input_file,
                         '-map', f"0:{sub['index']}", '-f', 'srt', tmp_srt],
                        capture_output=True
                    )
                    if os.path.exists(tmp_srt) and os.path.getsize(tmp_srt) > 0:
                        cleaned.append({'path': tmp_srt, 'lang': l_map.get(lang, lang),
                                        'codec': 'srt'})

        # ── Dış altyazılar ────────────────────────────────────
        if prefs["load_ext_subs"]:
            for f in sorted(glob.glob(base + "*.*")):
                if not f.lower().endswith(('.srt', '.ass')): continue
                if f == self.input_file: continue
                is_ass = f.lower().endswith('.ass')
                match  = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', f.lower())
                lang   = match.group(1) if match else "und"

                if fmt == "mp4":
                    tmp_srt = os.path.join(tmp, f"ext_{len(cleaned)}.srt")
                    if is_ass: self.process_ass_to_srt(f, tmp_srt)
                    else:      shutil.copy2(f, tmp_srt)
                    if os.path.exists(tmp_srt) and os.path.getsize(tmp_srt) > 0:
                        tmp_vtt = tmp_srt.replace('.srt', '.vtt')
                        self.convert_to_webvtt(tmp_srt, tmp_vtt)
                        cleaned.append({'path': tmp_vtt, 'lang': l_map.get(lang, lang)})
                else:
                    if is_ass and not convert_srt:
                        dst = os.path.join(tmp, f"ext_{len(cleaned)}.ass")
                        shutil.copy2(f, dst)
                        cleaned.append({'path': dst, 'lang': l_map.get(lang, lang),
                                        'codec': 'ass'})
                    else:
                        tmp_srt = os.path.join(tmp, f"ext_{len(cleaned)}.srt")
                        if is_ass: self.process_ass_to_srt(f, tmp_srt)
                        else:      shutil.copy2(f, tmp_srt)
                        if os.path.exists(tmp_srt) and os.path.getsize(tmp_srt) > 0:
                            cleaned.append({'path': tmp_srt,
                                            'lang': l_map.get(lang, lang), 'codec': 'srt'})

        # ── MP4 modu ──────────────────────────────────────────
        if fmt == "mp4":
            tmp_mp4 = os.path.join(tmp, "video_pure.mp4")
            cmd = [ffmpeg, '-y', '-i', self.input_file, '-map', '0:v:0']
            if has_audio: cmd.extend(['-map', '0:a?'])
            cmd.extend(['-c', 'copy', '-sn', '-map_metadata', '-1',
                        '-movflags', '+faststart'])
            if is_hevc: cmd.extend(['-tag:v', 'hvc1'])
            cmd.append(tmp_mp4)
            subprocess.run(cmd, capture_output=True)

            box = [mp4box, "-brand", "mp42", "-ab", "isom",
                   "-new", "-tight", "-inter", "500"]
            box.extend(["-add", f"{tmp_mp4}#video:forcesync:name="])
            if has_audio: box.extend(["-add", f"{tmp_mp4}#audio:name="])
            for i, c in enumerate(cleaned):
                dis = ":disable" if i > 0 else ""
                box.extend(["-add", f"{c['path']}:lang={c['lang']}:group=2:name={dis}"])
            if chaps:
                chap_f = os.path.join(tmp, "chapters.txt")
                with open(chap_f, "w", encoding="utf-8") as ff:
                    for c in chaps:
                        s = float(c.get('start_time', 0))
                        t = c.get('tags', {}).get('title') or f"Chapter {c.get('id', 0)}"
                        ff.write(f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{s%60:06.3f} {t}\n")
                box.extend(["-chap", chap_f])
            box.extend(["-ipod", out_file])
            subprocess.run(box, capture_output=True)

        # ── MKV modu ──────────────────────────────────────────
        else:
            meta_f = os.path.join(tmp, "meta.txt")
            with open(meta_f, "w", encoding="utf-8") as ff:
                ff.write(";FFMETADATA1\n")
                for c in chaps:
                    ff.write("\n[CHAPTER]\nTIMEBASE=1/1000\n")
                    ff.write(f"START={int(float(c['start_time'])*1000)}\n")
                    ff.write(f"END={int(float(c['end_time'])*1000)}\n")
                    t = c.get('tags', {}).get('title') or f"Chapter {c.get('id', 0)}"
                    ff.write(f"title={t}\n")

            cmd = [ffmpeg, '-y', '-i', self.input_file]
            for c in cleaned: cmd.extend(['-i', c['path']])
            cmd.extend(['-i', meta_f])
            cmd.extend(['-map', '0:v:0', '-map', '0:a?'])

            ass_indices = []
            for i, c in enumerate(cleaned):
                cmd.extend(['-map', f'{i+1}:0'])
                if c.get('codec') == 'ass':
                    cmd.extend([f'-c:s:{i}', 'copy'])
                    ass_indices.append(i)
                else:
                    cmd.extend([f'-c:s:{i}', 'subrip'])
                cmd.extend([f'-metadata:s:s:{i}', f"language={c['lang']}"])

            # ASS font attachment'larını koru
            if ass_indices:
                cmd.extend(['-map', '0:t?'])

            cmd.extend(['-c:v', 'copy', '-c:a', 'copy',
                        '-map_metadata', '-1',
                        '-map_metadata', f'{len(cleaned)+1}',
                        out_file])
            subprocess.run(cmd, capture_output=True)

        shutil.rmtree(tmp, ignore_errors=True)
        self.finished_signal.emit(self)


# ═══════════════════════════════════════════════════════════════
# SF SYMBOLS TARZINDA VEKTÖREL İKON BUTON
# Subler'daki gibi: ikon üstte, etiket altında, hover arka planı
# ═══════════════════════════════════════════════════════════════
class IconButton(QPushButton):
    """QPainter ile çizilen SF-Symbols benzeri ikon butonlar."""

    # icon_type: "play" | "gear" | "tray_down"
    def __init__(self, icon_type: str, label: str, parent=None):
        super().__init__(parent)
        self._icon_type = icon_type
        self._label     = label
        self._hovered   = False
        self._pressed   = False
        self.setFixedSize(64, 58)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def enterEvent(self, e):
        self._hovered = True;  self.update()
    def leaveEvent(self, e):
        self._hovered = False; self.update()
    def mousePressEvent(self, e):
        self._pressed = True;  self.update(); super().mousePressEvent(e)
    def mouseReleaseEvent(self, e):
        self._pressed = False; self.update(); super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # hover / pressed arka plan
        if self._pressed:
            p.setBrush(QBrush(QColor(0, 0, 0, 30)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(2, 2, w-4, h-4, 6, 6)
        elif self._hovered:
            p.setBrush(QBrush(QColor(0, 0, 0, 15)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(2, 2, w-4, h-4, 6, 6)

        icon_color = QColor(TXT_PRIMARY)
        p.setBrush(QBrush(icon_color))
        p.setPen(Qt.PenStyle.NoPen)

        # ── ikon çiz ──────────────────────────────────────────
        cx = w / 2
        # ikon merkezi üstte, etiket aşağıda
        icon_y = 8
        icon_size = 22

        if self._icon_type == "play":
            # Dolu üçgen — Subler'daki ▶ gibi
            tri = QPainterPath()
            # Biraz sağa kaydırılmış (optik denge)
            tri.moveTo(cx - 7 + 2, icon_y + 2)
            tri.lineTo(cx - 7 + 2, icon_y + icon_size - 2)
            tri.lineTo(cx + icon_size/2 + 1, icon_y + icon_size/2)
            tri.closeSubpath()
            p.drawPath(tri)

        elif self._icon_type == "gear":
            # Dişli çark
            gx, gy = cx, icon_y + icon_size/2
            outer_r = icon_size / 2
            inner_r = outer_r * 0.55
            teeth   = 8
            p.save()
            p.translate(gx, gy)
            path = QPainterPath()
            for i in range(teeth * 2):
                angle = math.radians(i * 180 / teeth)
                r = outer_r if i % 2 == 0 else outer_r * 0.80
                tooth_w = math.radians(10)
                a1 = angle - tooth_w / 2
                a2 = angle + tooth_w / 2
                x1 = r * math.cos(a1); y1 = r * math.sin(a1)
                x2 = r * math.cos(a2); y2 = r * math.sin(a2)
                if i == 0: path.moveTo(x1, y1)
                else:      path.lineTo(x1, y1)
                path.lineTo(x2, y2)
            path.closeSubpath()
            # Ortadaki delik
            hole = QPainterPath()
            hole.addEllipse(QPointF(0, 0), inner_r, inner_r)
            final = path.subtracted(hole)
            p.drawPath(final)
            p.restore()

        elif self._icon_type == "tray_down":
            # Tepsi + aşağı ok — "tray.and.arrow.down" SF Symbol
            p.save()
            p.translate(cx - 11, icon_y)
            pen = QPen(icon_color, 1.8, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)

            # Tepsi kutusu (alt yarısı)
            box = QPainterPath()
            box.moveTo(0, 13)
            box.lineTo(0, 20)
            box.lineTo(22, 20)
            box.lineTo(22, 13)
            p.drawPath(box)

            # Sol ve sağ çentik
            p.drawLine(QPointF(0, 13), QPointF(5, 13))
            p.drawLine(QPointF(17, 13), QPointF(22, 13))

            # Ok gövdesi
            p.drawLine(QPointF(11, 0), QPointF(11, 12))

            # Ok ucu
            arr = QPainterPath()
            arr.moveTo(6, 7)
            arr.lineTo(11, 13)
            arr.lineTo(16, 7)
            p.drawPath(arr)
            p.restore()

        # ── etiket ────────────────────────────────────────────
        p.setPen(QPen(icon_color))
        f = QFont(".AppleSystemUIFont" if sys.platform == "darwin" else "Arial")
        f.setPointSize(10)
        p.setFont(f)
        lbl_rect = QRect(0, h - 18, w, 16)
        p.drawText(lbl_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self._label)


# ═══════════════════════════════════════════════════════════════
# DOSYA SATIRI
# ═══════════════════════════════════════════════════════════════
class FileWidget(QFrame):
    ROW_H = 22

    def __init__(self, filename: str, queue_w):
        super().__init__()
        self.queue_w     = queue_w
        self.is_selected = False
        self.status      = "waiting"
        self.setFixedHeight(self.ROW_H)
        self.setFrameShape(QFrame.Shape.NoFrame)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(10, 0, 10, 0)
        hl.setSpacing(7)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(12)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(); f.setPointSize(7); self._dot.setFont(f)

        self._name = QLabel(filename)
        f2 = QFont(); f2.setPointSize(12); self._name.setFont(f2)

        hl.addWidget(self._dot)
        hl.addWidget(self._name)
        hl.addStretch()
        self._refresh()

    def set_status(self, mode: str):
        self.status = mode; self._refresh()

    def set_selected(self, v: bool):
        self.is_selected = v; self._refresh()

    def _refresh(self):
        dot_c = {
            "waiting": DOT_WAITING,
            "working": DOT_WORKING,
            "done":    DOT_DONE,
        }.get(self.status, DOT_WAITING)

        if self.is_selected:
            self.setStyleSheet(f"background:{SEL_BG}; border-radius:3px;")
            self._name.setStyleSheet(f"color:{SEL_TXT};")
            self._dot.setStyleSheet("color:rgba(255,255,255,0.7);")
        else:
            self.setStyleSheet("background:transparent;")
            self._name.setStyleSheet(f"color:{TXT_PRIMARY};")
            self._dot.setStyleSheet(f"color:{dot_c};")


# ═══════════════════════════════════════════════════════════════
# KUYRUK LİSTESİ
# ═══════════════════════════════════════════════════════════════
class QueueList(QWidget):
    files_dropped = pyqtSignal(list)
    ROW_H = FileWidget.ROW_H

    def __init__(self, main_win):
        super().__init__()
        self.main_win   = main_win
        self.items      = []
        self._sel_start = None
        self._sel_rect  = QRect()
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self.setMinimumHeight(200)
        self.setStyleSheet(f"background:{BG_WIN};")
        self._vl = QVBoxLayout(self)
        self._vl.setContentsMargins(0, 0, 0, 0)
        self._vl.setSpacing(0)
        self._vl.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, _):
        p = QPainter(self)
        for i in range(self.height() // self.ROW_H + 2):
            c = QColor(ZEBRA_ODD) if i % 2 == 1 else QColor(ZEBRA_EVEN)
            p.fillRect(0, i * self.ROW_H, self.width(), self.ROW_H, c)
        if not self._sel_rect.isNull():
            p.setPen(QPen(QColor(21, 96, 212, 180), 1))
            p.setBrush(QBrush(QColor(21, 96, 212, 35)))
            p.drawRect(self._sel_rect)

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
        self._sel_start = None; self._sel_rect = QRect(); self.update()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        self.files_dropped.emit([u.toLocalFile() for u in e.mimeData().urls()])

    def _ctx_menu(self, pos):
        m = QMenu(self)
        a1 = QAction("Remove Selected", self)
        a1.setEnabled(any(i.is_selected for i in self.items))
        a1.triggered.connect(self.main_win.remove_selected)
        a2 = QAction("Clear Completed", self)
        a2.setEnabled(any(i.status == "done" for i in self.items))
        a2.triggered.connect(self.main_win.remove_completed)
        m.addAction(a1); m.addAction(a2)
        m.exec(self.mapToGlobal(pos))


# ═══════════════════════════════════════════════════════════════
# SETTINGS POPUP — macOS native görünümü, QSettings kalıcı
# ═══════════════════════════════════════════════════════════════
class SettingsPanel(QDialog):

    def __init__(self, main_win):
        super().__init__(main_win,
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint)
        self.mw      = main_win
        self.prefs   = load_prefs()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build()
        self.adjustSize()

    # ── panel çerçevesini çiz ─────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
        p.fillPath(path, QBrush(QColor(SETTINGS_BG)))
        p.setPen(QPen(QColor("#c0c0c6"), 0.5))
        p.drawPath(path)

    # ── ayarları kaydet ───────────────────────────────────────
    def _collect(self):
        self.prefs["load_ext_subs"]  = self.cb_ext.isChecked()
        self.prefs["clear_names"]    = self.cb_clear.isChecked()
        self.prefs["prettify_audio"] = self.cb_pretty.isChecked()
        self.prefs["rename_chap"]    = self.cb_rename.isChecked()
        self.prefs["complete_lang"]  = self.cb_comp.isChecked()
        self.prefs["optimize"]       = self.cb_opt.isChecked()
        self.prefs["send_tv"]        = self.cb_tv.isChecked()
        self.prefs["autostart"]      = self.cb_auto.isChecked()
        self.prefs["notify_done"]    = self.cb_notify.isChecked()
        fmt = "mp4" if self.combo_fmt.currentIndex() == 1 else "mkv"
        self.prefs["output_format"]  = fmt
        self.prefs["convert_srt"]    = self.cb_conv.isChecked()
        save_prefs(self.prefs)
        self.mw.prefs = self.prefs
        # MKV alt seçenek görünürlüğü
        self.cb_conv.setVisible(fmt == "mkv")

    def _on_fmt_change(self, idx):
        is_mkv = idx == 0
        self.cb_conv.setVisible(is_mkv)
        self._collect()
        self.adjustSize()

    # ── yardımcılar ───────────────────────────────────────────
    def _sep(self):
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"background:{SECT_LINE}; border:none;")
        f.setFixedHeight(1); return f

    def _cb(self, text, key):
        c = QCheckBox(text)
        f = QFont()
        if sys.platform == "darwin": f.setFamily(".AppleSystemUIFont")
        f.setPointSize(12); c.setFont(f)
        c.setChecked(self.prefs.get(key, False))
        c.toggled.connect(lambda _: self._collect())
        return c

    def _section(self, text):
        lbl = QLabel(text)
        f = QFont()
        if sys.platform == "darwin": f.setFamily(".AppleSystemUIFont")
        f.setPointSize(12); f.setBold(True); lbl.setFont(f)
        lbl.setStyleSheet(f"color:{TXT_PRIMARY};")
        return lbl

    def _combo(self, items):
        c = QComboBox()
        f = QFont()
        if sys.platform == "darwin": f.setFamily(".AppleSystemUIFont")
        f.setPointSize(12); c.setFont(f)
        c.addItems(items)
        c.setStyleSheet(f"""
            QComboBox {{
                border:1px solid #c0c0c6;
                border-radius:5px;
                padding:2px 8px;
                background:white;
                color:{TXT_PRIMARY};
                min-height:22px;
            }}
            QComboBox::drop-down {{ border:none; width:18px; }}
            QComboBox QAbstractItemView {{
                background:white;
                color:{TXT_PRIMARY};
                selection-background-color:{SEL_BG};
                selection-color:{SEL_TXT};
            }}
        """)
        return c

    # ── UI inşası ─────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(5)

        # ── Add item ─────────────────────────────────────────
        root.addWidget(self._section("Add item:"))
        self.cb_clear_meta = self._cb("Clear existing metadata", "clear_names")
        root.addWidget(self.cb_clear_meta)

        root.addSpacing(4); root.addWidget(self._sep()); root.addSpacing(4)

        # ── Output Format ────────────────────────────────────
        root.addWidget(self._section("Output Format:"))
        self.combo_fmt = self._combo(["MKV", "MP4"])
        self.combo_fmt.setCurrentIndex(0 if self.prefs["output_format"] == "mkv" else 1)
        self.combo_fmt.setMinimumWidth(180)
        self.combo_fmt.currentIndexChanged.connect(self._on_fmt_change)
        fmt_hl = QHBoxLayout(); fmt_hl.addWidget(self.combo_fmt); fmt_hl.addStretch()
        root.addLayout(fmt_hl)

        # MKV alt seçenek: Convert subtitles to SRT
        self.cb_conv = self._cb("    Convert subtitles to SRT", "convert_srt")
        self.cb_conv.setVisible(self.prefs["output_format"] == "mkv")
        root.addWidget(self.cb_conv)

        root.addSpacing(4); root.addWidget(self._sep()); root.addSpacing(4)

        # ── Checkboxlar ──────────────────────────────────────
        self.cb_ext    = self._cb("Load external subtitles",   "load_ext_subs")
        self.cb_clear  = self._cb("Clear tracks names",        "clear_names")
        self.cb_pretty = self._cb("Prettify audio track names","prettify_audio")
        self.cb_rename = self._cb("Rename chapters titles",    "rename_chap")
        self.cb_comp   = self._cb("Complete tracks language",  "complete_lang")
        for cb in [self.cb_ext, self.cb_clear, self.cb_pretty,
                   self.cb_rename, self.cb_comp]:
            root.addWidget(cb)

        root.addSpacing(4)

        # Optimize / Send to TV
        self.cb_opt = self._cb("Optimize", "optimize")
        self.cb_tv  = self._cb("Send to TV", "send_tv")
        root.addWidget(self.cb_opt)
        root.addWidget(self.cb_tv)

        root.addSpacing(4); root.addWidget(self._sep()); root.addSpacing(4)

        # ── Global options ───────────────────────────────────
        root.addWidget(self._section("Global options:"))
        self.cb_auto   = self._cb("Auto-Start the queue",         "autostart")
        self.cb_notify = self._cb("Show Notification When Done",  "notify_done")
        root.addWidget(self.cb_auto)
        root.addWidget(self.cb_notify)

    # ── Dışarı tıklandığında kapat ────────────────────────────
    def event(self, e):
        from PyQt6.QtCore import QEvent
        if e.type() == QEvent.Type.WindowDeactivate:
            self.hide()
        return super().event(e)


# ═══════════════════════════════════════════════════════════════
# ANA PENCERE
# ═══════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion")
        self.resize(560, 420)
        self.setMinimumSize(480, 300)
        self.setAcceptDrops(True)

        self.prefs         = load_prefs()
        self.threads       = []
        self.active_queue  = []
        self._settings_dlg = None

        self._build_ui()
        self._build_menu()

        # Autostart
        if self.prefs["autostart"]:
            self.start_processing()

    # ── UI ────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── TOOLBAR ───────────────────────────────────────────
        # Subler: başlık sola, butonlar sağa hizalı
        tb = QWidget()
        tb.setFixedHeight(66)
        tb.setStyleSheet(
            f"background:{BG_TOOLBAR};"
            f"border-bottom:1px solid {BORDER_TOOLBAR};"
        )
        tb_hl = QHBoxLayout(tb)
        tb_hl.setContentsMargins(8, 0, 4, 0)
        tb_hl.setSpacing(0)

        # Başlık etiketi — sola hizalı (Subler gibi)
        title = QLabel("Fusion")
        tf = QFont()
        if sys.platform == "darwin": tf.setFamily(".AppleSystemUIFont")
        tf.setPointSize(13); tf.setBold(True); title.setFont(tf)
        title.setStyleSheet(f"color:{TXT_PRIMARY};")

        self.btn_start    = IconButton("play",      "Start")
        self.btn_settings = IconButton("gear",      "Settings")
        self.btn_add      = IconButton("tray_down", "Add Item")

        # Subler düzeni: başlık sol | stretch | Start Settings Add Item sağda
        tb_hl.addWidget(title)
        tb_hl.addStretch()
        tb_hl.addWidget(self.btn_start)
        tb_hl.addWidget(self.btn_settings)
        tb_hl.addWidget(self.btn_add)

        self.btn_start.clicked.connect(self.start_processing)
        self.btn_settings.clicked.connect(self._toggle_settings)
        self.btn_add.clicked.connect(self.open_files)

        # ── SCROLL + KUYRUK ────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{BG_WIN};")
        self._queue = QueueList(self)
        self._queue.files_dropped.connect(self.add_to_list)
        scroll.setWidget(self._queue)

        # ── FOOTER ────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(24)
        footer.setStyleSheet(
            f"background:{BG_FOOTER};"
            f"border-top:1px solid {BORDER_FOOTER};"
        )
        f_hl = QHBoxLayout(footer)
        f_hl.setContentsMargins(10, 0, 10, 0)
        f_hl.setSpacing(0)

        self._status_lbl = QLabel("0 items in queue.")
        sf = QFont()
        if sys.platform == "darwin": sf.setFamily(".AppleSystemUIFont")
        sf.setPointSize(11); self._status_lbl.setFont(sf)
        self._status_lbl.setStyleSheet(f"color:{TXT_SECONDARY};")

        self._progress = QProgressBar()
        self._progress.setFixedSize(130, 5)
        self._progress.setTextVisible(False)
        self._progress.setValue(0)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background:{PROG_BG}; border-radius:2px; border:none;
            }}
            QProgressBar::chunk {{
                background:{PROG_FG}; border-radius:2px;
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
        cw.setStyleSheet(f"background:{BG_WIN};")
        self.setCentralWidget(cw)

    # ── MENÜ ─────────────────────────────────────────────────
    def _build_menu(self):
        mb = self.menuBar()

        app_m = mb.addMenu("Fusion")
        a_about = QAction("About Fusion", self)
        a_about.triggered.connect(self._about)
        a_quit  = QAction("Quit Fusion", self)
        a_quit.setShortcut(QKeySequence("Ctrl+Q"))
        a_quit.triggered.connect(self.close)
        app_m.addAction(a_about); app_m.addSeparator(); app_m.addAction(a_quit)

        file_m = mb.addMenu("File")
        a_add = QAction("Add to Queue…", self)
        a_add.setShortcut(QKeySequence("Ctrl+O"))
        a_add.triggered.connect(self.open_files)
        a_rem = QAction("Remove Selected", self)
        a_rem.setShortcut(QKeySequence("Backspace"))
        a_rem.triggered.connect(self.remove_selected)
        a_clr = QAction("Clear Completed", self)
        a_clr.triggered.connect(self.remove_completed)
        file_m.addAction(a_add); file_m.addSeparator()
        file_m.addAction(a_rem); file_m.addAction(a_clr)

        q_m = mb.addMenu("Queue")
        a_st = QAction("Start", self)
        a_st.setShortcut(QKeySequence("Ctrl+Return"))
        a_st.triggered.connect(self.start_processing)
        q_m.addAction(a_st)

    # ── Settings toggle ───────────────────────────────────────
    def _toggle_settings(self):
        if self._settings_dlg is None:
            self._settings_dlg = SettingsPanel(self)

        if self._settings_dlg.isVisible():
            self._settings_dlg.hide()
            return

        # Settings butonunun altına hizala
        btn  = self.btn_settings
        gpos = btn.mapToGlobal(QPoint(btn.width() // 2, btn.height() + 4))
        # Ortala
        dlg_w = self._settings_dlg.sizeHint().width()
        if dlg_w < 10: dlg_w = 300
        gpos.setX(gpos.x() - dlg_w // 2)
        self._settings_dlg.move(gpos)
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    # ── Ana pencere tıklaması ile settings kapat ──────────────
    def mousePressEvent(self, e):
        if self._settings_dlg and self._settings_dlg.isVisible():
            self._settings_dlg.hide()
        super().mousePressEvent(e)

    # ── About ────────────────────────────────────────────────
    def _about(self):
        QMessageBox.information(self, "About Fusion",
            "Fusion v0.2.0\n\nUniversal macOS video queue processor.\n"
            "MKV & MP4 · Subtitle muxing · Chapter preservation\n\n"
            "Powered by ffmpeg · ffprobe · MP4Box")

    # ── Dosya işlemleri ───────────────────────────────────────
    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Videos", "",
            "Video Files (*.mkv *.mp4 *.avi *.mov *.ts *.m2ts);;All Files (*)"
        )
        if paths: self.add_to_list(paths)

    def add_to_list(self, paths):
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
        self._status_lbl.setText(f"{n} item{'s' if n != 1 else ''} in queue.")
        # Dock badge (macOS)
        if sys.platform == "darwin":
            try:
                app = QApplication.instance()
                app.setProperty("badge", str(n) if n > 0 else "")
            except:
                pass

    # ── İşleme ───────────────────────────────────────────────
    def start_processing(self):
        self.active_queue = [i for i in self._queue.items if i.status == "waiting"]
        if self.active_queue:
            self._progress.setValue(0)
            self._process_next()

    def _process_next(self):
        if not self.active_queue:
            self._status_lbl.setText("Completed.")
            if self.prefs.get("notify_done"):
                QMessageBox.information(self, "Fusion", "Queue completed.")
            return
        item = self.active_queue.pop(0)
        item.set_status("working")
        t = ConversionThread(item.full_path, item, dict(self.prefs))
        t.finished_signal.connect(self._on_done)
        self.threads.append(t); t.start()

    def _on_done(self, t):
        t.widget.set_status("done")
        done  = sum(1 for i in self._queue.items if i.status == "done")
        total = len(self._queue.items)
        if total: self._progress.setValue(int(done / total * 100))
        self._process_next()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_to_list([u.toLocalFile() for u in e.mimeData().urls()])


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName(ORG)
    app.setStyle("macos")
    f = QFont()
    if sys.platform == "darwin": f.setFamily(".AppleSystemUIFont")
    f.setPointSize(13)
    app.setFont(f)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
