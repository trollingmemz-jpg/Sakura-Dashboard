import math,time
from PySide6.QtCore import Qt,QTimer,QPointF,QRectF
from PySide6.QtGui import QPainter,QPainterPath,QColor,QPen,QLinearGradient,QRadialGradient,QFont,QTransform
from PySide6.QtWidgets import QDialog

class Bloom(QDialog):
 def __init__(self,parent,accent):
  super().__init__(parent)
  self.setWindowTitle('Sakura Bloom');self.resize(480,480);self.setMinimumSize(360,360)
  self.setMouseTracking(True);self.accent=QColor(accent);self.labels=['Lighting','Games','Spotify','Appearance','System']
  self.started=time.monotonic();self.closing=None;self.choice=-1;self.cursor=None
  self.timer=QTimer(self);self.timer.timeout.connect(self.update);self.timer.start(16)
  self.path=QPainterPath();self.path.moveTo(0,74)
  self.path.cubicTo(-28,46,-63,6,-63,-29);self.path.cubicTo(-63,-65,-25,-79,0,-63)
  self.path.cubicTo(25,-79,63,-65,63,-29);self.path.cubicTo(63,6,28,46,0,74);self.path.closeSubpath()
 def coords(self,e):
  scale=min(self.width(),self.height())/360
  return QPointF((e.position().x()-self.width()/2)/scale,(e.position().y()-self.height()/2)/scale)
 def mouseMoveEvent(self,e):self.cursor=self.coords(e);self.update()
 def leaveEvent(self,e):self.cursor=None;self.update()
 def mousePressEvent(self,e):
  if self.closing is not None:return
  p=self.coords(e);r=math.hypot(p.x(),p.y())
  if r<30:self.choice=-1
  elif r<140 and time.monotonic()-self.started>=1.35:self.choice=round((math.atan2(p.y(),p.x())+math.pi/2)/(2*math.pi/5))%5
  else:return
  self.closing=time.monotonic()
 def paintEvent(self,e):
  p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
  p.fillRect(self.rect(),QColor('#100b20'));p.translate(self.width()/2,self.height()/2);s=min(self.width(),self.height())/360;p.scale(s,s)
  elapsed=time.monotonic()-self.started
  if self.closing is not None and time.monotonic()-self.closing>=.30:
   self.done(self.choice+2 if self.choice>=0 else 0);return
  for i,label in enumerate(self.labels):
   t=max(0,min(1,(elapsed-i*.27)/.27))
   if self.closing is not None:t=1-max(0,min(1,(time.monotonic()-self.closing-(4-i)*.045)/.12))
   if t<=0:continue
   u=(1-math.cos(math.pi*t))/2;a=-math.pi/2+i*2*math.pi/5
   b=a-(1-u)*2*math.pi/5 if i else a
   x=65*math.cos(b)*(1 if i else u);y=65*math.sin(b)*(1 if i else u)
   rot=(i-1+u)*72 if i else 0
   p.save();p.translate(x,y);p.rotate(rot);p.scale(1 if i else .2+.8*u,1 if i else .2+.8*u)
   g=QLinearGradient(0,74,0,-74);g.setColorAt(0,QColor('#1d1126'));g.setColorAt(1,QColor('#3a223b'))
   p.setBrush(g);p.setPen(QPen(self.accent.darker(210),.8));p.drawPath(self.path)
   if self.cursor is not None:
    dx=self.cursor.x();dy=self.cursor.y();r=math.hypot(dx,dy)
    angle=math.atan2(dy,dx);delta=math.atan2(math.sin(angle-a),math.cos(angle-a))
    weight=math.exp(-.5*(delta/.70)**2)*max(0,min(1,(r-25)/30))
    if weight>.01:
     theta=math.radians(rot);lx=(dx-x)*math.cos(theta)+(dy-y)*math.sin(theta);ly=-(dx-x)*math.sin(theta)+(dy-y)*math.cos(theta)
     progress=max(0,min(1,(74-ly)/148))
     light=QLinearGradient(0,74,0,-74);c=QColor(self.accent);c.setAlphaF(weight*.55);light.setColorAt(0,c);light.setColorAt(max(0,progress-.10),c)
     c=QColor(self.accent.lighter(160));c.setAlphaF(weight*.8);light.setColorAt(progress,c);c.setAlpha(0);light.setColorAt(min(1,progress+.13),c);light.setColorAt(1,c)
     p.setPen(Qt.PenStyle.NoPen);p.setBrush(light);p.drawPath(self.path)
     spot=QRadialGradient(lx,ly,75);c=QColor(self.accent.lighter(170));c.setAlphaF(weight*.45);spot.setColorAt(0,c);c.setAlpha(0);spot.setColorAt(1,c);p.setBrush(spot);p.drawPath(self.path)
   p.restore()
  for i,label in enumerate(self.labels):
   if elapsed<(i+1)*.27:continue
   if self.closing is not None and time.monotonic()-self.closing>(4-i)*.045:continue
   a=-math.pi/2+i*2*math.pi/5;x=92*math.cos(a);y=92*math.sin(a)
   p.setFont(QFont('Sans Serif',10));p.setPen(QColor('#f1ddec'));p.drawText(QRectF(x-48,y-12,96,24),Qt.AlignmentFlag.AlignCenter,label)
  p.setBrush(QColor('#160e20'));p.setPen(QPen(self.accent,1));p.drawEllipse(QPointF(0,0),30,30)
  p.setFont(QFont('Sans Serif',22));p.setPen(self.accent);p.drawText(QRectF(-30,-30,60,60),Qt.AlignmentFlag.AlignCenter,'桜')
