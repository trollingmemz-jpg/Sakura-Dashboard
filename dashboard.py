import sys, math, random, time, subprocess, threading, os, glob, json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QRectF
from PySide6.QtGui import QPainter,QColor,QFont,QLinearGradient,QPen
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import QProcess
import psutil
from sakura_connect.spectrum import LiveSpectrum, RATE
class Dashboard(QWidget):
 def __init__(self):
  super().__init__(); self.setWindowTitle('Sakura Dashboard'); self.resize(1920,720); self.setWindowFlags(Qt.Window|Qt.FramelessWindowHint); self.bars=[0]*80; self.stats=(0,0,'—','—'); self.track=('Nothing playing',''); self.petals=[(random.random()*1920,random.random()*720,random.uniform(.2,1.2)) for _ in range(45)]
  self.sync_root=Path.home()/'.config/sakura-game-sync'; self.sync_status={}; self.sync_started=False; self.sync_error=''; self.sync_timer=QTimer(self); self.sync_timer.timeout.connect(self.refresh_sync); self.sync_timer.start(1000); self.refresh_sync(); self.ensure_sync()
  self.spectrum = LiveSpectrum(int(os.getenv('SAKURA_VISUAL_DELAY_MS', '0')))
  self.capture = QProcess(self)
  self.capture.readyReadStandardOutput.connect(self.audio)
  self.capture.readyReadStandardError.connect(self.audio_error)
  self.start_capture()
  self.audio_timer = QTimer(self)
  self.audio_timer.timeout.connect(self.update_spectrum)
  self.audio_timer.start(50)
  self.timer = QTimer(self)
  self.timer.timeout.connect(self.update)
  self.timer.start(16)
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
 def start_capture(self):
  source = os.getenv('SAKURA_SOURCE', 'sakura_bridge.monitor')
  self.capture.start('parec', ['--raw', '--format=s16le', f'--rate={RATE}',
                               '--channels=2', '--latency-msec=25', '--device=' + source])
  self.next_capture = time.monotonic() + 3

 def audio(self):
  self.spectrum.feed(bytes(self.capture.readAllStandardOutput()))

 def audio_error(self):
  sys.stderr.write(bytes(self.capture.readAllStandardError()).decode(errors='replace'))

 def update_spectrum(self):
  if self.capture.state() == QProcess.NotRunning and time.monotonic() >= self.next_capture:
   self.spectrum.pcm = b''
   self.start_capture()
  self.bars = self.spectrum.tick()

 def closeEvent(self, event):
  self.sync_timer.stop()
  self.audio_timer.stop()
  if self.capture.state() != QProcess.NotRunning:
   self.capture.kill()
   self.capture.waitForFinished(500)
  super().closeEvent(event)

 def poll(self):
  while True:
   def cmd(a):
    try:return subprocess.check_output(a,text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
    except Exception:return ''
   gpu=cmd(['nvidia-smi','--query-gpu=utilization.gpu,temperature.gpu','--format=csv,noheader,nounits']).split(','); temps=psutil.sensors_temperatures(); cpu=next((v.current for k,vs in temps.items() for v in vs if v.label=='Tctl'),None); self.stats=(psutil.cpu_percent(),psutil.virtual_memory().percent, f'{cpu:.0f}°C' if cpu is not None else '—', (' / '.join(x.strip() for x in gpu)+'°C') if len(gpu)==2 else '—'); t=cmd(['playerctl','metadata','--format','{{title}}\n{{artist}}']).splitlines(); self.track=(t[0],t[1] if len(t)>1 else '') if t else ('Nothing playing',''); time.sleep(2)
 def keyPressEvent(self,e):
  if e.key()==Qt.Key_Escape:self.close()
  if e.key()==Qt.Key_F11:self.showNormal() if self.isFullScreen() else self.showFullScreen()
  if e.key()==Qt.Key_F2:self.open_sync_settings()
 def mousePressEvent(self,e):
  x=e.position().x()*1920/max(1,self.width());y=e.position().y()*720/max(1,self.height())
  if 70<=x<=1180 and 615<=y<=705:self.open_sync_settings()
  super().mousePressEvent(e)
 def paintEvent(self,e):
  p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.scale(self.width()/1920,self.height()/720); g=QLinearGradient(0,0,1920,720); g.setColorAt(0,QColor('#100b20'));g.setColorAt(1,QColor('#32132e'));p.fillRect(QRectF(0,0,1920,720),g)
  def text(x,y,w,h,s,size,color='#f5d9ef',weight=400):
   p.setPen(QColor(color));f=QFont('Sans Serif',size);f.setWeight(QFont.Weight(weight));p.setFont(f);p.drawText(QRectF(x,y,w,h),Qt.AlignVCenter|Qt.AlignLeft,p.fontMetrics().elidedText(str(s),Qt.ElideRight,int(w)))
  p.setPen(Qt.NoPen)
  for i,(x,y,v) in enumerate(self.petals):
   p.setBrush(QColor(240,90,239,45));p.save();p.translate(x,y);p.rotate(y/4);p.drawEllipse(QRectF(-5,-2,10,4));p.restore();self.petals[i]=((x+v*.4)%1920,(y+v)%720,v)
  text(70,40,900,55,'桜の夜  /  SAKURA NIGHT',23,'#f05aef',500);text(1510,32,380,90,time.strftime('%H:%M'),54);text(70,150,1100,45,'NOW PLAYING',17,'#c393cc');text(70,195,1100,90,self.track[0],47);text(70,285,1100,50,self.track[1],25,'#c393cc');
  for i,b in enumerate(self.bars):
   h=max(3,min(1,b)*225);p.setBrush(QColor.fromHsvF(.79+i/80*.08,.55,.95));p.setPen(Qt.NoPen);p.drawRoundedRect(QRectF(70+i*13.5,600-h,8,h),4,4)
  p.setPen(QPen(QColor('#583456'),1));p.drawLine(1240,150,1240,620)
  for i,(label,value,detail) in enumerate([('CPU',self.stats[0],self.stats[2]),('GPU',None,self.stats[3]),('MEMORY',self.stats[1],'')]):
   y=160+i*150;text(1300,y,530,35,label,19,'#c393cc');text(1300,y+40,530,65,(f'{value:.0f}%  '+detail) if value is not None else detail,34)
   if value is not None:p.fillRect(QRectF(1300,y+112,500,4),QColor('#4b294c'));p.fillRect(QRectF(1300,y+112,5*value,4),QColor('#f05aef'))
  sync=self.sync_status
  mode='COMBAT LOCKED' if sync.get('combat') else 'SCANNING' if sync.get('scanning') else 'IDLE' if sync else 'OFFLINE'
  accent='#F01886' if sync.get('combat') else '#B36CFF' if sync.get('scanning') else '#F478D7'
  text(70,95,1100,35,'GAME SYNC  /  '+mode+'  •  '+str(sync.get('playlist','Waiting')),17,accent)
  text(70,615,1100,35,str(sync.get('scanner',self.sync_error or 'Waiting for Game Sync backend')),15,'#c393cc')
  text(70,650,1100,35,str(sync.get('rgb','RGB status unavailable'))+'  •  F2 / click for settings',15,'#a982b5')
  text(1300,640,530,45,time.strftime('%A  •  %d %B'),16,'#a982b5')
app=QApplication(sys.argv);w=Dashboard();w.show();sys.exit(app.exec())
