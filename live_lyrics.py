"""Optional live lyrics window; LRCLIB lookup runs off the Qt thread."""
import bisect, json, re, subprocess, threading, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from PySide6.QtCore import QObject, Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen

def parse_lrc(raw):
    result=[]
    for line in raw.splitlines():
        tags=list(re.finditer(r'\[(\d+):(\d+(?:\.\d+)?)\]',line))
        if tags:
            words=line[tags[-1].end():].strip()
            for tag in tags:
                result.append((int(tag[1])*60+float(tag[2]),words))
    return sorted(result)

class LyricsWindow(QObject):
    def __init__(self,dashboard):
        super().__init__(dashboard)
        self.lock=threading.Lock()
        self.result=None
        self.stop=threading.Event()
        self.cache={}
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

    def current_frame(self):
        with self.lock:result=self.result
        if not result:
            return ["","Waiting for local Spotify playback",""], -1
        title,lyrics,position,sampled,playing=result
        if not lyrics:return [title,"No synced lyrics available",""], -1
        now=position+(min(1.5,time.monotonic()-sampled) if playing else 0)
        index=bisect.bisect_right([t for t,_ in lyrics],now)-1
        lines=[lyrics[j][1] if 0<=j<len(lyrics) else "" for j in range(index-1,index+2)]
        if index<0:return lines,-1
        start=lyrics[index][0]
        end=lyrics[index+1][0] if index+1<len(lyrics) else start+4
        words=lines[1].split()
        weights=[max(1,len(w)) for w in words]
        progress=max(0,min(.999,(now-start)/max(.2,end-start)))
        word=bisect.bisect_right([sum(weights[:i+1]) for i in range(len(weights))],progress*sum(weights))
        return lines,word if words else -1

    def current_lines(self):
        return self.current_frame()[0]

    def close(self):
        self.stop.set()
        self.deleteLater()

def paint_lyrics(p, model, rect, accent):
    """Render three lines without a panel border; highlight estimated active word."""
    if rect.width()<40 or rect.height()<40:return
    lines,active=model.current_frame()
    p.save()
    p.setClipRect(rect)
    width=rect.width()-20
    center=rect.center()
    size=max(12,min(32,int(width/15),int(rect.height()/8)))
    for i,line in enumerate(lines):
        if not line:continue
        f=QFont("Sans Serif")
        f.setPixelSize(size if i==1 else max(10,int(size*.65)))
        f.setBold(i==1)
        p.setFont(f)
        if i!=1:
            p.setPen(QColor("#a982b5"))
            yy=center.y()+(i-1)*rect.height()*.29
            p.drawText(QRectF(rect.x()+10,yy-size,width,size*2),Qt.AlignCenter|Qt.TextWordWrap,line)
            continue
        words=line.split()
        if not words:continue
        fm=p.fontMetrics()
        rows=[];row=[];used=0
        for j,word in enumerate(words):
            ww=fm.horizontalAdvance(word)
            if row and used+ww>width:
                rows.append(row);row=[];used=0
            row.append((j,word,ww));used+=ww+fm.horizontalAdvance(" ")
        if row:rows.append(row)
        while len(rows)*fm.height()>rect.height()*.46 and f.pixelSize()>10:
            f.setPixelSize(f.pixelSize()-1);p.setFont(f);fm=p.fontMetrics()
            rows=[];row=[];used=0
            for j,word in enumerate(words):
                ww=fm.horizontalAdvance(word)
                if row and used+ww>width:rows.append(row);row=[];used=0
                row.append((j,word,ww));used+=ww+fm.horizontalAdvance(" ")
            if row:rows.append(row)
        gap=fm.horizontalAdvance(" ")
        for ri,row in enumerate(rows):
            total=sum(w for _,_,w in row)+gap*(len(row)-1)
            x=center.x()-total/2
            y=center.y()-len(rows)*fm.height()/2+fm.ascent()+ri*fm.height()
            for j,word,ww in row:
                if j==active:
                    path=QPainterPath();path.addText(QPointF(x,y),f,word)
                    for radius,alpha in ((10,18),(7,30),(4,65)):
                        glow=QColor(accent);glow.setAlpha(alpha)
                        p.strokePath(path,QPen(glow,radius))
                    p.fillPath(path,QColor("#fff4fc"))
                else:
                    p.setPen(QColor(accent) if j<active else QColor("#e5d0e2"))
                    p.drawText(QPointF(x,y),word)
                x+=ww+gap
    p.restore()
