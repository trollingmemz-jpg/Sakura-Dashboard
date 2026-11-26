"""Optional live lyrics window; LRCLIB lookup runs off the Qt thread."""
import bisect, json, re, subprocess, threading, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from PySide6.QtCore import QObject, Qt, QRectF
from PySide6.QtGui import QColor, QFont

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
        self.media=dashboard.media
        self.lock=threading.Lock()
        self.result=None
        self.stop=threading.Event()
        self.cache={}
        threading.Thread(target=self.worker,daemon=True).start()

    def worker(self):
        while not self.stop.is_set():
            try:
                data=self.media.state
                title,artist,album=data.get('title',''),data.get('artist',''),data.get('album','')
                length=round(float(data.get('duration',0))*1e6)
                if not title or length<=0:raise ValueError('No timed media')
                position=float(data.get('position',0))
                playing=bool(data.get('playing'))
                sampled=data.get('sampled',time.monotonic())
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
        if not result:return None,["Waiting for timed Windows media playback"],0
        title,lyrics,position,sampled,playing=result
        if not lyrics:return None,["No synced lyrics available"],0
        now=position+(min(1.5,time.monotonic()-sampled) if playing else 0)
        index=bisect.bisect_right([t for t,_ in lyrics],now)-1
        return (title,id(lyrics)),[line for _,line in lyrics],index

    def close(self):
        self.stop.set()
        self.deleteLater()

def paint_lyrics(p, model, rect, accent):
    """Smoothly scroll between timestamped lines, without word effects."""
    if rect.width()<40 or rect.height()<40:return
    key,lines,index=model.current_frame()
    now=time.monotonic()
    old=getattr(model,"_scroll",None)
    if old is None or old[0]!=key or abs(index-old[1])>2:
        old=(key,index,float(index),now)
    elif index!=old[1]:
        t=min(1.,(now-old[3])/.38)
        eased=t*t*(3-2*t)
        old=(key,index,old[2]+(old[1]-old[2])*eased,now)
    model._scroll=old
    t=min(1.,(now-old[3])/.38)
    center=old[2]+(index-old[2])*t*t*(3-2*t)
    p.save()
    p.setClipRect(rect)
    spacing=rect.height()/3.1
    for j in range(max(0,int(center)-2),min(len(lines),int(center)+4)):
        distance=abs(j-center)
        strength=max(0.,1-distance)
        opacity=max(0.,min(1.,(1.55-distance)*1.5))
        if not opacity:continue
        f=QFont("Sans Serif")
        f.setPixelSize(max(10,int(min(32,spacing*.38)*( .72+.28*strength))))
        f.setBold(strength>.5)
        p.setFont(f)
        muted=QColor("#a982b5")
        color=QColor(round(muted.red()+(accent.red()-muted.red())*strength),round(muted.green()+(accent.green()-muted.green())*strength),round(muted.blue()+(accent.blue()-muted.blue())*strength))
        color.setAlphaF(opacity)
        p.setPen(color)
        y=rect.center().y()+(j-center)*spacing
        p.drawText(QRectF(rect.x()+8,y-spacing/2,rect.width()-16,spacing),Qt.AlignCenter|Qt.TextWordWrap,lines[j])
    p.restore()
