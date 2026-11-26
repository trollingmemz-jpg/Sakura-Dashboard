"""Persistent normalized layout transforms and edit-only controls."""
import json, math
from contextlib import contextmanager
from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QPen, QColor, QFont, QTransform

class LayoutEditor:
    def __init__(self, host):
        self.host=host
        self.active=False
        self.regions={}
        self.drag=None
        self.selected=None
        self.guides=[]
        self.error=""
        try:
            data=json.loads((host.sync_root/'dashboard-layout.json').read_text())
            self.data=data if isinstance(data,dict) else {}
        except (OSError,ValueError):self.data={}
    def key(self):
        w,h=self.host.width(),max(1,self.host.height())
        return ('portrait' if w<h else 'ultrawide' if w/h>=2.2 else 'landscape')+('-lyrics' if getattr(self.host,'lyrics_window',None) else '')
    def toggle(self):
        self.active=not self.active
        self.drag=None;self.selected=None;self.guides=[]
        self.host.update()
    def save(self):
        try:self.host.write_setting('dashboard-layout.json',self.data);self.error=""
        except OSError:self.error="Could not save layout"
    def reset(self):
        self.data.pop(self.key(),None);self.drag=None;self.selected=None;self.save();self.host.update()
    def begin(self):
        self.regions={}
    def target(self,name,base):
        w,h=max(1,self.host.width()),max(1,self.host.height())
        values=self.data.get(self.key(),{})
        v=values.get(name) if isinstance(values,dict) else None
        if isinstance(v,list) and len(v)==4 and all(isinstance(x,(int,float)) and math.isfinite(x) for x in v):
            x,y,ww,hh=v
            ww=max(.025,min(1,ww));hh=max(.025,min(1,hh))
            return QRectF(max(0,min(1-ww,x))*w,max(0,min(1-hh,y))*h,ww*w,hh*h)
        return QRectF(base)
    @contextmanager
    def section(self,p,name,source):
        transform=p.worldTransform()
        base=transform.mapRect(source)
        if base.width()<=0 or base.height()<=0:
            yield QTransform()
            return
        dest=self.target(name,base)
        mapping=QTransform()
        mapping.translate(dest.x(),dest.y())
        mapping.scale(dest.width()/source.width(),dest.height()/source.height())
        mapping.translate(-source.x(),-source.y())
        self.regions[name]=dest
        p.save()
        p.setWorldTransform(mapping)
        try:yield mapping
        finally:p.restore()
    def press(self,pos):
        if not self.active:return False
        ordered=list(reversed(list(self.regions.items())))
        # Prefer visible resize handles, then the smallest overlapping section.
        handles=[(name,r) for name,r in ordered if QRectF(r.right()-9,r.bottom()-9,18,18).contains(pos)]
        bodies=sorted(ordered,key=lambda item:item[1].width()*item[1].height())
        for name,r in handles+bodies:
            if r.adjusted(-5,-5,5,5).contains(pos):
                corner=QRectF(r.right()-9,r.bottom()-9,18,18)
                self.selected=name
                self.drag=(name,QPointF(pos),QRectF(r),corner.contains(pos),self.key())
                return True
        self.selected=None
        return True
    def move(self,pos):
        if not self.active:return False
        if not self.drag:return True
        name,start,original,resize,key=self.drag
        # Always calculate from the immutable press-time geometry, never the previous frame.
        r=QRectF(original)
        if key!=self.key():self.drag=None;return True
        w,h=max(1,self.host.width()),max(1,self.host.height())
        dx,dy=pos.x()-start.x(),pos.y()-start.y()
        self.guides=[]
        if resize:
            r.setWidth(max(min(40,w-r.x()),min(w-r.x(),r.width()+dx)))
            r.setHeight(max(min(28,h-r.y()),min(h-r.y(),r.height()+dy)))
        else:
            x=max(0,min(w-r.width(),r.x()+dx));y=max(0,min(h-r.height(),r.y()+dy))
            xs=[0,w/2,w];ys=[0,h/2,h]
            for other,rect in self.regions.items():
                if other!=name:
                    xs.extend([rect.left(),rect.center().x(),rect.right()])
                    ys.extend([rect.top(),rect.center().y(),rect.bottom()])
            for coords,offsets,value,limit,axis in [(xs,[0,r.width()/2,r.width()],x,w-r.width(),'x'),(ys,[0,r.height()/2,r.height()],y,h-r.height(),'y')]:
                candidates=[(abs(value+off-line),line-off,line) for line in coords for off in offsets if 0<=line-off<=limit]
                if candidates:
                    distance,new,line=min(candidates)
                    if distance<=4:
                        if axis=='x':x=new
                        else:y=new
                        self.guides.append((axis,line))
            r.moveTo(x,y)
        self.data.setdefault(key,{})[name]=[r.x()/w,r.y()/h,r.width()/w,r.height()/h]
        self.host.update()
        return True
    def release(self):
        if not self.active:return False
        if self.drag:self.save()
        self.drag=None;self.guides=[];self.host.update()
        return True
    def overlay(self,p,accent):
        if not self.active:return
        p.save();p.resetTransform()
        c=QColor(accent);c.setAlpha(150)
        f=QFont('Sans Serif');f.setPixelSize(12);p.setFont(f)
        for name,r in self.regions.items():
            p.setPen(QPen(accent if name==self.selected else c,1,Qt.PenStyle.DashLine));p.setBrush(Qt.NoBrush);p.drawRect(r)
            p.setPen(accent);p.drawText(r.adjusted(5,3,-5,-3),Qt.AlignTop|Qt.AlignLeft,name.replace('_',' ').title())
            p.setBrush(accent);p.setPen(Qt.NoPen);p.drawEllipse(r.bottomRight(),4,4)
        p.setPen(QPen(c,1,Qt.PenStyle.DotLine))
        for axis,line in self.guides:
            if axis=='x':p.drawLine(QPointF(line,0),QPointF(line,self.host.height()))
            else:p.drawLine(QPointF(0,line),QPointF(self.host.width(),line))
        msg=self.error or 'EDIT LAYOUT  ·  Drag to move  ·  Corner to resize  ·  Bloom for options'
        p.setPen(accent);p.drawText(QRectF(0,self.host.height()-22,self.host.width(),20),Qt.AlignCenter,msg)
        p.restore()
