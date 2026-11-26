"""Optional live lyrics window; LRCLIB lookup runs off the Qt thread."""
import bisect, json, re, subprocess, threading, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel

def parse_lrc(raw):
    result=[]
    for line in raw.splitlines():
        tags=list(re.finditer(r'\[(\d+):(\d+(?:\.\d+)?)\]',line))
        if tags:
            words=line[tags[-1].end():].strip()
            for tag in tags:
                result.append((int(tag[1])*60+float(tag[2]),words))
    return sorted(result)

class LyricsWindow(QDialog):
    def __init__(self,dashboard):
        super().__init__(dashboard)
        self.dashboard=dashboard
        self.setWindowTitle("Sakura • Live lyrics")
        self.resize(680,420)
        self.setWindowFlag(Qt.WindowType.Tool,True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.lock=threading.Lock()
        self.result=None
        self.stop=threading.Event()
        self.cache={}
        self.labels=[]
        layout=QVBoxLayout(self)
        for i in range(5):
            label=QLabel()
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label,1)
            self.labels.append(label)
        self.labels[2].setText("Finding lyrics…")
        self.timer=QTimer(self)
        self.timer.timeout.connect(self.render)
        self.timer.start(100)
        threading.Thread(target=self.worker,daemon=True).start()

    def worker(self):
        while not self.stop.is_set():
            try:
                def call(*args):
                    return subprocess.check_output(["playerctl","--player=spotify",*args],text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
                data=call("metadata","--format","{{title}}\n{{artist}}\n{{album}}\n{{mpris:length}}").splitlines()
                title,artist,album,length=data
                position=float(call("position"))
                playing=call("status")=="Playing"
                sampled=time.monotonic()
                key=(title,artist,album,length)
                if key not in self.cache:
                    query=urlencode(dict(track_name=title,artist_name=artist,album_name=album,duration=round(int(length)/1e6)))
                    try:
                        req=Request("https://lrclib.net/api/get?"+query,headers={"User-Agent":"Sakura-Dashboard/1.0 (live lyrics)"})
                        with urlopen(req,timeout=6) as response:
                            item=json.load(response)
                        self.cache[key]=parse_lrc(item.get("syncedLyrics") or "")
                    except Exception:
                        self.cache[key]=[]
                with self.lock:
                    self.result=(title,self.cache[key],position,sampled,playing)
            except (ValueError,OSError,subprocess.SubprocessError):
                with self.lock:self.result=None
            self.stop.wait(.5)

    def render(self):
        with self.lock:result=self.result
        accent=self.dashboard.theme_target().name()
        self.setStyleSheet("QDialog{background:#201329} QLabel{color:#bda8c6}")
        if not result:
            lines=["","","Waiting for local Spotify playback","",""]
        else:
            title,lyrics,position,sampled,playing=result
            if not lyrics:lines=["",title,"No synced lyrics available","",""]
            else:
                now=position+(min(1.5,time.monotonic()-sampled) if playing else 0)
                index=bisect.bisect_right([t for t,_ in lyrics],now)-1
                lines=[lyrics[j][1] if 0<=j<len(lyrics) else "" for j in range(index-2,index+3)]
        for i,label in enumerate(self.labels):
            label.setText(lines[i])
            label.setStyleSheet("font-size: 24px; font-weight: 600; color:"+accent if i==2 else "font-size: 16px; color:#bda8c6")

    def closeEvent(self,event):
        self.stop.set()
        self.timer.stop()
        super().closeEvent(event)
