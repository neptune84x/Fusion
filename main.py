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
# RENKLER
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
    return {k: s.value(k, v, type=type(v)) for k, v in DEFAULTS.items()}

def save_prefs(d):
    s = QSettings(ORG, APP)
    for k, v in d.items(): s.setValue(k, v)


# ═══════════════════════════════════════════════════════════════
# İŞLEME THREAD
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
        """ffmpeg komutunu sessizce çalıştırır."""
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
            out = []; n = 1
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
            with open(srt_path, 'r', encoding='utf-8') as f: c = f.read()
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n" + c.replace(',', '.'))
            return True
        except: return False

    def run(self):
        ffmpeg  = self.get_bin('ffmpeg')
        ffprobe = self.get_bin('ffprobe')
        mp4box  = self.get_bin('mp4box')
        prefs   = self.prefs

        base        = os.path.splitext(self.input_file)[0]
        tmp         = base + ".fusiontemp"
        if os.path.exists(tmp): shutil.rmtree(tmp)
        os.makedirs(tmp, exist_ok=True)
        try:
            subprocess.run(['chflags', 'hidden', tmp], capture_output=True)
        except: pass

        fmt         = prefs["output_format"]
        convert_srt = prefs["convert_srt"]
        load_ext    = prefs["load_ext_subs"]
        out_file    = f"{base}_Fusion.{'mp4' if fmt == 'mp4' else 'mkv'}"

        try:
            info = json.loads(subprocess.check_output(
                [ffprobe, '-v', 'quiet', '-print_format', 'json',
                 '-show_streams', '-show_chapters', self.input_file]
            ))
        except: info = {}

        chaps     = info.get('chapters', [])
        streams   = info.get('streams', [])
        vstream   = next((s for s in streams if s.get('codec_type') == 'video'), None)
        has_audio = any(s.get('codec_type') == 'audio' for s in streams)
        is_hevc   = vstream and vstream.get('codec_name') == 'hevc'
        int_subs  = [s for s in streams if s.get('codec_type') == 'subtitle']

        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger",
                 "fr":"fra","es":"spa","it":"ita","pt":"por","ar":"ara"}

        cleaned = []

        for i, sub in enumerate(int_subs):
            lang  = sub.get('tags', {}).get('language', 'und')
            codec = sub.get('codec_name', '')
            if fmt == "mp4":
                p = os.path.join(tmp, f"int_{i}.srt")
                self.run_ff(ffmpeg, '-y', '-i', self.input_file,
                            '-map', f"0:{sub['index']}", '-f', 'srt', p)
                if os.path.exists(p) and os.path.getsize(p) > 0:
                    vp = p.replace('.srt', '.vtt'); self.to_vtt(p, vp)
                    cleaned.append({'path': vp, 'lang': l_map.get(lang, lang), 'codec': 'vtt'})
            else:
                if not convert_srt and codec in ('ass', 'ssa', 'ass '):
                    p = os.path.join(tmp, f"int_{i}.ass")
                    self.run_ff(ffmpeg, '-y', '-i', self.input_file,
                                '-map', f"0:{sub['index']}", p)
                    if os.path.exists(p) and os.path.getsize(p) > 0:
                        cleaned.append({'path': p, 'lang': l_map.get(lang, lang), 'codec': 'ass'})
                else:
                    p = os.path.join(tmp, f"int_{i}.srt")
                    self.run_ff(ffmpeg, '-y', '-i', self.input_file,
                                '-map', f"0:{sub['index']}", '-f', 'srt', p)
                    if os.path.exists(p) and os.path.getsize(p) > 0:
                        cleaned.append({'path': p, 'lang': l_map.get(lang, lang), 'codec': 'srt'})

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
                    if os.path.exists(p) and os.path.getsize(p) > 0:
                        vp = p.replace('.srt', '.vtt'); self.to_vtt(p, vp)
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
                        if os.path.exists(p) and os.path.getsize(p) > 0:
                            cleaned.append({'path': p, 'lang': l_map.get(lang, lang), 'codec': 'srt'})

        has_ass = any(c['codec'] == 'ass' for c in cleaned)

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
                        t = (c.get('tags') or {}).get('title') or f"Chapter {c.get('id',0)}"
                        ff.write(f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{s%60:06.3f} {t}\n")
                box.extend(["-chap", chap_f])
            box.extend(["-ipod", out_file])
            subprocess.run(box, capture_output=True)

        # ── MKV modu — 2 AŞAMALI STRATEJİ ───────────────────
        else:
            # ── Fontları kaynak MKV'den fiziksel olarak çıkar ──
            # Doğru kullanım: -dump_attachment:t "" bir INPUT seçeneğidir.
            # Syntax: ffmpeg -dump_attachment:t "" -i INPUT -t 0 -f null null
            # Bu komut tüm attachment'ları filename tag'ine göre tmp dizinine yazar.
            font_list = []
            if has_ass and not convert_srt:
                att_streams = [s for s in streams if s.get('codec_type') == 'attachment']
                if att_streams:
                    font_dir = os.path.join(tmp, "fonts")
                    os.makedirs(font_dir, exist_ok=True)
                    # -dump_attachment:t "" → tüm attachment'ları filename tag'e göre çıkar
                    # Bu input seçeneği, -i'dan ÖNCE gelmelidir
                    dump_cmd = [
                        ffmpeg,
                        '-dump_attachment:t', '',   # boş string = filename tag'i kullan
                        '-i', self.input_file,
                        '-t', '0',                  # hiç video/audio işleme
                        '-f', 'null', '-'           # çıktıyı at
                    ]
                    # Çalışma dizinini font_dir olarak ayarla,
                    # böylece dosyalar oraya yazılır
                    subprocess.run(dump_cmd, capture_output=True, cwd=font_dir)

                    # Çıkarılan fontları listele ve metadata eşle
                    for s in att_streams:
                        tags  = s.get('tags', {})
                        fname = tags.get('filename', '')
                        mtype = tags.get('mimetype', 'application/x-truetype-font')
                        if not fname:
                            continue
                        fpath = os.path.join(font_dir, fname)
                        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                            font_list.append({
                                'path':     fpath,
                                'filename': fname,
                                'mimetype': mtype,
                            })

            # ── AŞAMA 1: Video + Ses + Altyazılar → geçici MKV ──
            # (chapter ve font YOK; dil kodları burada atanır)
            tmp_mkv = os.path.join(tmp, "stage1.mkv")
            cmd1 = [ffmpeg, '-y', '-i', self.input_file]
            for c in cleaned:
                cmd1.extend(['-i', c['path']])

            cmd1.extend(['-map', '0:v:0', '-map', '0:a?'])
            for i, c in enumerate(cleaned):
                cmd1.extend(['-map', f'{i+1}:0'])
                codec = 'copy' if c['codec'] == 'ass' else 'subrip'
                cmd1.extend([f'-c:s:{i}', codec])
                cmd1.extend([f'-metadata:s:s:{i}', f"language={c['lang']}"])

            cmd1.extend(['-c:v', 'copy', '-c:a', 'copy'])
            cmd1.extend(['-map_metadata', '-1', '-map_chapters', '-1'])
            cmd1.append(tmp_mkv)
            subprocess.run(cmd1, capture_output=True)

            # ── AŞAMA 2: geçici MKV + chapter + fontlar → final MKV ──
            # Girdi 0 = stage1.mkv  (A/V/Sub + dil kodları)
            # Girdi 1 = kaynak      (chapter bilgisi için)
            cmd2 = [ffmpeg, '-y', '-i', tmp_mkv, '-i', self.input_file]

            # stage1'deki tüm stream'leri al (dil kodları korunur)
            cmd2.extend(['-map', '0'])
            # Codec: hepsini kopyala
            cmd2.extend(['-c', 'copy'])
            # Global metadata temizle, chapter'ları kaynaktan al
            cmd2.extend(['-map_metadata', '-1'])
            cmd2.extend(['-map_chapters', '1'])   # input 1 = kaynak = chapter sahibi

            # Fontları tek tek -attach ile ekle
            # -attach bir OUTPUT seçeneğidir, doğru yerde kullanılıyor
            # Attachment stream sayısı = map 0'daki stream sayısı sonrası başlar
            for idx, font in enumerate(font_list):
                cmd2.extend(['-attach', font['path']])
                cmd2.extend([f'-metadata:s:t:{idx}', f"mimetype={font['mimetype']}"])
                cmd2.extend([f'-metadata:s:t:{idx}', f"filename={font['filename']}"])

            cmd2.append(out_file)
            subprocess.run(cmd2, capture_output=True)

        shutil.rmtree(tmp, ignore_errors=True)
        self.finished_signal.emit(self)


# ═══════════════════════════════════════════════════════════════
# TOOLBAR BUTON
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

    def enterEvent(self, e): self._hover = True;  self.update()
    def leaveEvent(self, e): self._hover = False; self.update()
    def mousePressEvent(self, e):
        self._press = True;  self.update(); super().mousePressEvent(e)
    def mouseReleaseEvent(self, e):
        self._press = False; self.update(); super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        lbl_h = 16
        icon_h = H - lbl_h
        circle_r = 22.0
        cx = W / 2.0
        cy = max(circle_r + 2.0, icon_h / 2.0)
        alpha = 22 + (30 if self._press else (15 if self._hover else 0))
        p.setBrush(QBrush(QColor(0, 0, 0, alpha)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), circle_r, circle_r)
        ink = QColor(TXT_PRIMARY)

        if self._type == "play":
            p.setBrush(QBrush(ink)); p.setPen(Qt.PenStyle.NoPen)
            hs = 9.0
            path = QPainterPath()
            path.moveTo(cx - 6.0 + 1.5, cy - hs)
            path.lineTo(cx - 6.0 + 1.5, cy + hs)
            path.lineTo(cx + 8.0, cy)
            path.closeSubpath()
            p.drawPath(path)
        elif self._type == "gear":
            p.save(); p.translate(cx, cy)
            p.setBrush(QBrush(ink)); p.setPen(Qt.PenStyle.NoPen)
            R_out=9.5; R_body=7.0; R_hole=3.8; teeth=8
            tw=math.radians(11); step=math.radians(360/teeth)
            outer=QPainterPath(); first=True
            for i in range(teeth):
                base=math.radians(i*360/teeth)-math.pi/2
                a1=base-tw/2; a2=base+tw/2
                b1=base-step/2+tw/2; b2=base+step/2-tw/2
                for ang,r in [(b1,R_body),(a1,R_out),(a2,R_out),(b2,R_body)]:
                    pt=QPointF(r*math.cos(ang), r*math.sin(ang))
                    if first: outer.moveTo(pt); first=False
                    else: outer.lineTo(pt)
            outer.closeSubpath()
            hole=QPainterPath(); hole.addEllipse(QPointF(0,0),R_hole,R_hole)
            p.drawPath(outer.subtracted(hole)); p.restore()
        elif self._type == "tray_down":
            pen=QPen(ink,1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            dw=13.0; dh=15.0; dx=cx-dw/2-1.5; dy=cy-dh/2-1.0; corner=3.2
            doc=QPainterPath()
            doc.moveTo(dx,dy); doc.lineTo(dx+dw-corner,dy); doc.lineTo(dx+dw,dy+corner); doc.lineTo(dx+dw,dy+dh); doc.lineTo(dx,dy+dh); doc.lineTo(dx,dy); doc.closeSubpath()
            p.drawPath(doc)
            fold=QPainterPath()
            fold.moveTo(dx+dw-corner,dy); fold.lineTo(dx+dw-corner,dy+corner); fold.lineTo(dx+dw,dy+corner); p.drawPath(fold)
            bcx=dx+dw+2.5; bcy=dy+dh+1.0; br=5.0
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor(BG_TOOLBAR))); p.drawEllipse(QPointF(bcx,bcy),br+1.0,br+1.0)
            p.setBrush(QBrush(ink)); p.drawEllipse(QPointF(bcx,bcy),br,br)
            pp=QPen(QColor(BG_TOOLBAR),1.4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap)
            p.setPen(pp); p.setBrush(Qt.BrushStyle.NoBrush); pl=2.8
            p.drawLine(QPointF(bcx-pl,bcy),QPointF(bcx+pl,bcy))
            p.drawLine(QPointF(bcx,bcy-pl),QPointF(bcx,bcy+pl))

        p.setPen(QPen(ink)); p.setBrush(Qt.BrushStyle.NoBrush)
        f=QFont()
        if sys.platform=="darwin": f.setFamily(".AppleSystemUIFont")
        f.setPointSize(10); p.setFont(f)
        p.drawText(QRect(0,H-lbl_h,W,lbl_h), Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter, self._label)


