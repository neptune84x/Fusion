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

    def clean_and_force_srt_italics(self, text):
        if not text: return ""
        # Temel temizlik ve italik zorlaması
        text = re.sub(r'\{\\i1\}|\\i1|<i>|<I>', '', text)
        text = re.sub(r'\{\\i0\}|\\i0|</i>|</I>', '', text)
        text = re.sub(r'\{[^\}]*\}', '', text)
        return f"<i>{text.strip()}</i>"

    def convert_to_webvtt(self, srt_path, vtt_path):
        """SRT dosyasını WebVTT formatına dönüştürür."""
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n")
                for line in lines:
                    # SRT zaman damgasını (,) WebVTT damgasına (.) çevirir
                    f.write(line.replace(',', '.'))
            return True
        except:
            return False

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
                        style = parts[3]
                        text = parts[9].strip()
                        if "italic" in style.lower() or "{\\i1}" in text:
                            text = self.clean_and_force_srt_italics(text)
                        else:
                            text = re.sub(r'\{[^\}]*\}', '', text).strip()
                        if text:
                            srt_content.append(f"{counter}\n0{start_time[:-1]} --> 0{end_time[:-1]}\n{text}\n\n")
                            counter += 1
            with open(srt_output_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(srt_content)
        except:
            ffmpeg = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
            subprocess.run([ffmpeg, '-y', '-i', ass_path, srt_output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(self):
        ffmpeg = os.path.join(sys._MEIPASS, 'ffmpeg') if hasattr(sys, '_MEIPASS') else 'ffmpeg'
        ffprobe = os.path.join(sys._MEIPASS, 'ffprobe') if hasattr(sys, '_MEIPASS') else 'ffprobe'
        base_path = os.path.splitext(self.input_file)[0]
        temp_dir_path = base_path + ".fusiontemp"
        if os.path.exists(temp_dir_path): shutil.rmtree(temp_dir_path)
        os.makedirs(temp_dir_path, exist_ok=True)
        
        output_ext = "mp4" if self.output_format == "mp4_vtt" else self.output_format
        output_file = f"{base_path}_Fusion.{output_ext}"
        
        try:
            probe_cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_streams', self.input_file]
            info = json.loads(subprocess.check_output(probe_cmd))
        except: info = {}
        
        internal_subs = []
        for s in info.get('streams', []):
            if s.get('codec_type') == 'subtitle':
                lang = s.get('tags', {}).get('language', 'und')
                internal_subs.append({'index': s['index'], 'lang': lang})
        
        cleaned_list = []
        for i, sub in enumerate(internal_subs):
            temp_srt = os.path.join(temp_dir_path, f"int_{i}.srt")
            subprocess.run([ffmpeg, '-y', '-i', self.input_file, '-map', f"0:{sub['index']}", '-f', 'srt', temp_srt], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            final_sub = temp_srt
            if self.output_format == "mp4_vtt":
                temp_vtt = temp_srt.replace('.srt', '.vtt')
                if self.convert_to_webvtt(temp_srt, temp_vtt):
                    final_sub = temp_vtt
            
            cleaned_list.append({'path': final_sub, 'lang': sub['lang']})
            
        if self.load_external:
            for f in glob.glob(base_path + "*.*"):
                ext_check = f.lower()
                if (ext_check.endswith('.srt') or ext_check.endswith('.ass')) and f != self.input_file:
                    temp_srt = os.path.join(temp_dir_path, f"ext_{len(cleaned_list)}.srt")
                    if ext_check.endswith('.ass'): self.process_ass_to_srt_with_italics(f, temp_srt)
                    else: shutil.copy2(f, temp_srt)
                    
                    final_sub = temp_srt
                    if self.output_format == "mp4_vtt":
                        temp_vtt = temp_srt.replace('.srt', '.vtt')
                        self.convert_to_webvtt(temp_srt, temp_vtt)
                        final_sub = temp_vtt
                    
                    match = re.search(r'\.([a-z]{2,3})\.(?:srt|ass)$', ext_check)
                    cleaned_list.append({'path': final_sub, 'lang': match.group(1) if match else 'und'})

        cmd = [ffmpeg, '-y', '-i', self.input_file]
        for c in cleaned_list: cmd.extend(['-i', c['path']])
        
        cmd.extend(['-map', '0:v', '-map', '0:a?'])
        l_map = {"tr":"tur","en":"eng","ru":"rus","jp":"jpn","de":"ger","fr":"fra","es":"spa","it":"ita"}
        
        # Format bazlı codec belirleme
        for i, c in enumerate(cleaned_list):
            cmd.extend(['-map', str(i + 1)])
            if self.output_format == "mp4_vtt":
                # MP4 içinde WebVTT'yi 'webvtt' olarak işaretle
                cmd.extend([f"-c:s:{i}", "webvtt"])
            else:
                cmd.extend([f"-c:s:{i}", "subrip"])
            
            cmd.extend([f"-metadata:s:s:{i}", f"language={l_map.get(c['lang'], c['lang'])}", f"-metadata:s:s:{i}", "title="])
            
        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '-1', '-map_chapters', '0', output_file])
        
        # MP4/WebVTT için FFmpeg bazen özel bir 'strict' flag isteyebilir
        if self.output_format == "mp4_vtt":
            cmd.insert(-1, "-strict")
            cmd.insert(-1, "-2")
            
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(temp_dir_path): shutil.rmtree(temp_dir_path, ignore_errors=True)
        self.finished_signal.emit(self)

# (GUI sınıfları: FileWidget, SublerListWidget, MainWindow bölümleri aynı kalıyor...)
# Sadece MainWindow içindeki show_settings_menu kısmını güncellemelisin:

    def show_settings_menu(self):
        menu = QMenu(self)
        act_sub = QAction("Load External Subtitles", self, checkable=True); act_sub.setChecked(self.load_external_subs)
        act_sub.triggered.connect(lambda s: setattr(self, 'load_external_subs', s))
        menu.addAction(act_sub)
        menu.addSeparator()
        
        fmt_group = QMenu("Output Format", self)
        a_mkv = QAction("Matroska (.mkv)", self, checkable=True); a_mkv.setChecked(self.output_format == "mkv")
        a_mp4vtt = QAction("Apple MP4 (WebVTT)", self, checkable=True); a_mp4vtt.setChecked(self.output_format == "mp4_vtt")
        
        def set_fmt(f):
            self.output_format = f
            a_mkv.setChecked(f == "mkv")
            a_mp4vtt.setChecked(f == "mp4_vtt")
            
        a_mkv.triggered.connect(lambda: set_fmt("mkv"))
        a_mp4vtt.triggered.connect(lambda: set_fmt("mp4_vtt"))
        
        fmt_group.addAction(a_mkv); fmt_group.addAction(a_mp4vtt)
        menu.addMenu(fmt_group)
        menu.exec(self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height())))
