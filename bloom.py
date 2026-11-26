import math,time
from PySide6.QtCore import Qt,QTimer,QPointF,QRectF,QEvent
from PySide6.QtGui import QPainter,QPainterPath,QColor,QPen,QLinearGradient,QRadialGradient,QFont,QTransform
from inline_panel import InlinePanel

class Bloom(InlinePanel):
 def __init__(self,parent,accent,labels=None):
  super().__init__(parent)
  self.setWindowTitle('Sakura Bloom')
  self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,False)
  self.setAutoFillBackground(False)
  self.setStyleSheet('background: transparent; border: none;')
  self.setMouseTracking(True);self.accent=QColor(accent);self.labels=list(labels) if labels is not None else ['Lighting','Games','Connections','Appearance','System']
  self.started=time.monotonic();self.closing=None;self.choice=-1;self.cursor=None
  self.timer=QTimer(self);self.timer.timeout.connect(self.update);self.timer.start(16)
  self.path=QPainterPath();self.path.moveTo(0,74)
  self.path.cubicTo(-28,46,-63,6,-63,-29);self.path.cubicTo(-63,-65,-25,-79,0,-63)
  self.path.cubicTo(25,-79,63,-65,63,-29);self.path.cubicTo(63,6,28,46,0,74);self.path.closeSubpath()
 def fit(self):
  side=max(1,min(int(self.host.height()*.61),int(self.host.width()*.85)))
  self.setGeometry((self.host.width()-side)//2,(self.host.height()-side)//2,side,side)
 def coords(self,e):
  scale=min(self.width(),self.height())/360
  return QPointF((e.position().x()-self.width()/2)/scale,(e.position().y()-self.height()/2)/scale)
 def mouseMoveEvent(self,e):self.cursor=self.coords(e);self.update()
 def leaveEvent(self,e):self.cursor=None;self.update()
 def dismiss(self):
  if self.closing is None:
   self.choice=-1;self.closing=time.monotonic();self.update()
 def eventFilter(self,obj,event):
  if obj is self.host and event.type()==QEvent.Type.MouseButtonPress and self.isVisible():
   self.dismiss();return True
  return super().eventFilter(obj,event)
 def mousePressEvent(self,e):
  if self.closing is not None:return
  p=self.coords(e);r=math.hypot(p.x(),p.y())
  if r<30:self.dismiss();return
  if time.monotonic()-self.started>=1.35:
   for j in range(len(self.labels)-1,-1,-1):
    angle=-math.pi/2+j*2*math.pi/len(self.labels)
    tr=QTransform();tr.translate(65*math.cos(angle),65*math.sin(angle));tr.rotate(j*360/len(self.labels))
    inv,valid=tr.inverted()
    if valid and self.path.contains(inv.map(p)):
     self.choice=j;self.closing=time.monotonic();return
  self.dismiss()
 def paintEvent(self,e):
  p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
  p.translate(self.width()/2,self.height()/2);s=min(self.width(),self.height())/360;p.scale(s,s)
  elapsed=time.monotonic()-self.started
  if self.closing is not None and time.monotonic()-self.closing>=.30:
   QTimer.singleShot(0,lambda:self.done(self.choice+2 if self.choice>=0 else 0));return
  for i,label in enumerate(self.labels):
   t=max(0,min(1,(elapsed-i*.27)/.27))
   if self.closing is not None:t=1-max(0,min(1,(time.monotonic()-self.closing-(len(self.labels)-1-i)*.045)/.12))
   if t<=0:continue
   u=(1-math.cos(math.pi*t))/2;a=-math.pi/2+i*2*math.pi/len(self.labels)
   b=a-(1-u)*2*math.pi/len(self.labels) if i else a
   x=65*math.cos(b)*(1 if i else u);y=65*math.sin(b)*(1 if i else u)
   rot=(i-1+u)*360/len(self.labels) if i else 0
   p.save();p.translate(x,y);p.rotate(rot);p.scale(1 if i else .2+.8*u,1 if i else .2+.8*u)
   g=QLinearGradient(0,74,0,-74);g.setColorAt(0,QColor('#1d1126'));g.setColorAt(1,QColor('#3a223b'))
   p.setBrush(g);p.setPen(QPen(self.accent.darker(210),.8));p.drawPath(self.path)
   if self.cursor is not None:
    dx=self.cursor.x();dy=self.cursor.y();r=math.hypot(dx,dy)
    theta=math.radians(rot);lx=(dx-x)*math.cos(theta)+(dy-y)*math.sin(theta);ly=-(dx-x)*math.sin(theta)+(dy-y)*math.cos(theta)
    # Resolve hover in actual paint order, so overlapping petals cannot both be primary.
    primary=-1
    if r>30 and elapsed>=1.35 and self.closing is None:
     for j in range(4,-1,-1):
      angle=-math.pi/2+j*2*math.pi/len(self.labels)
      tr=QTransform();tr.translate(65*math.cos(angle),65*math.sin(angle));tr.rotate(j*360/len(self.labels))
      inv,valid=tr.inverted()
      if valid and self.path.contains(inv.map(self.cursor)):
       primary=j;break
    if primary>=0:
     p.save();p.setClipPath(self.path);p.setPen(Qt.PenStyle.NoPen)
     if i==primary:
      progress=max(0,min(1,(74-ly)/148))
      light=QLinearGradient(0,74,lx,ly if abs(ly-74)>1 else 73)
      c=QColor(self.accent);c.setAlphaF(.23);light.setColorAt(0,c);c.setAlphaF(.14);light.setColorAt(.72,c);c.setAlpha(0);light.setColorAt(1,c)
      p.fillPath(self.path,light)
      spot=QRadialGradient(lx,ly,43);c=QColor(self.accent);c.setAlphaF(.32);spot.setColorAt(0,c);c.setAlphaF(.10);spot.setColorAt(.55,c);c.setAlpha(0);spot.setColorAt(1,c);p.fillPath(self.path,spot)
     elif (i-primary)%len(self.labels) in (1,len(self.labels)-1):
      # Only a tiny, local halo can cross the shared edge, never a whole-petal beam.
      spot=QRadialGradient(lx,ly,15);c=QColor(self.accent);c.setAlphaF(.065);spot.setColorAt(0,c);c.setAlpha(0);spot.setColorAt(1,c);p.fillPath(self.path,spot)
     p.restore()
   p.restore()
  for i,label in enumerate(self.labels):
   if elapsed<(i+1)*.27:continue
   if self.closing is not None and time.monotonic()-self.closing>(4-i)*.045:continue
   a=-math.pi/2+i*2*math.pi/len(self.labels);x=92*math.cos(a);y=92*math.sin(a)
   font=QFont('Sans Serif')
   font.setPixelSize(11 if len(label)>12 else 13)
   font.setWeight(QFont.Weight.Medium)
   font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,.65)
   p.setFont(font)
   color=QColor('#f1ddec')
   if self.cursor is not None and math.hypot(self.cursor.x()-x,self.cursor.y()-y)<38:
    color=QColor(self.accent).lighter(135)
   color.setAlphaF(max(0.,min(1.,(elapsed-(i+1)*.27)/.16)))
   p.setPen(color)
   p.drawText(QRectF(x-49,y-22,98,44),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,label)
  p.setBrush(QColor('#160e20'));p.setPen(QPen(self.accent,1));p.drawEllipse(QPointF(0,0),30,30)
  center_font=QFont('Sans Serif');center_font.setPixelSize(26);center_font.setWeight(QFont.Weight.Normal);p.setFont(center_font);p.setPen(self.accent);p.drawText(QRectF(-30,-30,60,60),Qt.AlignmentFlag.AlignCenter,'桜')

def paint_settings_petal(p,x,y,r,accent):
 """Compact outlined blossom, with no surrounding box or circle."""
 p.save()
 p.translate(x,y)
 p.scale(r/18,r/18)
 p.setPen(QPen(QColor(accent),1.15))
 p.setBrush(Qt.BrushStyle.NoBrush)
 petal=QPainterPath()
 petal.moveTo(0,-2)
 petal.cubicTo(-8,-5,-10,-13,-4,-16)
 petal.quadTo(-1,-18,0,-14)
 petal.quadTo(1,-18,4,-16)
 petal.cubicTo(10,-13,8,-5,0,-2)
 petal.closeSubpath()
 for i in range(5):
  p.drawPath(petal)
  p.rotate(72)
 p.restore()
 return QRectF(x-r-5,y-r-5,2*r+10,2*r+10)