# ═══════════════════════════════════════════════════════════════
# DOSYA SATIRI
# ═══════════════════════════════════════════════════════════════
class FileWidget(QFrame):
    ROW_H = 24
    def __init__(self, filename, queue_w):
        super().__init__()
        self.queue_w=queue_w; self.is_selected=False; self.status="waiting"
        self.setFixedHeight(self.ROW_H); self.setFrameShape(QFrame.Shape.NoFrame)
        hl=QHBoxLayout(self); hl.setContentsMargins(10,0,10,0); hl.setSpacing(7)
        self._dot=QLabel("●"); self._dot.setFixedWidth(12)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        df=QFont(); df.setPointSize(7); self._dot.setFont(df)
        self._name=QLabel(filename)
        nf=QFont()
        if sys.platform=="darwin": nf.setFamily(".AppleSystemUIFont")
        nf.setPointSize(12); self._name.setFont(nf)
        hl.addWidget(self._dot); hl.addWidget(self._name); hl.addStretch()
        self._refresh()

    def set_status(self,m): self.status=m; self._refresh()
    def set_selected(self,v): self.is_selected=v; self._refresh()
    def _refresh(self):
        dot_c={"waiting":DOT_WAITING,"working":DOT_WORKING,"done":DOT_DONE}.get(self.status,DOT_WAITING)
        if self.is_selected:
            self.setStyleSheet(f"background:{SEL_BG}; border-radius:3px;")
            self._name.setStyleSheet(f"color:{SEL_TXT};")
            self._dot.setStyleSheet("color:rgba(255,255,255,200);")
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
        self.main_win=main_win; self.items=[]
        self._sel_start=None; self._sel_rect=QRect()
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self.setMinimumHeight(200)
        self._vl=QVBoxLayout(self); self._vl.setContentsMargins(0,0,0,0); self._vl.setSpacing(0); self._vl.setAlignment(Qt.AlignmentFlag.AlignTop)

    def paintEvent(self,_):
        p=QPainter(self)
        for i in range(self.height()//self.ROW_H+2):
            c=QColor(ZEBRA_ODD) if i%2==1 else QColor(ZEBRA_EVEN)
            p.fillRect(0,i*self.ROW_H,self.width(),self.ROW_H,c)
        if not self._sel_rect.isNull():
            p.setPen(QPen(QColor(21,96,212,180),1)); p.setBrush(QBrush(QColor(21,96,212,35))); p.drawRect(self._sel_rect)

    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._sel_start=e.pos()
            if not(e.modifiers()&Qt.KeyboardModifier.ControlModifier):
                for it in self.items: it.set_selected(False)
            self.update()

    def mouseMoveEvent(self,e):
        if self._sel_start:
            self._sel_rect=QRect(self._sel_start,e.pos()).normalized()
            for it in self.items: it.set_selected(self._sel_rect.intersects(it.geometry()))
            self.update()

    def mouseReleaseEvent(self,e): self._sel_start=None; self._sel_rect=QRect(); self.update()
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self,e): self.files_dropped.emit([u.toLocalFile() for u in e.mimeData().urls()])

    def _ctx_menu(self, pos):
        m = QMenu(self.main_win)
        m.setStyleSheet("QMenu { background: white; border: 1px solid #c8c8c8; border-radius: 6px; padding: 4px 0px; } QMenu::item { padding: 5px 20px; font-size: 13px; color: #1d1d1f; background: transparent; } QMenu::item:selected { background: #1560d4; color: white; border-radius: 4px; }")
        a_rem = QAction("Remove Selected", m); a_rem.setEnabled(any(it.is_selected for it in self.items)); a_rem.triggered.connect(self.main_win.remove_selected)
        a_clr = QAction("Clear Completed", m); a_clr.setEnabled(any(it.status == "done" for it in self.items)); a_clr.triggered.connect(self.main_win.remove_completed)
        m.addAction(a_rem); m.addAction(a_clr); m.exec(self.mapToGlobal(pos))


