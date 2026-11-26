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
        p.save();p.setOpacity(opacity)
        p.translate(0,-(1-opacity)*10)
        p.setClipRect(rect)
        for i,(value,size,color) in enumerate([(app,12,accent),(title,20,QColor("#f1ddec")),(body,14,QColor("#bba5c3"))]):
            f=QFont("Sans Serif");f.setPixelSize(size);f.setBold(i==1);p.setFont(f);p.setPen(color)
            p.drawText(QRectF(rect.x(),rect.y()+i*24,rect.width()-40,24),Qt.AlignVCenter|Qt.AlignLeft,p.fontMetrics().elidedText(value,Qt.ElideRight,int(rect.width()-40)))
        x=rect.right()-18;y=rect.top()+16
        p.save();p.translate(x,y);p.rotate(35)
        petal=QPainterPath();petal.moveTo(0,9);petal.cubicTo(-11,-1,-8,-13,0,-8);petal.cubicTo(8,-13,11,-1,0,9);petal.closeSubpath()
        p.setBrush(Qt.NoBrush);p.setPen(QPen(accent,1.4));p.drawPath(petal);p.restore();p.restore()
        self.hit=QRectF(x-16,y-16,32,32)
    def close(self):
        self.process.terminate()
        if not self.process.waitForFinished(300):self.process.kill()
