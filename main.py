import sys, os, subprocess, json, glob, re, shutil
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                                 QWidget, QLabel, QProgressBar, QScrollArea, 
                                 QFrame, QPushButton, QFileDialog, QMenu, QMessageBox)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPoint
    from PyQt6.QtGui import QPainter, QColor, QBrush, QAction, QKeySequence
except ImportError:
    sys.exit(1)

class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    
    def __init__(self, input_file, widget, load_external=True, output_format="mkv"):
        super().__init__()
        self.input_file = input_file
        self.widget = widget
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

    def convert_to_webvtt(self, srt_path, vtt_path):
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n")
                for line in lines:
                    f.write(line.replace(',', '.'))
            return True
        except: return False

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
                        end_time = parts[2].replace('.', ',') + "0"
                        text = parts[9].strip()
                        if "italic" in parts[3].lower() or "{\\i1}" in text:
                            text = self.clean_and_force_srt_italics(text)
                        else:
                            text = text.replace(r'\N', '\n').replace(r'\\N', '\n')
                            text = re.sub(r'\{[^\}]*\}', '', text).strip()
                        if text:
                            srt_content.append(f"{counter}\n0{start_time[:-1]} --> 0{end_time[:-1]}\n{text}\n\n")
                            counter += 1
            with open(srt_output_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(srt_content)
        except:
            ffmpeg = self.get_bin('ffmpeg')
            subprocess.run([ffmpeg, '-y', '-i', ass_path, srt_output_path], capture_output=True)

    def run(self):
        ffmpeg = self.get_bin('ffmpeg')
        ffprobe = self.get_bin('ffprobe')
        mp4box = self.get_bin('mp4box')
        
        base_path = os.path.splitext(self.input_file)[0]
        temp_dir = base_path + ".fusiontemp"
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        output_ext = "mp4" if self.output_format == "mp4_vtt" else "mkv"
        output_file = f"{base_path}_Fusion.{output_ext}"
        
        # Metadata ve Chapters okuma (MP4 için çıkartılıyor)
        try:
            probe_cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_chapters', self.input_file]
            info = json.loads(subprocess.check_output(probe_cmd))
        except: info = {}
        
        # MP4 formatında kaybolan bölümleri gömmek için txt dosyası oluşturuyoruz
        chapters = info.get('chapters', [])
        chap_file = os.path.join(temp_dir, 'chapters.txt')
        has_chaps = False
        if chapters:
            try:
                with open(chap_file, 'w', encoding='utf-8') as f:
                    for i, c in enumerate(chapters):
                        start_time = float(c.get('start_time', 0))
                        hours = int(start_time // 3600)
                        minutes = int((start_time % 3600) // 60)
                        seconds = start_time % 60
                        title = c.get('tags', {}).get('title', f"Chapter {i+1}")
                        f.write(f"{hours:02d}:{minutes:02d}:{seconds:06.3f} {title}\n")
                has_chaps = True
            except: pass
        
        internal_subs = [s for s in info.get('streams', []) if s.get('codec_type') == 'subtitle']
        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger","fr":"fra","es":"spa","it":"ita", "pt":"por", "ar":"ara"}
        
        cleaned_list = []
        for i, sub in enumerate(internal_subs):
            lang = sub.get('tags', {}).get('language', 'und')
            temp_srt = os.path.join(temp_dir, f"int_{i}.srt")
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", '-f', 'srt', temp_srt], capture_output=True)
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
            # Sadece video ve ses izini saf olarak çıkartıyoruz. Metadata ve chapter'ları tamamen engelliyoruz
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', '0:v:0', '-map', '0:a?', 
                           '-c', 'copy', '-tag:v', 'hvc1', '-sn', '-map_metadata', '-1', '-map_chapters', '-1', 
                           '-movflags', '+faststart', temp_mp4], capture_output=True)
            
            # MP4Box Başlangıç Komutları (Doğru sıralama)
            box_cmd = [mp4box, "-brand", "mp42", "-ab", "mp42"]
            
            # Video ve sesi ekle
            box_cmd.extend(["-add", f"{temp_mp4}#video", "-add", f"{temp_mp4}#audio"])
            
            # Altyazıları ekle: name= parametresindeki boşluk '@GPAC' çöpünü temizler
            for i, c in enumerate(cleaned_list):
                is_disabled = ":disable" if i > 0 else ""
                box_cmd.extend(["-add", f"{c['path']}:lang={c['lang']}:group=2:name= {is_disabled}"])
            
            # Bölümleri kesin ekle
            if has_chaps:
                box_cmd.extend(["-chap", chap_file])
            
            # Tereyağı sarma (Subler kalitesi) komutları en sona eklendi
            box_cmd.extend(["-ipod", "-tight", "-inter", "500", "-new", output_file])
            subprocess.run(box_cmd, capture_output=True)
        else:
            # MKV Modu
            cmd = [ffmpeg, '-y', '-i', self.input_file]
            for c in cleaned_list: cmd.extend(['-i', c['path']])
            cmd.extend(['-map', '0:v:0', '-map', '0:a?'])
            for i, c in enumerate(cleaned_list):
                cmd.extend(['-map', str(i + 1), f"-c:s:{i}", "subrip", f"-metadata:s:s:{i}", f"language={c['lang']}"])
            # -map_metadata:c 0:c -> Bölüm başlıklarını korur, diğer metadataları -1 ile siler
            cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '-1', '-map_metadata:c', '0:c', '-map_chapters', '0', output_file])
            subprocess.run(cmd, capture_output=True)

        if os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)
        self.finished_signal.emit(self)