# ═══════════════════════════════════════════════════════════════
# SETTINGS POPUP
# ═══════════════════════════════════════════════════════════════
class SettingsPanel(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win, Qt.WindowType.Dialog|Qt.WindowType.FramelessWindowHint|Qt.WindowType.NoDropShadowWindowHint)
        self.mw=main_win; self.prefs=dict(main_win.prefs)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,False)
        self._build(); self.adjustSize()

    def paintEvent(self,_):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path=QPainterPath(); path.addRoundedRect(QRectF(self.rect()),10,10)
        p.fillPath(path,QBrush(QColor(SETTINGS_BG)))
        p.setPen(QPen(QColor("#b0b0b8"),0.6)); p.drawPath(path)

    def event(self,e):
        if e.type()==QEvent.Type.WindowDeactivate: self.hide()
        return super().event(e)

    def _font(self,size=12,bold=False):
        f=QFont()
        if sys.platform=="darwin": f.setFamily(".AppleSystemUIFont")
        f.setPointSize(size)
        if bold: f.setBold(True)
        return f

    def _sep(self):
        fr=QFrame(); fr.setFrameShape(QFrame.Shape.HLine); fr.setFixedHeight(1); fr.setStyleSheet(f"background:{SECT_LINE}; border:none;")
        return fr

    def _section(self,text):
        lbl=QLabel(text); lbl.setFont(self._font(12,bold=True)); lbl.setStyleSheet(f"color:{TXT_PRIMARY};"); return lbl

    def _cb(self,text,key):
        cb=QCheckBox(text); cb.setFont(self._font(12)); cb.setChecked(self.prefs.get(key,False)); cb.toggled.connect(lambda _:self._save()); return cb

    def _save(self):
        fmt="mp4" if self.combo_fmt.currentIndex()==1 else "mkv"
        self.prefs["output_format"]=fmt; self.prefs["convert_srt"]=self.cb_conv.isChecked(); self.prefs["load_ext_subs"]=self.cb_ext.isChecked()
        self.cb_conv.setVisible(fmt=="mkv"); save_prefs(self.prefs); self.mw.prefs=dict(self.prefs)

    def _on_fmt(self): self._save(); self.adjustSize()

    def _build(self):
        root=QVBoxLayout(self); root.setContentsMargins(18,14,18,16); root.setSpacing(6)
        root.addWidget(self._section("Output Format:"))
        self.combo_fmt=QComboBox(); self.combo_fmt.setFont(self._font(12)); self.combo_fmt.addItems(["mkv","mp4"]); self.combo_fmt.setCurrentIndex(0 if self.prefs["output_format"]=="mkv" else 1); self.combo_fmt.setMinimumWidth(160)
        self.combo_fmt.setStyleSheet("QComboBox{border:1px solid #b8b8be;border-radius:5px;padding:2px 8px;background:white;color:#1d1d1f;min-height:24px;} QComboBox::drop-down{border:none;width:20px;} QComboBox QAbstractItemView{background:white;color:#1d1d1f;selection-background-color:#1560d4;selection-color:white;outline:none;}")
        self.combo_fmt.currentIndexChanged.connect(self._on_fmt)
        fmt_hl=QHBoxLayout(); fmt_hl.setContentsMargins(0,0,0,0); fmt_hl.addWidget(self.combo_fmt); fmt_hl.addStretch(); root.addLayout(fmt_hl)
        self.cb_conv=self._cb("Convert subtitles to SRT","convert_srt"); self.cb_conv.setVisible(self.prefs["output_format"]=="mkv"); root.addWidget(self.cb_conv)
        root.addSpacing(4); root.addWidget(self._sep()); root.addSpacing(4)
        root.addWidget(self._section("Subtitles:"))
        self.cb_ext=self._cb("Load external subtitles","load_ext_subs"); root.addWidget(self.cb_ext); root.addStretch()

    def sync(self,prefs):
        self.prefs=dict(prefs); self.combo_fmt.blockSignals(True); self.combo_fmt.setCurrentIndex(0 if prefs["output_format"]=="mkv" else 1); self.combo_fmt.blockSignals(False); self.cb_conv.setChecked(prefs["convert_srt"]); self.cb_conv.setVisible(prefs["output_format"]=="mkv"); self.cb_ext.setChecked(prefs["load_ext_subs"])


