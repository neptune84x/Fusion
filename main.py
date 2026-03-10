class ConversionThread(QThread):
    finished_signal = pyqtSignal(object)
    def __init__(self, full_path, widget):
        super().__init__()
        self.full_path = full_path
        self.widget = widget

    def run(self):
        ffmpeg_path = get_resource_path('ffmpeg')
        base_no_ext = os.path.splitext(self.full_path)[0]
        output_file = f"{base_no_ext}_Fusion.mkv"
        
        # Giriş dosyalarını hazırla
        ext_subs = glob.glob(f"{base_no_ext}*.*")
        sub_inputs = [f for f in ext_subs if f.lower().endswith(('.srt', '.ass', '.vtt'))]
        
        cmd = [ffmpeg_path, '-i', self.full_path]
        for s in sub_inputs:
            cmd.extend(['-i', s])
            
        # MAP Ayarları
        cmd.extend(['-map', '0:v', '-map', '0:a', '-map', '0:s?']) # Orijinal video, ses ve varsa iç altyazılar
        for i in range(len(sub_inputs)):
            cmd.extend(['-map', f'{i+1}:s']) # Dışarıdan gelen her altyazıyı ekle

        # CODEC Ayarları (Tüm altyazıları SRT'ye zorla)
        cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'srt'])
        
        # CHAPTER KORUMA VE METADATA TEMİZLİĞİ
        cmd.extend(['-map_chapters', '0']) # Bölümleri koru
        cmd.extend(['-map_metadata', '-1']) # Global etiketleri (Judas vb.) temizle
        
        # DİL ETİKETLERİNİ TANIMLAMA
        # Dışarıdan gelen altyazılar 0:s'den sonraki indexlere yerleşir. 
        # Önce iç altyazıların dillerini koruyalım:
        cmd.extend(['-metadata:s:s', 'language=eng']) # Varsayılan olarak hepsini temizle/resetle
        
        # Dosya isminden dil analizi ve atama
        lang_map = {".tr": "tur", ".ru": "rus", ".en": "eng", ".jp": "jpn", ".de": "ger", ".fr": "fra"}
        
        for idx, sub_path in enumerate(sub_inputs):
            # FFmpeg'de track indexi: iç altyazı sayısı + idx şeklinde gider. 
            # Ancak en garanti yol 'metadata:s:s:{index}' kullanmaktır.
            assigned_lang = "eng" # Bulamazsa default
            for key, val in lang_map.items():
                if key in sub_path.lower():
                    assigned_lang = val
                    break
            
            # Bu altyazı kanalına dilini ve başlığını ata
            # Not: İç altyazıların üzerine binmemesi için genel bir loop yerine 
            # FFmpeg'in çıktı sırasına göre metadata ekliyoruz.
            cmd.extend([f'-metadata:s:s:{idx}', f'language={assigned_lang}'])

        cmd.extend(['-y', output_file])
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except: pass
        self.finished_signal.emit(self)
