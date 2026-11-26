"""Three-segment media overlay with clipped, perspective-projected hinges."""
import math,json,threading,urllib.request,webbrowser
from PySide6.QtCore import Qt,QTimer,QVariantAnimation,QEasingCurve,QRectF,QPointF
from PySide6.QtGui import QPainter,QColor,QPolygonF,QTransform,QPixmap,QImage,QPen
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QTabWidget,QListWidget,QListWidgetItem,QApplication,QMessageBox
from media_library import clean_url

class MediaPage(QWidget):
 def __init__(self,owner):
  super().__init__(owner);self.owner=owner;self.bridge=owner.media_bridge;self.progress=0.;self.closing=False;self.ready=False;self.result=[];self.busy=False
  self.setStyleSheet('QWidget{background:#201329;color:#f5d9ef} QPushButton,QListWidget{background:#39253e;color:#f5d9ef;padding:7px;border-radius:5px} QLabel{background:transparent}')
  self.library=QWidget(self);self.discovery=QWidget(self)
  a=QVBoxLayout(self.library);header=QHBoxLayout();header.addWidget(QLabel('桜  /  MEDIA LIBRARY'));header.addStretch()
  close=QPushButton('Fold away');close.clicked.connect(self.fold);header.addWidget(close);a.addLayout(header)
  self.private=QCheckBox('Enable tracking and reveal history');self.private.setChecked(self.bridge.enabled);a.addWidget(self.private)
  self.status=QLabel();self.status.setTextFormat(Qt.PlainText);a.addWidget(self.status)
  buttons=QHBoxLayout()
  for name,fn in [('Copy pairing code',lambda:QApplication.clipboard().setText(self.bridge.token)),('Resume selected',self.resume),('Remove selected',self.remove),('Clear history',self.clear)]:
   b=QPushButton(name);b.clicked.connect(fn);buttons.addWidget(b)
  a.addLayout(buttons)
  self.tabs=QTabWidget();self.lists={}
  for kind,label in [('all','Recent'),('anime','Anime'),('manga','Manga')]:
   widget=QListWidget();widget.setWordWrap(True);widget.itemDoubleClicked.connect(lambda _:self.resume());self.tabs.addTab(widget,label);self.lists[kind]=widget
  a.addWidget(self.tabs)
  b=QVBoxLayout(self.discovery);b.addWidget(QLabel('DISCOVER'))
  self.hint=QLabel('Optional: query AniList for recommendations using title and genre metadata.');self.hint.setWordWrap(True);b.addWidget(self.hint)
  recommend=QPushButton('Find recommendations');recommend.clicked.connect(self.recommend);b.addWidget(recommend)
  self.recs=QListWidget();self.recs.setWordWrap(True);self.recs.itemDoubleClicked.connect(self.open_recommendation);b.addWidget(self.recs)
  self.private.toggled.connect(self.privacy)
  self.animation=QVariantAnimation(self);self.animation.setDuration(400);self.animation.setEasingCurve(QEasingCurve.InOutSine);self.animation.valueChanged.connect(self.frame);self.animation.finished.connect(self.finished)
  self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(2000)
  self.refresh();self.fit();self.library.hide();self.discovery.hide();self.show();self.raise_();self.animation.setStartValue(0.);self.animation.setEndValue(1.);self.animation.start()
 def fit(self):
  w,h=self.owner.width(),self.owner.height();self.setGeometry(0,0,w,h)
  hinge=max(50,int(h*.19));middle=int((h-hinge)*.57);self.hinge=hinge
  self.library.setGeometry(0,hinge,w,middle);self.discovery.setGeometry(0,hinge+middle,w,h-hinge-middle)
 def frame(self,v):self.progress=float(v);self.update()
 def finished(self):
  if self.closing:
   self.timer.stop();self.owner.media_page=None;self.hide();self.deleteLater()
  else:self.ready=True;self.library.show();self.discovery.show();self.update()
 def fold(self):
  if self.closing:return
  self.closing=True;self.ready=False;self.library.hide();self.discovery.hide();self.animation.stop();self.animation.setStartValue(self.progress);self.animation.setEndValue(0.);self.animation.start()
 def paintEvent(self,e):
  if self.ready:return
  p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setClipRect(QRectF(0,self.hinge,self.width(),self.height()-self.hinge))
  w=self.width();z=0.;y=float(self.hinge);distance=max(500.,w*1.4)
  def project(x,yy,zz):
   f=distance/(distance+max(-distance*.7,zz));return QPointF(w/2+(x-w/2)*f,self.hinge+(yy-self.hinge)*f)
  for i,widget in enumerate((self.library,self.discovery)):
   length=widget.height();t=max(0.,min(1.,(self.progress-i*.10)/(1-i*.10)));angle=(-1 if i==0 else 1)*math.pi*(1-t)
   # Both panels remain clipped below the stationary dashboard hinge.
   yy=y+length*math.cos(angle);zz=z+length*math.sin(angle)
   quad=QPolygonF([project(0,y,z),project(w,y,z),project(w,yy,zz),project(0,yy,zz)])
   if math.cos(angle)>0 and length>0:
    pix=widget.grab();src=QPolygonF([QPointF(0,0),QPointF(pix.width(),0),QPointF(pix.width(),pix.height()),QPointF(0,pix.height())])
    transform=QTransform()
    if QTransform.quadToQuad(src,quad,transform):
     p.save();p.setTransform(transform);p.drawPixmap(0,0,pix);p.fillRect(QRectF(0,0,pix.width(),pix.height()),QColor(0,0,0,int(85*(1-t))));p.restore()
   else:p.setBrush(QColor('#201329'));p.setPen(QPen(QColor('#805071'),1));p.drawPolygon(quad)
   y,z=yy,zz
  p.end()
 def privacy(self,on):
  self.bridge.privacy(on)
  if not on:self.result=[];self.recs.clear()
  self.refresh()
 def refresh(self):
  active=self.bridge.current();self.status.setText((self.bridge.status+' • '+(active.get('source','Waiting for browser') if self.bridge.enabled else 'Privacy mode — tracking stopped')))
  for kind,widget in self.lists.items():
   old=widget.currentItem();key=old.data(Qt.UserRole) if old else None
   rows=self.bridge.library.recent(None if kind=='all' else kind) if self.bridge.enabled else []
   widget.clear()
   for row in rows:
    position=int(row['position']);detail=f'{position//60}:{position%60:02d}' if row['kind']=='anime' else f'Page {position}' if position else 'Page unknown'
    item=QListWidgetItem(f"{row['title']}  •  {row['part']}\n{row['source']}  •  {detail}");item.setData(Qt.UserRole,(row['url'],row['part']));widget.addItem(item)
    if key==item.data(Qt.UserRole):widget.setCurrentItem(item)
  if self.bridge.enabled and self.result:
   self.recs.clear()
   for title,url in self.result:
    item=QListWidgetItem(title);item.setData(Qt.UserRole,url);self.recs.addItem(item)
 def selected(self):
  item=self.tabs.currentWidget().currentItem();return item.data(Qt.UserRole) if item else None
 def resume(self):
  key=self.selected()
  if key and self.bridge.enabled and clean_url(key[0]):webbrowser.open(key[0])
 def remove(self):
  key=self.selected()
  if key:self.bridge.library.remove(*key);self.refresh()
 def clear(self):
  if QMessageBox.question(self,'Clear history','Delete all local media history?')==QMessageBox.Yes:self.bridge.privacy(False);self.private.setChecked(False);self.bridge.library.clear();self.refresh()
 def recommend(self):
  if not self.bridge.enabled or self.busy:return
  rows=self.bridge.library.recent()
  if not rows:self.hint.setText('Watch or read something first.');return
  self.busy=True;self.hint.setText('Finding related titles…')
  titles={r['title'].casefold() for r in rows};seed=rows[0];kind=seed['kind'].upper()
  def work():
   result=[]
   try:
    query='query($title:String,$type:MediaType){Media(search:$title,type:$type){recommendations(sort:RATING_DESC,perPage:12){nodes{mediaRecommendation{title{romaji english} siteUrl isAdult}}}}}'
    req=urllib.request.Request('https://graphql.anilist.co',data=json.dumps({'query':query,'variables':{'title':seed['title'],'type':kind}}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=12) as response:data=json.load(response)
    for node in data['data']['Media']['recommendations']['nodes']:
     m=node.get('mediaRecommendation') or {};t=m.get('title') or {};title=t.get('english') or t.get('romaji')
     if title and title.casefold() not in titles and not m.get('isAdult') and str(m.get('siteUrl','')).startswith('https://anilist.co/'):result.append((title,m['siteUrl']))
   except Exception:pass
   if self.bridge.enabled:self.result=result
   self.busy=False
  threading.Thread(target=work,daemon=True).start()
  QTimer.singleShot(13000,lambda:self.hint.setText('Related titles from AniList' if self.result else 'No recommendations found yet.'))
 def open_recommendation(self,item):
  url=item.data(Qt.UserRole)
  if self.bridge.enabled and url and url.startswith('https://anilist.co/'):webbrowser.open(url)
