import sys, math, random, time, subprocess, threading, os, glob, json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QRectF
from PySide6.QtGui import QPainter,QColor,QFont,QLinearGradient,QPen
from PySide6.QtWidgets import QApplication,QWidget,QDialog,QVBoxLayout,QFormLayout,QComboBox,QSlider,QCheckBox,QPushButton,QColorDialog,QDialogButtonBox,QLabel,QMessageBox,QTabWidget,QLineEdit,QSpinBox
from PySide6.QtCore import QProcess
import psutil
import urllib.request
from bloom import Bloom
from PySide6.QtGui import QImage
from PySide6.QtCore import QPointF
from local_spectrum import LiveSpectrum, RATE
class Dashboard(QWidget):
 def __init__(self):
  super().__init__(); self.setWindowTitle('Sakura Dashboard'); self.resize(1920,720); self.setWindowFlags(Qt.Window|Qt.FramelessWindowHint); self.bars=[0]*80; self.stats=(0,0,'—','—'); self.track=('Nothing playing',''); self.petals=[(random.random()*1920,random.random()*720,random.uniform(.2,1.2)) for _ in range(45)]
  self.sync_root=Path.home()/'.config/sakura-game-sync'; self.sync_status={}; self.sync_started=False; self.sync_error=''; self.sync_timer=QTimer(self); self.sync_timer.timeout.connect(self.refresh_sync); self.sync_timer.start(1000); self.refresh_sync(); self.ensure_sync()
  self.player={};self.devices=[];self.art_url='';self.art=QImage();self.art_accent=QColor('#f478d7');self.accent=QColor('#f478d7');self.circle_points=[]
  self.spectrum = LiveSpectrum()
  self.spotify_target=None; self.capture_target=None; self.next_capture=0.; self.audio_status='Waiting for Spotify audio'
  self.capture = QProcess(self)
  self.capture.readyReadStandardOutput.connect(self.audio)
  self.capture.readyReadStandardError.connect(self.audio_error)
  self.audio_timer = QTimer(self)
  self.audio_timer.timeout.connect(self.update_spectrum)
  self.audio_timer.start(50)
  self.timer = QTimer(self)
  self.timer.timeout.connect(self.update)
  self.timer.start(16)
  self.load_display()
  threading.Thread(target=self.poll, daemon=True).start()

 def refresh_sync(self):
  try:
   state=json.loads((self.sync_root/'dashboard-status.json').read_text())
   self.sync_status=state if abs(time.time()-state['time'])<5 else {}
  except (OSError,ValueError,KeyError,TypeError):self.sync_status={}
 def ensure_sync(self):
  if self.sync_status or self.sync_started:return
  root=Path.home()/'.local/share/sakura-game-sync'
  python=root/'venv/bin/python'; entry=root/'app.py'
  if not python.is_file() or not entry.is_file():
   self.sync_error='Game Sync installation not found';return
  try:
   subprocess.Popen([str(python),str(entry),'--background'],cwd=root,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   self.sync_started=True
  except OSError as e:self.sync_error=str(e)
 def open_sync_settings(self):
  if not self.sync_status:
   self.sync_started=False;self.ensure_sync()
   return
  try:
   self.sync_root.mkdir(parents=True,exist_ok=True)
   (self.sync_root/'dashboard-show.request').write_text('')
  except OSError as e:self.sync_error=str(e)
 def bloom_menu(self):
  choice=Bloom(self,self.accent).exec()-2
  if choice==0:self.open_settings(1)
  elif choice==1:self.open_settings(0)
  elif choice==2:self.open_player()
  elif choice==3:self.open_settings(2)
  elif choice==4:QMessageBox.information(self,'Sakura • System','Automatic updates on launch\n'+str(self.sync_status.get('scanner','Backend unavailable'))+'\n'+str(self.sync_status.get('spotify',''))+'\n'+self.audio_status)
 def command(self,action,**data):
  try:self.write_setting('dashboard-player.request',dict(time=time.time(),action=action,**data))
  except OSError as e:QMessageBox.warning(self,'Spotify',str(e))
 def open_player(self):
  dlg=QDialog(self);dlg.setWindowTitle('Sakura • Spotify');dlg.setMinimumWidth(420);layout=QFormLayout(dlg)
  devices=QComboBox();available=[d for d in self.devices if d.get('id') and not d.get('is_restricted')]
  for d in available:devices.addItem(d.get('name','Device')+(' • active' if d.get('is_active') else ''),d['id'])
  for i,d in enumerate(available):
   if d.get('is_active'):devices.setCurrentIndex(i)
  layout.addRow('Spotify Connect',devices);transfer=QPushButton('Transfer playback');transfer.setEnabled(bool(available));transfer.clicked.connect(lambda:(self.command('transfer',device=devices.currentData()),dlg.accept()));layout.addRow(transfer)
  volume=QSlider(Qt.Orientation.Horizontal);volume.setRange(0,100);volume.setValue(int((self.player.get('device') or {}).get('volume_percent') or 0));layout.addRow('Volume',volume);volume.sliderReleased.connect(lambda:self.command('volume',value=volume.value()))
  playlist=QLineEdit();playlist.setPlaceholderText('Spotify playlist link or ID');layout.addRow('Playlist',playlist);play=QPushButton('Play playlist');play.clicked.connect(lambda:(self.command('playlist',value=playlist.text()),dlg.accept()));layout.addRow(play)
  shuffle=QPushButton('Toggle shuffle');shuffle.clicked.connect(lambda:(self.command('shuffle',value=not self.player.get('shuffle_state',False)),dlg.accept()));layout.addRow(shuffle)
  repeat=QComboBox();repeat.addItems(['off','context','track']);repeat.setCurrentText(self.player.get('repeat_state','off'));repeat.activated.connect(lambda _:self.command('repeat',value=repeat.currentText()));layout.addRow('Repeat',repeat)
  account=QPushButton('Account and advanced settings');account.clicked.connect(lambda:(dlg.reject(),self.open_sync_settings()));layout.addRow(account)
  close=QPushButton('Close');close.clicked.connect(dlg.accept);layout.addRow(close);dlg.exec()
 def poll_player(self):
  try:
   state=json.loads((self.sync_root/'dashboard-player.json').read_text())
   if abs(time.time()-state['time'])>45:return
   self.player=state.get('player') or {};self.devices=state.get('devices',[])
   item=self.player.get('item') or {};images=(item.get('album') or {}).get('images',[]);url=images[-1].get('url','') if images else ''
   if url and url!=self.art_url and url.startswith('https://'):
    with urllib.request.urlopen(url,timeout=4) as response:raw=response.read(4000000)
    image=QImage.fromData(raw)
    if not image.isNull():
     small=image.scaled(24,24);colors=[small.pixelColor(x,y) for x in range(24) for y in range(24)];colors.sort(key=lambda c:c.saturationF()*min(1,c.valueF()*2),reverse=True);c=colors[:100];avg=QColor(*(int(sum(getattr(v,k)() for v in c)/len(c)) for k in ('red','green','blue')));h,s,v,_=avg.getHsvF();self.art_accent=QColor.fromHsvF(max(0,h),max(.35,min(.8,s)),.95);self.art=image;self.art_url=url
   if not url:self.art=QImage();self.art_url='';self.art_accent=QColor('#f478d7')
  except (OSError,ValueError,TypeError,KeyError):pass
 def open_rgb_settings(self):
  self.open_settings(1)
 def open_settings(self,index=0):
  dlg=QDialog(self);dlg.setWindowTitle('Sakura • Settings');dlg.setMinimumWidth(560)
  dlg.setStyleSheet('QDialog{background:#201329;color:#f5d9ef} QLabel,QCheckBox{color:#f5d9ef} QPushButton,QComboBox{background:#39253e;color:#f5d9ef;padding:8px;border-radius:5px}')
  outer=QVBoxLayout(dlg);tabs=QTabWidget();outer.addWidget(tabs)
  general=QWidget();g=QFormLayout(general);tabs.addTab(general,'Game & Spotify')
  rgb=QWidget();layout=QVBoxLayout(rgb);form=QFormLayout();layout.addLayout(form);tabs.addTab(rgb,'Lighting')
  display=QWidget();dform=QFormLayout(display);tabs.addTab(display,'Display')
  try:profile=json.loads((self.sync_root/'dashboard-rgb.json').read_text())
  except (OSError,ValueError):profile={}
  if not isinstance(profile,dict):profile={}
  try:legacy=json.loads((self.sync_root/'settings.json').read_text())
  except (OSError,ValueError):legacy={}
  if not isinstance(legacy,dict):legacy={}
  controls={}
  for key,label,default in [('enabled','Automatic soundtrack switching',False),('shuffle','Shuffle playlists',True),('fallback','Desktop playlist on game exit',True),('adaptive','Automatic Trailmakers scanning',False),('hud_enabled','Combat overlay',True)]:
   box=QCheckBox();box.setChecked(bool(legacy.get(key,default)));controls[key]=box;g.addRow(label,box)
  combat=QLineEdit(str(legacy.get('combat','')));g.addRow('Combat playlist',combat)
  device=QLineEdit(str(legacy.get('device','')));device.setPlaceholderText('Blank = active Spotify device');g.addRow('Playback device',device)
  threshold=QSpinBox();threshold.setRange(8,100);threshold.setValue(int(legacy.get('threshold',12)));g.addRow('Matching threshold',threshold)
  advanced=QPushButton('Advanced: game mappings, Spotify sign-in and mech references')
  g.addRow(advanced)
  advanced.clicked.connect(lambda:(dlg.reject(),self.open_sync_settings()))
  try:view=json.loads((self.sync_root/'dashboard-display.json').read_text())
  except (OSError,ValueError):view={}
  if not isinstance(view,dict):view={}
  petals=QCheckBox();petals.setChecked(bool(view.get('petals',True)));dform.addRow('Animated petals',petals)
  visual=QCheckBox();visual.setChecked(bool(view.get('visualiser',True)));dform.addRow('Spotify visualiser',visual)
  adaptive_theme=QCheckBox();adaptive_theme.setChecked(bool(view.get('album_theme',False)));dform.addRow('Colours from album artwork',adaptive_theme)
  fps=QComboBox();fps.addItems(['30 FPS','60 FPS']);fps.setCurrentIndex(0 if view.get('fps',60)==30 else 1);dform.addRow('Refresh rate',fps)
  tabs.setCurrentIndex(index)
  mode=QComboBox();mode.addItems(['Automatic game effects','Manual static colour','Off (release control)'])
  mode.setCurrentIndex({'auto':0,'manual':1,'off':2}.get(profile.get('mode'),0 if legacy.get('rgb_enabled',False) else 2));form.addRow('Lighting mode',mode)
  brightness=QSlider(Qt.Orientation.Horizontal);brightness.setRange(0,100);brightness.setValue(int(profile.get('brightness',100)));level=QLabel(str(brightness.value())+'%');brightness.valueChanged.connect(lambda v:level.setText(str(v)+'%'));form.addRow('Brightness',brightness);form.addRow('',level)
  colors={}
  for key,label,default in [('idle','Desktop',(244,120,215)),('scanning','Normal gameplay',(179,108,255)),('combat','Combat pulse',(240,24,134)),('manual','Manual colour',(244,120,215))]:
   value=profile.get(key,default);colors[key]=QColor(*value);btn=QPushButton()
   def paint_button(button,color):
    button.setText(color.name().upper());button.setStyleSheet('background:'+color.name()+';color:'+('#19101f' if color.lightness()>135 else '#ffffff')+';padding:8px;border-radius:5px')
   paint_button(btn,colors[key])
   def choose(checked=False,k=key,b=btn):
    c=QColorDialog.getColor(colors[k],dlg,'Choose Sakura colour')
    if c.isValid():colors[k]=c;paint_button(b,c)
   btn.clicked.connect(choose);form.addRow(label,btn)
  checks={}
  for key,label in [('keyboard','Keyboard'),('ram','Both RAM sticks'),('mouse','Harpoon mouse')]:
   box=QCheckBox(label);box.setChecked(bool(profile.get(key,legacy.get('rgb_'+key,True))));checks[key]=box;layout.addWidget(box)
  hint=QLabel('Automatic mode follows game detection. Manual mode overrides game lighting only. Brightness 0 turns selected LEDs black; Off releases control.');hint.setWordWrap(True);layout.addWidget(hint)
  buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);outer.addWidget(buttons)
  if dlg.exec()!=QDialog.DialogCode.Accepted:return
  data=dict(mode=('auto','manual','off')[mode.currentIndex()],brightness=brightness.value())
  data.update({k:[v.red(),v.green(),v.blue()] for k,v in colors.items()});data.update({k:v.isChecked() for k,v in checks.items()})
  try:
   self.sync_root.mkdir(parents=True,exist_ok=True);tmp=self.sync_root/'dashboard-rgb.tmp';tmp.write_text(json.dumps(data,indent=2));tmp.replace(self.sync_root/'dashboard-rgb.json')
   game={k:v.isChecked() for k,v in controls.items()};game.update(combat=combat.text().strip(),device=device.text().strip(),threshold=threshold.value())
   self.write_setting('dashboard-game.request',game)
   self.write_setting('dashboard-display.json',dict(petals=petals.isChecked(),visualiser=visual.isChecked(),fps=30 if fps.currentIndex()==0 else 60,album_theme=adaptive_theme.isChecked()));self.load_display()
  except OSError as e:QMessageBox.warning(self,'RGB settings',str(e))
  if not self.sync_status:self.sync_started=False;self.ensure_sync()
 def write_setting(self,name,data):
  self.sync_root.mkdir(parents=True,exist_ok=True)
  tmp=self.sync_root/(name+'.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(self.sync_root/name)
 def load_display(self):
  try:v=json.loads((self.sync_root/'dashboard-display.json').read_text())
  except (OSError,ValueError):v={}
  self.display_options=v if isinstance(v,dict) else {}
  self.timer.setInterval(33 if self.display_options.get('fps')==30 else 16)
 def discover_spotify(self):
  try:
   def pulse(kind):
    return json.loads(subprocess.check_output(['pactl','-f','json','list',kind],text=True,stderr=subprocess.DEVNULL,timeout=2))
   streams=pulse('sink-inputs')
   candidates=[]
   for stream in streams:
    props=stream.get('properties',{})
    binary=str(props.get('application.process.binary','')).lower()
    name=str(props.get('application.name','')).lower()
    appid=str(props.get('application.id','')).lower()
    if binary=='spotify' or name=='spotify' or appid=='com.spotify.client':candidates.append(stream)
   if not candidates:return None
   stream=next((v for v in candidates if not v.get('corked',False)),candidates[0])
   sink=next((v for v in pulse('sinks') if str(v.get('index'))==str(stream.get('sink'))),None)
   if not sink:return None
   monitor=sink.get('monitor_source_name') or sink.get('name','')+'.monitor'
   return (str(stream['index']),monitor)
  except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):return None
 def start_capture(self):
  if not self.spotify_target:return
  index,source=self.spotify_target
  self.capture_target=self.spotify_target
  self.next_capture=time.monotonic()+3
  self.capture.start('parec',['--raw','--format=s16le',f'--rate={RATE}','--channels=2','--latency-msec=25','--device='+source,'--monitor-stream='+index])
  self.audio_status='Spotify audio • local capture'

 def audio(self):
  self.spectrum.feed(bytes(self.capture.readAllStandardOutput()))

 def audio_error(self):
  message=bytes(self.capture.readAllStandardError()).decode(errors='replace').strip()
  if message:self.audio_status='Spotify capture: '+message.splitlines()[-1];sys.stderr.write(message+'\n')

 def update_spectrum(self):
  if not self.display_options.get('visualiser',True):
   if self.capture.state()!=QProcess.NotRunning:self.capture.kill()
   self.spectrum.reset();self.bars=[0]*80;self.audio_status='Visualiser disabled';return
  if self.spotify_target!=self.capture_target:
   if self.capture.state()!=QProcess.NotRunning:
    self.capture.kill()
    return
   self.capture_target=self.spotify_target
   self.spectrum.reset()
   self.next_capture=0.
  if self.capture.state()==QProcess.NotRunning:
   if self.spotify_target and time.monotonic()>=self.next_capture:self.start_capture()
   elif not self.spotify_target:self.audio_status='Waiting for Spotify audio'
  self.bars=self.spectrum.tick()

 def closeEvent(self, event):
  self.sync_timer.stop()
  self.audio_timer.stop()
  if self.capture.state() != QProcess.NotRunning:
   self.capture.kill()
   self.capture.waitForFinished(500)
  super().closeEvent(event)

 def poll(self):
  while True:
   self.spotify_target=self.discover_spotify()
   self.poll_player()
   def cmd(a):
    try:return subprocess.check_output(a,text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
    except Exception:return ''
   gpu=cmd(['nvidia-smi','--query-gpu=utilization.gpu,temperature.gpu','--format=csv,noheader,nounits']).split(','); temps=psutil.sensors_temperatures(); cpu=next((v.current for k,vs in temps.items() for v in vs if v.label=='Tctl'),None); self.stats=(psutil.cpu_percent(),psutil.virtual_memory().percent, f'{cpu:.0f}°C' if cpu is not None else '—', (' / '.join(x.strip() for x in gpu)+'°C') if len(gpu)==2 else '—'); t=cmd(['playerctl','--player=spotify','metadata','--format','{{title}}\n{{artist}}']).splitlines(); self.track=(t[0],t[1] if len(t)>1 else '') if t else ('Nothing playing',''); time.sleep(2)
 def keyPressEvent(self,e):
  if e.key()==Qt.Key_Escape:self.close()
  if e.key()==Qt.Key_F11:self.showNormal() if self.isFullScreen() else self.showFullScreen()
  if e.key()==Qt.Key_F2:self.bloom_menu()
  if e.key()==Qt.Key_F3:self.open_rgb_settings()
 def mousePressEvent(self,e):
  x=e.position().x()*1920/max(1,self.width());y=e.position().y()*720/max(1,self.height())
  if e.button()==Qt.MouseButton.RightButton:self.circle_points=[(x,y)]
  elif math.hypot(x-1830,y-655)<45:self.bloom_menu()
  elif 300<=x<=370 and 330<=y<=390:self.command('previous')
  elif 380<=x<=450 and 330<=y<=390:self.command('pause' if self.player.get('is_playing') else 'play')
  elif 460<=x<=530 and 330<=y<=390:self.command('next')
  elif 550<=x<=1180 and 330<=y<=390:self.open_player()
  super().mousePressEvent(e)
 def mouseMoveEvent(self,e):
  if self.circle_points:self.circle_points.append((e.position().x()*1920/max(1,self.width()),e.position().y()*720/max(1,self.height())))
 def mouseReleaseEvent(self,e):
  pts=self.circle_points;self.circle_points=[]
  if len(pts)<12:return
  cx=sum(x for x,y in pts)/len(pts);cy=sum(y for x,y in pts)/len(pts);r=[math.hypot(x-cx,y-cy) for x,y in pts];avg=sum(r)/len(r)
  angles=[math.atan2(y-cy,x-cx) for x,y in pts];travel=sum(math.atan2(math.sin(b-a),math.cos(b-a)) for a,b in zip(angles,angles[1:]))
  if 65<avg<280 and abs(travel)>5.35 and max(r)-min(r)<avg*.85 and math.dist(pts[0],pts[-1])<avg*.5:self.bloom_menu()
 def paintEvent(self,e):
  p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.scale(self.width()/1920,self.height()/720); g=QLinearGradient(0,0,1920,720); target=self.art_accent if self.display_options.get('album_theme',False) else QColor('#f478d7');self.accent=QColor(*(round(a+(b-a)*.10) for a,b in zip(self.accent.getRgb()[:3],target.getRgb()[:3])));g.setColorAt(0,QColor('#100b20'));g.setColorAt(1,self.accent.darker(430) if self.display_options.get('album_theme',False) else QColor('#32132e'));p.fillRect(QRectF(0,0,1920,720),g)
  def text(x,y,w,h,s,size,color='#f5d9ef',weight=400):
   p.setPen(QColor(color));f=QFont('Sans Serif',size);f.setWeight(QFont.Weight(weight));p.setFont(f);p.drawText(QRectF(x,y,w,h),Qt.AlignVCenter|Qt.AlignLeft,p.fontMetrics().elidedText(str(s),Qt.ElideRight,int(w)))
  p.setPen(Qt.NoPen)
  for i,(x,y,v) in enumerate(self.petals if self.display_options.get('petals',True) else []):
   p.setBrush(QColor(240,90,239,45));p.save();p.translate(x,y);p.rotate(y/4);p.drawEllipse(QRectF(-5,-2,10,4));p.restore();self.petals[i]=((x+v*.4)%1920,(y+v)%720,v)
  text(70,40,900,55,'桜  /  SAKURA',23,self.accent,500);text(1300,14,550,76,time.strftime('%H:%M'),46)
  if not self.art.isNull():p.drawImage(QRectF(70,150,200,200),self.art)
  else:p.fillRect(QRectF(70,150,200,200),QColor('#39253e'))
  item=self.player.get('item') or {};title=item.get('name') or self.track[0];artist=', '.join(a.get('name','') for a in item.get('artists',[])) or self.track[1]
  text(300,150,880,40,'NOW PLAYING',17,self.accent);text(300,195,880,90,title,40);text(300,280,880,45,artist,23,'#c393cc')
  text(310,330,60,60,'‹',30);text(390,330,60,60,'Ⅱ' if self.player.get('is_playing') else '▶',23);text(470,330,60,60,'›',30)
  text(550,330,630,60,(self.player.get('device') or {}).get('name','Spotify devices'),18,self.accent)
  for i,b in enumerate(self.bars):
   h=max(3,min(1,b)*190);p.setBrush(self.accent);p.setPen(Qt.NoPen);p.drawRoundedRect(QRectF(70+i*13.5,600-h,8,h),4,4)
  p.setPen(QPen(QColor('#583456'),1));p.drawLine(1240,150,1240,620)
  for i,(label,value,detail) in enumerate([('CPU',self.stats[0],self.stats[2]),('GPU',None,self.stats[3]),('MEMORY',self.stats[1],'')]):
   y=160+i*150;text(1300,y,530,35,label,19,'#c393cc');text(1300,y+40,530,65,(f'{value:.0f}%  '+detail) if value is not None else detail,34)
   if value is not None:p.fillRect(QRectF(1300,y+112,500,4),QColor('#4b294c'));p.fillRect(QRectF(1300,y+112,5*value,4),QColor('#f05aef'))
  sync=self.sync_status
  mode='COMBAT LOCKED' if sync.get('combat') else 'SCANNING' if sync.get('scanning') else 'IDLE' if sync else 'OFFLINE'
  accent='#F01886' if sync.get('combat') else '#B36CFF' if sync.get('scanning') else '#F478D7'
  text(70,645,1100,35,'Sakura active' if sync else 'Game Sync offline',15,'#a982b5')
  text(1300,640,470,45,time.strftime('%A  •  %d %B'),16,'#a982b5')
  p.setPen(QPen(self.accent,1.3));p.setBrush(QColor('#211329'));p.drawEllipse(QPointF(1830,655),36,36)
  text(1808,624,60,62,'桜',25,self.accent)
  if self.circle_points:
   p.setPen(QPen(self.accent,2))
   for a,b in zip(self.circle_points,self.circle_points[1:]):p.drawLine(QPointF(*a),QPointF(*b))
app=QApplication(sys.argv);w=Dashboard();w.show();sys.exit(app.exec())
