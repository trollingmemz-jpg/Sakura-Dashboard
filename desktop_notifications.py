"""Mirror freedesktop notifications without replacing KDE's notification service."""
import html
import re
import time
from collections import deque
from PySide6.QtCore import QObject, QProcess, Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen

class Notifications(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.history=deque(maxlen=100)
        self.pending=deque(maxlen=12)
        self.current=None
        self.started=0.
        self.dismissed=None
        self.hit=QRectF()
        self.enabled=True
        self.buffer=""
        self.fields=None
        self.process=QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.start("dbus-monitor",["--session","type='method_call',interface='org.freedesktop.Notifications',member='Notify'"])

    def read(self):
        self.buffer+=bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        lines=self.buffer.split("\n")
        self.buffer=lines.pop()
        for line in lines:
            if line.startswith("method call"):
                self.fields=[] if "member=Notify" in line else None
                continue
            if self.fields is None:continue
            m=re.match(r'^   string "(.*)"$',line)
            if m:
                value=m.group(1).replace(r'\n'," ").replace(r'\"','"')
                self.fields.append(value)
                if len(self.fields)==4:
                    app,icon,title,body=self.fields
                    self.fields=None
                    title=html.unescape(re.sub(r"<[^>]*>","",title))
                    body=html.unescape(re.sub(r"<[^>]*>","",body))
                    item=(app[:100],title[:240],body[:500],time.time())
                    self.history.appendleft(item)
                    if self.enabled:self.pending.append(item)
    def dismiss(self):
        if self.current and self.dismissed is None:self.dismissed=time.monotonic()
    def paint(self,p,rect,accent):
        now=time.monotonic()
        self.hit=QRectF()
        if not self.enabled:
            self.current=None;self.pending.clear();return
        if self.current and (self.dismissed is not None and now-self.dismissed>=.3):
            self.current=None
        if self.current is None and self.pending:
            self.current=self.pending.popleft();self.started=now;self.dismissed=None
        if self.current is None:return
        if now-self.started>=6 and self.dismissed is None:self.dismissed=now
        t=min(1.,(now-self.started)/.3)
        opacity=t*t*(3-2*t)
        if self.dismissed is not None:
            t=min(1.,(now-self.dismissed)/.3);opacity*=1-t*t*(3-2*t)
        app,title,body,_=self.current
        if rect.width()<72 or rect.height()<24:return
        # The supplied rectangle is the available layout slot, in widget pixels.
        height=min(rect.height(),max(48,min(100,rect.width()*.23)))
        width=min(rect.width(),max(height*2.5,min(560,rect.width())))
        full=QRectF(rect.center().x()-width/2,rect.center().y()-height/2,width,height)
        scale=max(.35,min(1.25,height/80,width/280))
        reveal=max(.01,opacity)
        capsule=QRectF(full.center().x()-width*reveal/2,full.center().y()-height*reveal/2,width*reveal,height*reveal)
        p.save();p.setOpacity(opacity)
        bg=QColor(round(24+accent.red()*.09),round(18+accent.green()*.09),round(32+accent.blue()*.09),242)
        p.setPen(Qt.NoPen);p.setBrush(bg)
        p.drawRoundedRect(capsule,capsule.height()/2,capsule.height()/2)
        clip=QPainterPath();clip.addRoundedRect(capsule,capsule.height()/2,capsule.height()/2)
        p.setClipPath(clip)
        inset=max(14,height*.32)
        x=full.right()-inset;y=full.center().y()
        text_width=max(1,full.width()-2*inset-24*scale)
        values=[(app,12,accent),(title,17,QColor("#f1ddec")),(body,13,QColor("#bba5c3"))]
        row=height*.25
        for i,(value,size,color) in enumerate(values):
            f=QFont("Sans Serif");f.setPixelSize(max(8,round(size*scale)));f.setBold(i==1);p.setFont(f);p.setPen(color)
            p.drawText(QRectF(full.left()+inset,full.top()+height*.125+i*row,text_width,row),Qt.AlignVCenter|Qt.AlignLeft,p.fontMetrics().elidedText(value,Qt.ElideRight,int(text_width)))
        p.save();p.translate(x,y);p.scale(scale,scale);p.rotate(35)
        petal=QPainterPath();petal.moveTo(0,9);petal.cubicTo(-11,-1,-8,-13,0,-8);petal.cubicTo(8,-13,11,-1,0,9);petal.closeSubpath()
        p.setBrush(Qt.NoBrush);p.setPen(QPen(accent,1.4));p.drawPath(petal);p.restore();p.restore()
        if opacity>.75:self.hit=QRectF(x-16*scale,y-16*scale,32*scale,32*scale)
    def visible(self):
        return self.enabled and bool(self.current or self.pending)
    def close(self):
        self.process.terminate()
        if not self.process.waitForFinished(300):self.process.kill()