class FileWidget(QFrame):
    def __init__(self, filename, parent_list):
        super().__init__()
        self.parent_list = parent_list; self.is_selected = False; self.status = "waiting"; self.setFixedHeight(30)
        self.layout = QHBoxLayout(self); self.layout.setContentsMargins(15, 0, 15, 0); self.status_icon = QLabel("○"); self.status_icon.setFixedWidth(20)
        self.name_label = QLabel(filename); self.layout.addWidget(self.status_icon); self.layout.addWidget(self.name_label); self.layout.addStretch(); self.update_style()
    def set_status(self, mode):
        self.status = mode; icons = {"working": "●", "done": "✓", "waiting": "○"}; colors = {"working": "#ff9500", "done": "#34c759", "waiting": "#8e8e93"}
        self.status_icon.setText(icons.get(mode, "○")); self.status_icon.setStyleSheet(f"color: {colors.get(mode, '#8e8e93')}; font-size: 14px;")
    def update_style(self):
        bg = "#007aff" if self.is_selected else "transparent"; txt = "white" if self.is_selected else "#111"
        self.setStyleSheet(f"background-color: {bg}; border-radius: 4px;"); self.name_label.setStyleSheet(f"color: {txt}; font-size: 13px;")

class SublerListWidget(QWidget):
    def __init__(self, main_window):
        super().__init__(); self.main_window = main_window; self.items = []; self.selection_start = None; self.selection_rect = QRect()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.customContextMenuRequested.connect(self.show_context_menu)
        self.layout = QVBoxLayout(self); self.layout.setContentsMargins(5, 5, 5, 5); self.layout.setSpacing(2); self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    def paintEvent(self, event):
        painter = QPainter(self); row_h = 30
        for i in range(0, (self.height() // row_h) + 1):
            if i % 2 == 1: painter.fillRect(0, i * row_h, self.width(), row_h, QBrush(QColor(245, 245, 247)))
        if not self.selection_rect.isNull():
            painter.setPen(QColor(0, 122, 255, 150)); painter.setBrush(QColor(0, 122, 255, 50)); painter.drawRect(self.selection_rect)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selection_start = event.pos()
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                for item in self.items: item.is_selected = False; item.update_style()
            self.update()
    def mouseMoveEvent(self, event):
        if self.selection_start:
            self.selection_rect = QRect(self.selection_start, event.pos()).normalized()
            for item in self.items: item.is_selected = self.selection_rect.intersects(item.geometry()); item.update_style()
            self.update()
    def mouseReleaseEvent(self, event): self.selection_start = None; self.selection_rect = QRect(); self.update()
    def show_context_menu(self, pos):
        menu = QMenu(self); act_rem = QAction("Remove selected", self); act_rem.setEnabled(any(i.is_selected for i in self.items))
        act_rem.triggered.connect(self.main_window.remove_selected); act_clear = QAction("Clear completed", self)
        act_clear.setEnabled(any(i.status == "done" for i in self.items)); act_clear.triggered.connect(self.main_window.remove_completed)
        menu.addAction(act_rem); menu.addAction(act_clear); menu.exec(self.mapToGlobal(pos))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.
