import sys, math, random, time, subprocess, threading, os, glob, json, socket, colorsys
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QRectF
from PySide6.QtGui import QPainter,QColor,QFont,QLinearGradient,QPen
from PySide6.QtWidgets import QApplication,QWidget,QDialog,QVBoxLayout,QFormLayout,QComboBox,QSlider,QCheckBox,QPushButton,QColorDialog,QDialogButtonBox,QLabel,QMessageBox,QTabWidget,QLineEdit,QSpinBox
from PySide6.QtCore import QProcess
import psutil
import urllib.request
from bloom import Bloom, paint_settings_petal
from spotify_connect import Connect
from inline_panel import InlinePanel
from mobile_panel import MobileCompanion
from discord_connection import DiscordConnection
from feature_panels import read_profiles,profiles_panel,discord_panel
from responsive_layout import paint_responsive
from media_bridge import MediaBridge
from media_page import MediaPage
from live_lyrics import LyricsWindow, paint_lyrics
from desktop_notifications import Notifications
from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QFileDialog,QHeaderView
from PySide6.QtGui import QPainterPath
from PySide6.QtGui import QImage
from PySide6.QtCore import QPointF
from local_spectrum import LiveSpectrum, RATE
class Dashboard(QWidget):
 def __init__(self):
  super().__init__(); self.setWindowTitle('Sakura Dashboard'); self.resize(1920,720); self.setWindowFlags(Qt.Window|Qt.FramelessWindowHint); self.bars=[0]*80; self.stats=(0,0,'—','—'); self.track=('Nothing playing',''); self.petals=[(random.random()*1920,random.random()*720,random.uniform(.2,1.2)) for _ in range(45)]
  self.sync_root=Path.home()/'.config/sakura-game-sync'; self.sync_status={}; self.sync_started=False; self.sync_error=''; self.sync_timer=QTimer(self); self.sync_timer.timeout.connect(self.refresh_sync); self.sync_timer.start(1000); self.refresh_sync(); self.ensure_sync()
  self.sync_root.mkdir(parents=True,exist_ok=True);self.media_bridge=MediaBridge(self.sync_root);self.media_bridge.start();self.media_page=None
  self.discord=DiscordConnection();self.game_profile={};self.hit_regions={}
  self.connect=Connect(self.sync_root)
  self.player={};self.devices=[];self.art_url='';self.art=QImage();self.art_accent=QColor('#f478d7');self.art_palette=[];self.accent=QColor('#f478d7');self.circle_points=[];self.local_playing=None;self.panel_active=False
  self.spectrum = LiveSpectrum()
  self.spotify_target=None; self.capture_target=None; self.next_capture=0.; self.audio_status='Waiting for Spotify audio'
  self.capture = QProcess(self)
  self.capture.readyReadStandardOutput.connect(self.audio)
  self.capture.readyReadStandardError.connect(self.audio_error)
  self.audio_timer = QTimer(self)
  self.audio_timer.timeout.connect(self.update_spectrum)
  self.audio_timer.setTimerType(Qt.TimerType.PreciseTimer);self.audio_timer.start(17)
  self.timer = QTimer(self)
  self.timer.timeout.connect(self.update)
  self.timer.start(16)
  self.load_display()
  self.notifications=Notifications(self)
  self.room_stop=threading.Event();self.room_pending=None;self.room_status='Room sync disabled';threading.Thread(target=self.room_worker,daemon=True).start()
  self.chroma_socket=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);self.chroma_socket.setblocking(False);self.chroma_heartbeat=0.;self.chroma_process=None;self.chroma_retry=0.;self.chroma_error='';self.chroma_was_enabled=None;self.chroma_timer=QTimer(self);self.chroma_timer.timeout.connect(self.publish_chroma);self.chroma_timer.setTimerType(Qt.TimerType.PreciseTimer);self.chroma_timer.start(17);self.publish_chroma()
  self.profile_timer=QTimer(self);self.profile_timer.timeout.connect(self.refresh_profile);self.profile_timer.start(1000);self.refresh_profile()
  threading.Thread(target=self.poll, daemon=True).start()
  self.mobile=MobileCompanion(self)

 def room_worker(self):
  def request(payload):
   with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
    client.settimeout(15);client.connect(str(Path.home()/'.local/run/lightctl/lightctl.sock'))
    client.sendall(json.dumps(payload).encode());reply=json.loads(client.recv(65536).decode())
   if not reply.get('ok'):raise RuntimeError(str(reply.get('error','Lightctl rejected command')))
  active=False
  try:
   while not self.room_stop.wait(.04):
    pending=self.room_pending
    try:
     if pending is None:
      if active:request(dict(action='sakura_stop'));active=False
      continue
     rgb,devices,level=pending
     request(dict(action='sakura_frame',colour=rgb,devices=devices,level=level))
     active=True;self.room_status='Room sync active — '+', '.join(devices)
    except (OSError,ValueError,RuntimeError,AttributeError) as e:
     self.room_status='Lightctl: '+str(e)
     self.room_stop.wait(1)
  finally:
   if active:
    try:request(dict(action='sakura_stop'))
    except (OSError,ValueError,RuntimeError):pass
 def publish_chroma(self):
  enabled=bool(self.display_options.get('hardware_visualiser',False))
  color=self.theme_target().name()
  room_enabled=bool(self.display_options.get('room_sync',False))
  room_devices=tuple(dict.fromkeys(n.strip() for n in str(self.display_options.get('room_device','bulb,cupboard')).split(',') if n.strip()))
  room_level=min(1.,max(self.bars[:24],default=0.)*1.35) if enabled else 1.
  self.room_pending=(tuple(QColor(color).getRgb()[:3]),room_devices,room_level) if room_enabled and room_devices else None
  if not room_enabled:self.room_status='Room sync disabled'
  try:
   payload=dict(enabled=enabled,color=color,heartbeat=time.time(),bars=self.bars,effect=self.display_options.get('chroma_effect','Spectrum'),palette=self.art_palette if self.display_options.get('album_theme') and not self.game_profile else [],adaptive=self.display_options.get('chroma_adaptive',True),rate=self.display_options.get('chroma_rate',30))
   if self.chroma_was_enabled!=enabled or (enabled and time.monotonic()-self.chroma_heartbeat>=.5):
    self.write_setting('dashboard-chroma.json',payload);self.chroma_heartbeat=time.monotonic()
   if enabled:
    try:self.chroma_socket.sendto(json.dumps(payload,separators=(',',':')).encode(),str(Path.home()/'.config/sakura-lighting/chroma.sock'))
    except OSError:pass
   self.chroma_was_enabled=enabled
   if not enabled:
    if self.chroma_process and self.chroma_process.poll() is not None:self.chroma_process=None
    return
   if self.chroma_process and self.chroma_process.poll() is None:return
   if time.monotonic()<self.chroma_retry:return
   self.chroma_retry=time.monotonic()+5
   interpreter=Path.home()/'.local/share/sakura-game-sync/venv/bin/python'
   if not interpreter.is_file():interpreter=Path(sys.executable)
   package=Path(__file__).resolve().parent/'optional/lighting.py'
   installed=Path.home()/'.local/share/sakura-lighting/lighting.py'
   # The old standalone GUI has no IPC. Release only that exact user-owned process.
   for proc in psutil.process_iter(['pid','cmdline','uids']):
    try:
     argv=proc.info.get('cmdline') or [];uids=proc.info.get('uids')
     if uids and uids.real==os.getuid() and len(argv)>1 and argv[1]==str(installed) and '--visualiser' not in argv:
      proc.terminate();self.chroma_error='Handing control over from standalone Sakura Lighting';return
    except (psutil.NoSuchProcess,psutil.AccessDenied):continue
   self.chroma_error='';self.chroma_process=subprocess.Popen([str(interpreter),str(package),'--visualiser'],start_new_session=True)
  except OSError as e:self.chroma_error=str(e)
 def theme_target(self):
  return QColor(self.game_profile.get('accent','#f478d7')) if self.game_profile else self.art_accent if self.display_options.get('album_theme',False) else QColor('#f478d7')
 def refresh_profile(self):
  name=self.sync_status.get('detected_game','Desktop');profile=read_profiles(self.sync_root).get(name,{})
  self.game_profile=profile if isinstance(profile,dict) and profile.get('enabled') else {}
  fps=self.game_profile.get('fps') or self.display_options.get('fps',60)
  interval=33 if fps==30 else 16
  if self.timer.interval()!=interval:self.timer.setInterval(interval)
 def open_profiles(self):profiles_panel(self);self.refresh_profile()
 def open_discord(self):discord_panel(self)
 def open_media(self):
  if self.media_page is None:self.media_page=MediaPage(self)
  else:self.media_page.fold()
 def resizeEvent(self,event):
  if getattr(self,'media_page',None):self.media_page.fit()
  super().resizeEvent(event)
 def responsive(self):return self.width()/max(1,self.height())<2.2
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
  dlg=InlinePanel(self);dlg.setWindowTitle('Advanced settings');layout=QVBoxLayout(dlg)
  def request(action,**data):
   try:
    if not self.sync_status:self.sync_started=False;self.ensure_sync()
    self.write_setting('dashboard-advanced.request',dict(action=action,**data));status.setText('Request queued: '+action)
   except OSError as e:status.setText(str(e))
  table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['Game','Steam ID','Process match','Playlist']);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(table)
  try:rows=json.loads((self.sync_root/'games.json').read_text())
  except (OSError,ValueError):rows=[]
  def add(row):
   i=table.rowCount();table.insertRow(i)
   for j,value in enumerate(row):table.setItem(i,j,QTableWidgetItem(str(value)))
  for row in rows:add(row)
  for label,fn in [('Add game',lambda:add(['New game','','',''])),('Remove selected game',lambda:table.removeRow(table.currentRow()) if table.currentRow()>=0 else None),('Save game mappings',lambda:request('mappings',rows=[[table.item(i,j).text() if table.item(i,j) else '' for j in range(4)] for i in range(table.rowCount())])),('Start scanner',lambda:request('start')),('Stop scanner',lambda:request('stop')),('Install vision dependencies',lambda:request('dependencies'))]:
   button=QPushButton(label);button.clicked.connect(fn);layout.addWidget(button)
  def images():
   paths,_=QFileDialog.getOpenFileNames(self,'Select mech references',str(Path.home()),'Images (*.png *.jpg *.jpeg *.webp)')
   if paths:request('images',paths=paths)
  def archive():
   path,_=QFileDialog.getOpenFileName(self,'Select blueprint archive',str(Path.home()),'Archives (*.tar.gz *.tgz *.tar)')
   if path:request('archive',path=path)
  for label,fn in [('Import reference images',images),('Import blueprint archive',archive)]:
   button=QPushButton(label);button.clicked.connect(fn);layout.addWidget(button)
  status=QLabel('');status.setWordWrap(True);layout.addWidget(status)
  dlg.exec()
 def bloom_menu(self):
  if self.panel_active:return
  self.panel_active=True
  try:choice=Bloom(self,self.accent).exec()-2
  finally:self.panel_active=False
  if choice==0:self.open_settings(1)
  elif choice==1:self.open_settings(0)
  elif choice==2:self.open_player()
  elif choice==3:self.open_settings(2)
  elif choice==4:self.open_system()
 def open_system(self):
  dlg=InlinePanel(self);dlg.setWindowTitle('Sakura / System');layout=QVBoxLayout(dlg)
  info=QLabel();info.setWordWrap(True);layout.addWidget(info)
  log=QLabel();log.setWordWrap(True);layout.addWidget(log)
  state=Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'sakura'
  def update():
   info.setText('Game Sync: '+('Running' if self.sync_status else 'Offline')+'\nSpotify: '+(self.connect.state.get('device_error') or ('Connected' if self.connect.state.get('time') else 'Connecting'))+'\n'+self.audio_status+'\n'+str(self.sync_status.get('scanner','Scanner offline'))+'\n'+str(self.sync_status.get('rgb','Lighting offline')))
  def restart():
   if self.sync_status:self.write_setting('dashboard-restart.request',{})
   else:self.sync_started=False;self.ensure_sync()
   log.setText('Game Sync restart requested.')
  def logs():
   try:log.setText('\n'.join((state/'update.log').read_text().splitlines()[-12:]))
   except OSError:log.setText('No update log available.')
  def relaunch():
   try:
    subprocess.Popen(['bash',str(Path(__file__).resolve().parent/'run.sh')],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    dlg.accept();self.close()
   except OSError as e:log.setText(str(e))
  def history():
   panel=InlinePanel(self);panel.setWindowTitle('Notifications');items=QVBoxLayout(panel)
   toggle=QCheckBox('Mirror desktop notifications');toggle.setChecked(self.notifications.enabled);toggle.toggled.connect(lambda value:setattr(self.notifications,'enabled',value));items.addWidget(toggle)
   for app,title,body,stamp in self.notifications.history:
    label=QLabel(time.strftime('%H:%M',time.localtime(stamp))+'  ·  '+app+'\n'+title+'\n'+body);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);items.addWidget(label)
   panel.exec()
  for label,fn in [('Notifications',history),('Restart Game Sync',restart),('Check for updates and relaunch',relaunch),('View update log',logs),('Copy diagnostics',lambda:QApplication.clipboard().setText(info.text()+'\n'+log.text())),('Exit Sakura',lambda:(dlg.accept(),self.close()))]:
   button=QPushButton(label);button.clicked.connect(fn);layout.addWidget(button)
  timer=QTimer(dlg);timer.timeout.connect(update);timer.start(1000);update();dlg.exec();timer.stop()
 def open_account(self):
  dlg=InlinePanel(self);dlg.setWindowTitle('Spotify account');layout=QFormLayout(dlg)
  client=QLineEdit(str(self.connect.read('settings.json').get('client','')));layout.addRow('Spotify client ID',client)
  hint=QLabel('Use your Spotify developer application with redirect URI http://127.0.0.1:8700/callback. Authorisation opens in your browser.');hint.setWordWrap(True);layout.addRow(hint)
  link=QPushButton('Open Spotify developer dashboard');link.clicked.connect(lambda:__import__('webbrowser').open('https://developer.spotify.com/dashboard'));layout.addRow(link)
  status=QLabel('Spotify account connected' if self.connect.read('token.json').get('refresh_token') else 'Not connected');status.setWordWrap(True);layout.addRow(status)
  pending=[0.]
  def login():
   pending[0]=time.time();button.setEnabled(False);status.setText('Complete sign-in in your browser.');self.connect.submit('login',client=client.text())
  def update():
   result=self.connect.result
   if pending[0] and result.get('action')=='login' and result.get('time',0)>=pending[0]:
    pending[0]=0.;button.setEnabled(True);status.setText(result.get('error') or 'Spotify connected successfully.')
  button=QPushButton('Connect Spotify');button.clicked.connect(login);layout.addRow(button)
  timer=QTimer(dlg);timer.timeout.connect(update);timer.start(500);dlg.exec();timer.stop()
 def playing(self):
  if self.local_playing is not None and (self.spotify_target or not self.player.get('device')):return self.local_playing
  return bool(self.player.get('is_playing'))
 def command(self,action,**data):
  if action in ('play','pause','previous','next') and self.spotify_target and self.local_playing is not None:
   subprocess.Popen(['playerctl','--player=spotify',action],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   if action in ('play','pause'):self.local_playing=action=='play'
   return
  self.connect.submit(action,**data)
 def open_player(self):
  dlg=InlinePanel(self);dlg.setWindowTitle('Connections / Spotify');layout=QFormLayout(dlg)
  status=QLabel('Discovering Spotify Connect devices…');status.setWordWrap(True);layout.addRow(status)
  devices=QComboBox();layout.addRow('Playback device',devices)
  transfer=QPushButton('Transfer playback');transfer.setEnabled(False);layout.addRow(transfer)
  refresh=QPushButton('Refresh devices');layout.addRow(refresh)
  volume=QSlider(Qt.Orientation.Horizontal);volume.setRange(0,100);volume.setValue(int((self.player.get('device') or {}).get('volume_percent') or 0));layout.addRow('Volume',volume)
  playlist=QLineEdit();playlist.setPlaceholderText('Spotify playlist link or ID');layout.addRow('Playlist',playlist)
  play=QPushButton('Play playlist');layout.addRow(play)
  shuffle=QCheckBox('Shuffle');shuffle.setChecked(bool(self.player.get('shuffle_state',False)));layout.addRow(shuffle)
  repeat=QComboBox();repeat.addItems(['off','context','track']);repeat.setCurrentText(self.player.get('repeat_state','off'));layout.addRow('Repeat',repeat)
  media=QPushButton('Sakura Media library');media.clicked.connect(lambda:dlg.done(4));layout.addRow(media)
  discord=QPushButton('Discord connection');discord.clicked.connect(lambda:dlg.done(3));layout.addRow(discord)
  account=QPushButton('Spotify account settings');account.clicked.connect(lambda:dlg.done(2));layout.addRow(account)
  pending=[0.];seen=[None]
  def send(action,**data):
   pending[0]=time.time();status.setText('Requesting '+action+'…');self.command(action,**data)
  def update():
   state=self.connect.state
   if state.get('time',0)!=seen[0]:
    seen[0]=state.get('time',0);old=devices.currentData();devices.clear()
    available=[d for d in state.get('devices',[]) if d.get('id') and not d.get('is_restricted')]
    for d in available:devices.addItem(d.get('name','Device')+(' • active' if d.get('is_active') else ''),d['id'])
    for i,d in enumerate(available):
     if d['id']==old or (not old and d.get('is_active')):devices.setCurrentIndex(i)
    transfer.setEnabled(bool(available))
    if not pending[0]:status.setText(state.get('device_error') or (str(len(available))+' available devices' if available else 'No devices found. Open Spotify on the target device.'))
   result=self.connect.result
   if pending[0] and result.get('time',0)>=pending[0]:
    pending[0]=0.;status.setText(result.get('error') or (str(devices.count())+' available devices' if result.get('action')=='refresh' else 'Spotify request completed'))
   elif pending[0] and time.time()-pending[0]>30:
    pending[0]=0.;status.setText('Spotify did not respond. Check your network and account connection.')
  transfer.clicked.connect(lambda:send('transfer',device=devices.currentData()) if devices.currentData() else None)
  refresh.clicked.connect(lambda:send('refresh'))
  volume.sliderReleased.connect(lambda:send('volume',value=volume.value()))
  play.clicked.connect(lambda:send('playlist',value=playlist.text()))
  shuffle.toggled.connect(lambda value:send('shuffle',value=value))
  repeat.activated.connect(lambda _:send('repeat',value=repeat.currentText()))
  timer=QTimer(dlg);timer.timeout.connect(update);timer.start(500);update();send('refresh')
  result=dlg.exec();timer.stop()
  if result==2:self.open_account()
  elif result==3:self.open_discord()
  elif result==4:self.open_media()
 def poll_player(self):
  try:
   state=self.connect.state
   if abs(time.time()-state.get('time',0))<45:self.player=state.get('player') or {};self.devices=state.get('devices',[])
   else:self.player={};self.devices=[]
   item=self.player.get('item') or {};images=(item.get('album') or {}).get('images',[]);url=images[0].get('url','') if images else ''
   try:
    local_url=subprocess.check_output(['playerctl','--player=spotify','metadata','mpris:artUrl'],text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
    if local_url and (self.spotify_target or not url):url=local_url
   except (OSError,subprocess.SubprocessError):pass
   if url.startswith('https://open.spotify.com/image/'):url=url.replace('https://open.spotify.com/image/','https://i.scdn.co/image/',1)
   if url and url!=self.art_url and url.startswith(('https://','http://','file://')):
    with urllib.request.urlopen(url,timeout=4) as response:raw=response.read(4000000)
    image=QImage.fromData(raw)
    if not image.isNull():
     small=image.scaled(24,24);colors=[small.pixelColor(x,y) for x in range(24) for y in range(24)];colors.sort(key=lambda c:c.saturationF()*min(1,c.valueF()*2),reverse=True);c=colors[:100];avg=QColor(*(int(sum(getattr(v,k)() for v in c)/len(c)) for k in ('red','green','blue')));h,s,v,_=avg.getHsvF();self.art_accent=QColor.fromHsvF(max(0,h),max(.35,min(.8,s)),.95);self.art=image;self.art_url=url
     buckets={}
     for pixel in colors:
      ph,ps,pv,_=pixel.getHsvF()
      if ph<0 or ps<.25 or pv<.18:continue
      bin=int(ph*18)%18;buckets[bin]=buckets.get(bin,0)+ps*pv
     self.art_palette=[QColor.fromHsvF((k+.5)/18,.95,.95).name() for k in sorted(buckets,key=buckets.get,reverse=True)[:4]]
   if not url:self.art=QImage();self.art_url='';self.art_accent=QColor('#f478d7');self.art_palette=[]
  except (OSError,ValueError,TypeError,KeyError):pass
 def open_rgb_settings(self):
  self.open_settings(1)
 def open_settings(self,index=0):
  dlg=InlinePanel(self);dlg.setWindowTitle('Sakura • Settings');dlg.setMinimumWidth(560)
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
  device=QComboBox();device.setEditable(True);device.addItem('');device.addItems([d.get('name','') for d in self.devices if d.get('name')]);device.setCurrentText(str(legacy.get('device','')));g.addRow('Playback device (blank = active)',device)
  threshold=QSpinBox();threshold.setRange(8,100);threshold.setValue(int(legacy.get('threshold',12)));g.addRow('Matching threshold',threshold)
  advanced=QPushButton('Advanced: game mappings and mech references')
  g.addRow(advanced)
  advanced.clicked.connect(lambda:dlg.done(2))
  profiles=QPushButton('Game profiles');profiles.clicked.connect(lambda:dlg.done(3));g.addRow(profiles)
  try:view=json.loads((self.sync_root/'dashboard-display.json').read_text())
  except (OSError,ValueError):view={}
  if not isinstance(view,dict):view={}
  petals=QCheckBox();petals.setChecked(bool(view.get('petals',True)));dform.addRow('Animated petals',petals)
  visual=QCheckBox();visual.setChecked(bool(view.get('visualiser',True)));dform.addRow('Spotify visualiser',visual)
  adaptive_theme=QCheckBox();adaptive_theme.setChecked(bool(view.get('album_theme',False)));dform.addRow('Colours from album artwork',adaptive_theme)
  fps=QComboBox();fps.addItems(['30 FPS','60 FPS']);fps.setCurrentIndex(0 if view.get('fps',60)==30 else 1);dform.addRow('Refresh rate',fps)
  optional=QWidget();features=QVBoxLayout(optional);tabs.addTab(optional,'Optional features')
  heading=QLabel('Sakura Lighting');heading.setStyleSheet('font-size:20px;font-weight:bold;color:#f478d7');features.addWidget(heading)
  desc=QLabel('Standalone RGB controller for your keyboard, both RAM sticks and mouse. Uses the existing OpenLinkHub and ckb-next backends.');desc.setWordWrap(True);features.addWidget(desc)
  installed=Path.home()/'.local/share/sakura-lighting/lighting.py'
  package=Path(__file__).resolve().parent/'optional/lighting.py'
  interpreter=Path.home()/'.local/share/sakura-game-sync/venv/bin/python'
  if not interpreter.is_file():interpreter=Path(sys.executable)
  hardware_visualiser=QCheckBox('Enable media-reactive hardware lighting');hardware_visualiser.setChecked(bool(view.get('hardware_visualiser',False)));features.addWidget(hardware_visualiser)
  chroma_effect=QComboBox();chroma_effect.addItems(['Spectrum','Bass shockwave','Ambient flow','Album palette','Automatic']);chroma_effect.setCurrentText(view.get('chroma_effect','Spectrum'));features.addWidget(QLabel('Media lighting effect'));features.addWidget(chroma_effect)
  chroma_rate=QComboBox();chroma_rate.addItems(['30 FPS — compatibility','60 FPS — low latency']);chroma_rate.setCurrentIndex(1 if view.get('chroma_rate',30)==60 else 0);features.addWidget(chroma_rate)
  room_sync=QCheckBox('Sync room lights with Chroma (album colours and audio)');room_sync.setChecked(bool(view.get('room_sync',False)));features.addWidget(room_sync)
  room_device=QLineEdit(str(view.get('room_device','bulb,cupboard')));features.addWidget(QLabel('Lightctl device names (comma-separated)'));features.addWidget(room_device)
  room_status=QLabel(self.room_status);room_status.setWordWrap(True);features.addWidget(room_status)
  room_timer=QTimer(dlg);room_timer.timeout.connect(lambda:room_status.setText(self.room_status));room_timer.start(500)
  chroma_adaptive=QCheckBox('Adaptive audio sensitivity');chroma_adaptive.setChecked(bool(view.get('chroma_adaptive',True)));features.addWidget(chroma_adaptive)
  reactive_hint=QLabel('Automatically runs Sakura Lighting in the background. Keyboard, RAM and mouse react to local Spotify audio; album colours are used when enabled.');reactive_hint.setWordWrap(True);features.addWidget(reactive_hint)
  feature_status=QLabel();feature_status.setWordWrap(True);features.addWidget(feature_status)
  reactive_status=QLabel();reactive_status.setWordWrap(True);features.addWidget(reactive_status)
  def refresh_reactive():
   if not self.display_options.get('hardware_visualiser',False):reactive_status.setText('Media lighting is disabled');return
   try:
    state=json.loads((Path.home()/'.config/sakura-lighting/visualiser-status.json').read_text())
    if abs(time.time()-state['heartbeat'])<3:reactive_status.setText(state['status']);return
   except (OSError,ValueError,KeyError,TypeError):pass
   reactive_status.setText(self.chroma_error or 'Starting media lighting / waiting for hardware')
  reactive_timer=QTimer(dlg);reactive_timer.timeout.connect(refresh_reactive);reactive_timer.start(500);refresh_reactive()
  install_btn=QPushButton('Install / update Sakura Lighting');launch_btn=QPushButton('Open Sakura Lighting');remove_btn=QPushButton('Uninstall Sakura Lighting')
  def refresh_feature():
   feature_status.setText('Installed' if installed.is_file() else 'Not installed');launch_btn.setEnabled(installed.is_file());remove_btn.setEnabled(installed.is_file())
  def manage_feature(action):
   try:
    result=subprocess.run([str(interpreter),str(package),action],capture_output=True,text=True,timeout=10,check=True)
    refresh_feature()
   except (OSError,subprocess.SubprocessError) as e:feature_status.setText(str(e))
  def launch_feature():
   try:subprocess.Popen([str(interpreter),str(installed)],start_new_session=True)
   except OSError as e:feature_status.setText(str(e))
  install_btn.clicked.connect(lambda:manage_feature('--install'));launch_btn.clicked.connect(launch_feature)
  def remove_feature():
   if QMessageBox.question(dlg,'Uninstall Sakura Lighting','Close Sakura Lighting first. Remove its application files? Your saved profile will be retained.')==QMessageBox.StandardButton.Yes:manage_feature('--uninstall')
  remove_btn.clicked.connect(remove_feature)
  for b in (install_btn,launch_btn,remove_btn):features.addWidget(b)
  mobile_heading=QLabel('Sakura Mobile');mobile_heading.setStyleSheet('font-size:20px;font-weight:bold;color:#f478d7');features.addWidget(mobile_heading)
  lyrics_button=QPushButton('Toggle live lyrics (F5)');lyrics_button.clicked.connect(self.open_lyrics);features.addWidget(lyrics_button)
  mobile_pair=QPushButton('Pair phone / show pairing QR');mobile_pair.clicked.connect(self.mobile.show_pairing);features.addWidget(mobile_pair)
  features.addStretch();refresh_feature()
  tabs.setCurrentIndex(index)
  mode=QComboBox();mode.addItems(['Automatic game effects','Manual static colour','Off (release control)'])
  mode.setCurrentIndex({'auto':0,'manual':1,'off':2}.get(profile.get('chroma_previous_mode',profile.get('mode')),0 if legacy.get('rgb_enabled',False) else 2));form.addRow('Lighting mode',mode)
  mode.setEnabled(not hardware_visualiser.isChecked());hardware_visualiser.toggled.connect(lambda enabled:mode.setEnabled(not enabled))
  brightness=QSlider(Qt.Orientation.Horizontal);brightness.setRange(0,100);brightness.setValue(int(profile.get('brightness',100)));level=QLabel(str(brightness.value())+'%');brightness.valueChanged.connect(lambda v:level.setText(str(v)+'%'));form.addRow('Brightness',brightness);form.addRow('',level)
  colors={}
  for key,label,default in [('idle','Desktop',(244,120,215)),('scanning','Normal gameplay',(179,108,255)),('combat','Combat pulse',(240,24,134)),('manual','Manual colour',(244,120,215))]:
   value=profile.get(key,default);colors[key]=QColor(*value);btn=QPushButton()
   def paint_button(button,color):
    button.setText(color.name().upper());button.setStyleSheet('background:'+color.name()+';color:'+('#19101f' if color.lightness()>135 else '#ffffff')+';padding:8px;border-radius:5px')
   paint_button(btn,colors[key])
   def choose(checked=False,k=key,b=btn):
    picker=InlinePanel(self);picker.setWindowTitle('Choose Sakura colour');f=QFormLayout(picker);channels=[]
    for label,value in zip(('Red','Green','Blue'),colors[k].getRgb()[:3]):
     spin=QSpinBox();spin.setRange(0,255);spin.setValue(value);f.addRow(label,spin);channels.append(spin)
    hexfield=QLineEdit(colors[k].name());f.addRow('Hex colour',hexfield)
    for spin in channels:spin.valueChanged.connect(lambda _:hexfield.setText(QColor(*(v.value() for v in channels)).name()))
    ok=QPushButton('Apply');ok.clicked.connect(picker.accept);f.addRow(ok)
    if picker.exec()==1:
     c=QColor(hexfield.text());
     if c.isValid():colors[k]=c;paint_button(b,c)
   btn.clicked.connect(choose);form.addRow(label,btn)
  checks={}
  for key,label in [('keyboard','Keyboard'),('ram','Both RAM sticks'),('mouse','Harpoon mouse')]:
   box=QCheckBox(label);box.setChecked(bool(profile.get(key,legacy.get('rgb_'+key,True))));checks[key]=box;layout.addWidget(box)
  hint=QLabel('Automatic mode follows game detection. Manual mode overrides game lighting only. Brightness 0 turns selected LEDs black; Off releases control.');hint.setWordWrap(True);layout.addWidget(hint)
  buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);outer.addWidget(buttons)
  result=dlg.exec()
  if result==2:self.open_sync_settings();return
  if result==3:self.open_profiles();return
  if result!=QDialog.DialogCode.Accepted:return
  selected_mode=('auto','manual','off')[mode.currentIndex()]
  data=dict(mode='off' if hardware_visualiser.isChecked() else selected_mode,brightness=brightness.value())
  if hardware_visualiser.isChecked():data['chroma_previous_mode']=selected_mode
  data.update({k:[v.red(),v.green(),v.blue()] for k,v in colors.items()});data.update({k:v.isChecked() for k,v in checks.items()})
  try:
   self.sync_root.mkdir(parents=True,exist_ok=True);tmp=self.sync_root/'dashboard-rgb.tmp';tmp.write_text(json.dumps(data,indent=2));tmp.replace(self.sync_root/'dashboard-rgb.json')
   game={k:v.isChecked() for k,v in controls.items()};game.update(combat=combat.text().strip(),device=device.currentText().strip(),threshold=threshold.value())
   self.write_setting('dashboard-game.request',game)
   self.write_setting('dashboard-display.json',dict(petals=petals.isChecked(),visualiser=visual.isChecked(),fps=30 if fps.currentIndex()==0 else 60,album_theme=adaptive_theme.isChecked(),hardware_visualiser=hardware_visualiser.isChecked(),chroma_effect=chroma_effect.currentText(),chroma_rate=60 if chroma_rate.currentIndex()==1 else 30,chroma_adaptive=chroma_adaptive.isChecked(),room_sync=room_sync.isChecked(),room_device=room_device.text().strip() or 'bulb,cupboard'));self.load_display();self.publish_chroma()
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
  if not (self.display_options.get('visualiser',True) or self.display_options.get('hardware_visualiser',False)):
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
  self.notifications.close()
  self.media_bridge.stop();self.discord.disconnect();self.connect.closed=True
  self.sync_timer.stop()
  self.audio_timer.stop()
  self.chroma_timer.stop()
  self.chroma_socket.close()
  self.room_stop.set()
  if getattr(self,'lyrics_window',None):self.lyrics_window.close()
  try:self.write_setting('dashboard-chroma.json',dict(enabled=False,heartbeat=time.time()))
  except OSError:pass
  if self.chroma_process and self.chroma_process.poll() is None:
   try:self.chroma_process.wait(timeout=.8)
   except subprocess.TimeoutExpired:self.chroma_process.terminate()
  if self.capture.state() != QProcess.NotRunning:
   self.capture.kill()
   self.capture.waitForFinished(500)
  super().closeEvent(event)

 def poll(self):
  while True:
   self.spotify_target=self.discover_spotify()
   self.poll_player()
   try:self.local_playing=subprocess.check_output(['playerctl','--player=spotify','status'],text=True,stderr=subprocess.DEVNULL,timeout=2).strip()=='Playing'
   except (OSError,subprocess.SubprocessError):self.local_playing=None
   def cmd(a):
    try:return subprocess.check_output(a,text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
    except Exception:return ''
   gpu=cmd(['nvidia-smi','--query-gpu=utilization.gpu,temperature.gpu','--format=csv,noheader,nounits']).split(','); temps=psutil.sensors_temperatures(); cpu=next((v.current for k,vs in temps.items() for v in vs if v.label=='Tctl'),None); self.stats=(psutil.cpu_percent(),psutil.virtual_memory().percent, f'{cpu:.0f}°C' if cpu is not None else '—', (' / '.join(x.strip() for x in gpu)+'°C') if len(gpu)==2 else '—'); t=cmd(['playerctl','--player=spotify','metadata','--format','{{title}}\n{{artist}}']).splitlines(); self.track=(t[0],t[1] if len(t)>1 else '') if t else ('Nothing playing',''); time.sleep(2)
 def open_lyrics(self):
  panel=getattr(self,'lyrics_window',None)
  if panel is not None:
   self.lyrics_window=None;panel.close();self.update();return
  panel=LyricsWindow(self);self.lyrics_window=panel
  self.update()
 def keyPressEvent(self,e):
  if any(isinstance(c,InlinePanel) and c.isVisible() for c in self.children()):return
  if e.key()==Qt.Key_F4 or (e.key()==Qt.Key_Escape and self.media_page):self.open_media();return
  if e.key()==Qt.Key_Escape:self.close()
  if e.key()==Qt.Key_F11:self.showNormal() if self.isFullScreen() else self.showFullScreen()
  if e.key()==Qt.Key_F2:self.bloom_menu()
  if e.key()==Qt.Key_F3:self.open_rgb_settings()
  if e.key()==Qt.Key_F5:self.open_lyrics()
 def mousePressEvent(self,e):
  if e.button()==Qt.MouseButton.LeftButton and self.notifications.hit.contains(e.position()):
   self.notifications.dismiss();self.update();return
  if any(isinstance(c,InlinePanel) and c.isVisible() for c in self.children()):return
  if self.responsive():
   for action,rect in self.hit_regions.items():
    if rect.contains(e.position()):
     if action=='settings':self.bloom_menu()
     elif action=='connections':self.open_player()
     elif action=='discord':self.open_discord()
     elif action=='media':self.open_media()
     elif action=='toggle':self.command('pause' if self.playing() else 'play')
     else:self.command(action)
     return
   return
  x=e.position().x()*1920/max(1,self.width());y=e.position().y()*720/max(1,self.height())
  if e.button()==Qt.MouseButton.RightButton:self.circle_points=[(x,y)]
  elif 1120<=x<=1260 and 640<=y<=695:self.open_media()
  elif math.hypot(x-1850,y-665)<32:self.bloom_menu()
  elif 300<=x<=370 and 330<=y<=390:self.command('previous')
  elif 380<=x<=450 and 330<=y<=390:self.command('pause' if self.playing() else 'play')
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
  target=self.theme_target()
  if self.responsive():
   self.accent=QColor(*(round(a+(b-a)*.10) for a,b in zip(self.accent.getRgb()[:3],target.getRgb()[:3])));paint_responsive(self)
   return
  p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.scale(self.width()/1920,self.height()/720); g=QLinearGradient(0,0,1920,720); self.accent=QColor(*(round(a+(b-a)*.10) for a,b in zip(self.accent.getRgb()[:3],target.getRgb()[:3])));g.setColorAt(0,QColor('#100b20'));g.setColorAt(1,self.accent.darker(430) if self.game_profile or self.display_options.get('album_theme',False) else QColor('#32132e'));p.fillRect(QRectF(0,0,1920,720),g)
  def text(x,y,w,h,s,size,color='#f5d9ef',weight=400):
   p.setPen(QColor(color));f=QFont('Sans Serif',size);f.setWeight(QFont.Weight(weight));p.setFont(f);p.drawText(QRectF(x,y,w,h),Qt.AlignVCenter|Qt.AlignLeft,p.fontMetrics().elidedText(str(s),Qt.ElideRight,int(w)))
  p.setPen(Qt.NoPen)
  for i,(x,y,v) in enumerate(self.petals if (self.game_profile.get('petals') if self.game_profile.get('petals') is not None else self.display_options.get('petals',True)) else []):
   petal=QColor(self.accent);petal.setAlpha(45);p.setBrush(petal);p.save();p.translate(x,y);p.rotate(y/4);p.drawEllipse(QRectF(-5,-2,10,4));p.restore();self.petals[i]=((x+v*.4)%1920,(y+v)%720,v)
  text(70,40,900,55,'桜  /  SAKURA',23,self.accent,500);text(1300,14,550,76,time.strftime('%H:%M'),46)
  if not self.art.isNull():p.drawImage(QRectF(70,150,200,200),self.art)
  else:p.fillRect(QRectF(70,150,200,200),QColor('#39253e'))
  item=self.player.get('item') or {};title=item.get('name') or self.track[0];artist=', '.join(a.get('name','') for a in item.get('artists',[])) or self.track[1]
  text(300,195,880,90,title,40);text(300,280,880,45,artist,23,'#c393cc')
  p.setBrush(QColor('#f5d9ef'));p.setPen(Qt.NoPen)
  for x,direction in ((335,-1),(495,1)):
   path=QPainterPath();path.moveTo(x-12*direction,348);path.lineTo(x+9*direction,360);path.lineTo(x-12*direction,372);path.closeSubpath();p.drawPath(path);p.drawRoundedRect(QRectF(x+11*direction-2,348,4,24),1,1)
  if self.playing():
   p.drawRoundedRect(QRectF(405,347,7,26),2,2);p.drawRoundedRect(QRectF(419,347,7,26),2,2)
  else:
   path=QPainterPath();path.moveTo(405,345);path.lineTo(430,360);path.lineTo(405,375);path.closeSubpath();p.drawPath(path)
  text(550,330,630,60,(self.player.get('device') or {}).get('name','Spotify devices'),18,self.accent)
  lyrics=getattr(self,'lyrics_window',None)
  notice_active=self.notifications.visible()
  if lyrics:paint_lyrics(p,lyrics,QRectF(1270,135,600,310),self.accent)
  for i,b in enumerate(self.bars):
   base=505 if lyrics and notice_active else 600;h=max(2,min(1,b)*(95 if lyrics and notice_active else 190));c=QColor(self.accent);c.setAlpha(185);p.setBrush(c);p.setPen(Qt.NoPen);p.drawRoundedRect(QRectF(70+i*13.5,base-h,5,h),2,2)
  import re
  gpu=re.match(r'\s*(\d+(?:\.\d+)?)\s*/\s*(.*)',str(self.stats[3]))
  entries=[('CPU',self.stats[0],self.stats[2]),('GPU',float(gpu.group(1)) if gpu else None,gpu.group(2) if gpu else ''),('MEMORY',self.stats[1],'')]
  for i,(label,value,detail) in enumerate(entries):
   y=(460 if lyrics else 220)+i*(48 if lyrics else 72)
   text(1300,y,160,30,label,15,'#a982b5')
   reading=(f'{value:.0f}%' if value is not None else '—')+('  ·  '+str(detail) if detail and detail!='—' else '')
   text(1480,y,350,30,reading,20)
   p.fillRect(QRectF(1300,y+34,500,2),QColor('#352b40'))
   if value is not None:p.fillRect(QRectF(1300,y+34,5*max(0,min(100,value)),2),self.accent)
  sync=self.sync_status
  text(70,605,1100,30,('Game: '+sync.get('detected_game','Desktop') if sync.get('detected_game','Desktop')!='Desktop' else '')+('  •  Discord: '+self.discord.state.get('channel','') if self.discord.state.get('channel') else ''),13,'#a982b5')
  mode='COMBAT LOCKED' if sync.get('combat') else 'SCANNING' if sync.get('scanning') else 'IDLE' if sync else 'OFFLINE'
  accent='#F01886' if sync.get('combat') else '#B36CFF' if sync.get('scanning') else '#F478D7'
  if not sync:text(70,645,1100,35,'Game Sync offline',13,'#a982b5')
  text(1120,640,140,45,'MEDIA ↗',18,self.accent)
  text(1300,640,470,45,time.strftime('%A  •  %d %B'),16,'#a982b5')
  paint_settings_petal(p,1850,665,22,self.accent)
  slot=QRectF(70,515,1080,80) if lyrics else QRectF(1300,420,500,120)
  slot=p.transform().mapRect(slot)
  p.resetTransform();self.notifications.paint(p,slot,self.accent)
  p.scale(self.width()/1920,self.height()/720)
  if self.circle_points:
   p.setPen(QPen(self.accent,2))
   for a,b in zip(self.circle_points,self.circle_points[1:]):p.drawLine(QPointF(*a),QPointF(*b))
app=QApplication(sys.argv);w=Dashboard();w.show();sys.exit(app.exec())