# ═══════════════════════════════════════════════════════════════
# ANA PENCERE
# ═══════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fusion"); self.resize(560,420); self.setMinimumSize(480,300); self.setAcceptDrops(True); self.prefs=load_prefs(); self.threads=[]; self.active_queue=[]; self._settings=None
        self._build_ui(); self._build_menu()

    def _build_ui(self):
        root=QVBoxLayout(); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        tb=QWidget(); tb.setFixedHeight(70); tb.setStyleSheet(f"background:{BG_TOOLBAR}; border-bottom:1px solid {BORDER_TOOLBAR};")
        tb_hl=QHBoxLayout(tb); tb_hl.setContentsMargins(12,0,6,0); tb_hl.setSpacing(0)
        title=QLabel("Queue"); tf=QFont()
        if sys.platform=="darwin": tf.setFamily(".AppleSystemUIFont")
        tf.setPointSize(13); tf.setBold(True); title.setFont(tf); title.setStyleSheet(f"color:{TXT_PRIMARY};")
        self.btn_start=IconButton("play","Start"); self.btn_settings=IconButton("gear","Settings"); self.btn_add=IconButton("tray_down","Add Item")
        tb_hl.addWidget(title); tb_hl.addStretch(); tb_hl.addWidget(self.btn_start); tb_hl.addWidget(self.btn_settings); tb_hl.addWidget(self.btn_add)
        self.btn_start.clicked.connect(self.start_processing); self.btn_settings.clicked.connect(self._toggle_settings); self.btn_add.clicked.connect(self.open_files)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); scroll.setStyleSheet(f"background:{BG_WIN};")
        self._queue=QueueList(self); self._queue.files_dropped.connect(self.add_to_list); scroll.setWidget(self._queue)
        footer=QWidget(); footer.setFixedHeight(24); footer.setStyleSheet(f"background:{BG_FOOTER}; border-top:1px solid {BORDER_FOOTER};")
        f_hl=QHBoxLayout(footer); f_hl.setContentsMargins(10,0,10,0); f_hl.setSpacing(0)
        self._status_lbl=QLabel("0 items in queue.")
        sf=QFont()
        if sys.platform=="darwin": sf.setFamily(".AppleSystemUIFont")
        sf.setPointSize(11); self._status_lbl.setFont(sf); self._status_lbl.setStyleSheet(f"color:{TXT_SECONDARY};")
        self._progress=QProgressBar(); self._progress.setFixedSize(130,5); self._progress.setTextVisible(False); self._progress.setValue(0); self._progress.setStyleSheet(f"QProgressBar{{background:{PROG_BG};border-radius:2px;border:none;}} QProgressBar::chunk{{background:{PROG_FG};border-radius:2px;}}")
        f_hl.addWidget(self._status_lbl); f_hl.addStretch(); f_hl.addWidget(self._progress); root.addWidget(tb); root.addWidget(scroll); root.addWidget(footer)
        cw=QWidget(); cw.setLayout(root); cw.setStyleSheet(f"background:{BG_WIN};"); self.setCentralWidget(cw)

    def _build_menu(self):
        mb=self.menuBar(); app_m=mb.addMenu("Fusion")
        a_about=QAction("About Fusion",self); a_about.triggered.connect(self._about)
        a_quit=QAction("Quit Fusion",self); a_quit.setShortcut(QKeySequence("Ctrl+Q")); a_quit.triggered.connect(self.close)
        app_m.addAction(a_about); app_m.addSeparator(); app_m.addAction(a_quit)
        file_m=mb.addMenu("File")
        a_add=QAction("Add to Queue…",self); a_add.setShortcut(QKeySequence("Ctrl+O")); a_add.triggered.connect(self.open_files)
        a_rem=QAction("Remove Selected",self); a_rem.setShortcut(QKeySequence("Backspace")); a_rem.triggered.connect(self.remove_selected)
        a_clr=QAction("Clear Completed",self); a_clr.triggered.connect(self.remove_completed)
        file_m.addAction(a_add); file_m.addSeparator(); file_m.addAction(a_rem); file_m.addAction(a_clr)
        q_m=mb.addMenu("Queue"); a_st=QAction("Start",self); a_st.setShortcut(QKeySequence("Ctrl+Return")); a_st.triggered.connect(self.start_processing); q_m.addAction(a_st)

    def _toggle_settings(self):
        if self._settings is None: self._settings=SettingsPanel(self)
        if self._settings.isVisible(): self._settings.hide(); return
        self._settings.sync(self.prefs); btn=self.btn_settings; gp=btn.mapToGlobal(QPoint(btn.width()//2,btn.height()+2)); sw=max(self._settings.sizeHint().width(),280); gp.setX(gp.x()-sw//2); self._settings.move(gp); self._settings.show(); self._settings.raise_(); self._settings.activateWindow()

    def mousePressEvent(self,e):
        if self._settings and self._settings.isVisible(): self._settings.hide()
        super().mousePressEvent(e)

    def _about(self): QMessageBox.information(self,"About Fusion", "Fusion v0.3.1\n\nUniversal macOS video queue processor.\nMKV & MP4 · Subtitle muxing · Chapter preservation\n\nPowered by ffmpeg · ffprobe · MP4Box")
    def open_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,"Add Videos","", "Video Files (*.mkv *.mp4 *.avi *.mov *.ts *.m2ts);;All Files (*)")
        if paths: self.add_to_list(paths)
    def add_to_list(self,paths):
        for p in paths:
            w=FileWidget(os.path.basename(p),self._queue); w.full_path=p; self._queue._vl.addWidget(w); self._queue.items.append(w)
        self._refresh_status()
    def remove_completed(self):
        for it in [i for i in self._queue.items if i.status=="done"]: self._queue.items.remove(it); it.setParent(None)
        self._refresh_status()
    def remove_selected(self):
        for it in [i for i in self._queue.items if i.is_selected]: self._queue.items.remove(it); it.setParent(None)
        self._refresh_status()
    def _refresh_status(self):
        n=len(self._queue.items); self._status_lbl.setText(f"{n} item{'s' if n!=1 else ''} in queue.")
    def start_processing(self):
        self.active_queue=[i for i in self._queue.items if i.status=="waiting"]
        if self.active_queue: self._progress.setValue(0); self._process_next()
    def _process_next(self):
        if not self.active_queue: self._status_lbl.setText("Completed."); return
        item=self.active_queue.pop(0); item.set_status("working"); t=ConversionThread(item.full_path,item,dict(self.prefs)); t.finished_signal.connect(self._on_done); self.threads.append(t); t.start()
    def _on_done(self,t):
        t.widget.set_status("done"); done=sum(1 for i in self._queue.items if i.status=="done"); total=len(self._queue.items)
        if total: self._progress.setValue(int(done/total*100))
        self._process_next()
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self,e): self.add_to_list([u.toLocalFile() for u in e.mimeData().urls()])

if __name__=="__main__":
    app=QApplication(sys.argv); app.setApplicationName(APP); app.setOrganizationName(ORG); app.setStyle("macos")
    f=QFont()
    if sys.platform=="darwin": f.setFamily(".AppleSystemUIFont")
    f.setPointSize(13); app.setFont(f); w=MainWindow(); w.show(); sys.exit(app.exec())
