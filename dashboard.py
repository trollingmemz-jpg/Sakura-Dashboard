import sys, math, random, time, subprocess, threading, os, glob, json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QRectF
from PySide6.QtGui import QPainter,QColor,QFont,QLinearGradient,QPen
from PySide6.QtWidgets import QApplication,QWidget,QDialog,QVBoxLayout,QFormLayout,QComboBox,QSlider,QCheckBox,QPushButton,QColorDialog,QDialogButtonBox,QLabel,QMessageBox,QTabWidget,QLineEdit,QSpinBox
from PySide6.QtCore import QProcess
import psutil
import urllib.request
from bloom import Bloom, paint_settings_petal
from layout_editor import LayoutEditor
from desktop_notifications import Notifications
from live_lyrics import LyricsWindow, paint_lyrics
from spotify_connect import Connect
from inline_panel import InlinePanel
from discord_connection import DiscordConnection
from feature_panels import read_profiles,profiles_panel,discord_panel
from responsive_layout import paint_responsive
from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QFileDialog,QHeaderView
from PySide6.QtGui import QPainterPath
from PySide6.QtGui import QImage
from PySide6.QtCore import QPointF
from local_spectrum import LiveSpectrum, RATE
from windows_audio import WindowsAudio
from windows_stats import GPUStats
from windows_media import LocalMedia
from windows_update import Updater
from game_autohide import AutoHide
from PySide6.QtWidgets import QSystemTrayIcon,QMenu
from PySide6.QtGui import QIcon,QPixmap
class Dashboard(QWidget):
 def __init__(self):
  super().__init__(); self.setWindowTitle('Sakura Dashboard'); self.resize(1280,480); self.setWindowFlags(Qt.Window); self.bars=[0]*80; self.stats=(0,0,'—','—'); self.track=('Nothing playing',''); self.petals=[(random.random()*1920,random.random()*720,random.uniform(.2,1.2)) for _ in range(45)]
  self.sync_root=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Sakura'/'state';self.sync_root.mkdir(parents=True,exist_ok=True); self.sync_status={}; self.sync_started=False; self.sync_error=''; self.sync_timer=QTimer(self); self.sync_timer.timeout.connect(self.refresh_sync); self.sync_timer.start(1000); self.refresh_sync(); self.ensure_sync()
  self.discord=DiscordConnection();self.game_profile={};self.hit_regions={}
  self.connect=Connect(self.sync_root);self.media=LocalMedia();self.updater=Updater(self.sync_root);self.media_key=None
  self.player={};self.devices=[];self.art_url='';self.art=QImage();self.art_accent=QColor('#f478d7');self.accent=QColor('#f478d7');self.circle_points=[];self.local_playing=None;self.panel_active=False
  self.spectrum = LiveSpectrum();self.win_audio=WindowsAudio();self.gpu_stats=GPUStats()
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
  self.game_autohide=AutoHide(self)
  self.tray=None;self.tray_hidden=False;self.tray_lyrics=False
  self.settings_hit=QRectF();self.editor=LayoutEditor(self);self.notifications=Notifications(self);self.notifications.enabled=False
  self.profile_timer=QTimer(self);self.profile_timer.timeout.connect(self.refresh_profile);self.profile_timer.start(1000);self.refresh_profile()
  self.update_check_timer=QTimer(self);self.update_check_timer.timeout.connect(self.updater.check);self.update_check_timer.start(1800000)
  if not self.display_options.get('welcome_seen'):QTimer.singleShot(600,self.welcome)
  self.poll_stop=threading.Event()
  threading.Thread(target=self.poll, daemon=True).start()
  threading.Thread(target=self.poll_artwork,daemon=True).start()

 def welcome(self):
  dlg=InlinePanel(self);dlg.setWindowTitle('Welcome to Sakura');layout=QVBoxLayout(dlg)
  for line in ('Your music, games and system in one dashboard.','Play music in Spotify or another Windows media app. Basic playback needs no Premium account.','Click the blossom in the lower-right corner to open settings.','Optional: connect Spotify Premium for remote devices and automatic playlists.','Optional: enable the system audio visualiser or OpenRGB lighting in settings.'):
   label=QLabel(line);label.setWordWrap(True);layout.addWidget(label)
  done=QPushButton('Get started');done.clicked.connect(dlg.accept);layout.addWidget(done)
  dlg.exec();self.display_options['welcome_seen']=True;self.write_setting('dashboard-display.json',self.display_options)
 def open_updates(self):
  dlg=InlinePanel(self);dlg.setWindowTitle('Sakura updates');layout=QVBoxLayout(dlg)
  status=QLabel(self.updater.status);status.setWordWrap(True);layout.addWidget(status)
  check=QPushButton('Check for updates');check.clicked.connect(self.updater.check);layout.addWidget(check)
  download=QPushButton('Download update');download.clicked.connect(self.updater.download);layout.addWidget(download)
  install=QPushButton('Install update and restart');layout.addWidget(install)
  def apply():
   try:self.updater.launch();dlg.accept();self.close()
   except OSError as e:status.setText(str(e))
  install.clicked.connect(apply)
  def update():
   status.setText(self.updater.status);check.setEnabled(not self.updater.busy);download.setEnabled(bool(self.updater.asset) and not self.updater.busy and not self.updater.ready);install.setEnabled(bool(self.updater.ready))
  timer=QTimer(dlg);timer.timeout.connect(update);timer.start(500);update();dlg.exec();timer.stop()
 def refresh_profile(self):
  name=self.sync_status.get('detected_game','Desktop');profile=read_profiles(self.sync_root).get(name,{})
  self.game_profile=profile if isinstance(profile,dict) and profile.get('enabled') else {}
  fps=self.game_profile.get('fps') or self.display_options.get('fps',60)
  interval=33 if fps==30 else 16
  if self.timer.interval()!=interval:self.timer.setInterval(interval)
 def open_profiles(self):profiles_panel(self);self.refresh_profile()
 def open_discord(self):discord_panel(self)
 def responsive(self):return self.width()/max(1,self.height())<2.2
 def refresh_sync(self):
  try:
   state=json.loads((self.sync_root/'dashboard-status.json').read_text())
   self.sync_status=state if abs(time.time()-state['time'])<5 else {}
  except (OSError,ValueError,KeyError,TypeError):self.sync_status={}
 def ensure_sync(self):
  if self.sync_status or self.sync_started:return
  root=Path(__file__).resolve().parent/'game_sync'
  python=Path(sys.executable); entry=root/'app.py'
  if getattr(sys,'frozen',False):root=Path(sys.executable).resolve().parent;python=Path(sys.executable);entry=python
  if not python.is_file() or not entry.is_file():
   self.sync_error='Game Sync installation not found';return
  try:
   subprocess.Popen(([str(python),'--game-sync','--background'] if getattr(sys,'frozen',False) else [str(python),str(entry),'--background']),cwd=root,creationflags=subprocess.CREATE_NO_WINDOW,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
  if not rows:add(['Trailmakers','585420','trailmakers.exe','0WJzQWmJyamJTDxct2Tzw8'])
  hint=QLabel('Steam games are detected automatically. Import installed games, then optionally paste a Spotify playlist link for each game. Blank playlists leave music unchanged.');hint.setWordWrap(True);layout.addWidget(hint)
  def discover():
   try:library=json.loads((self.sync_root/'steam-library.json').read_text())
   except (OSError,ValueError):library={}
   existing={table.item(i,1).text() for i in range(table.rowCount()) if table.item(i,1)}
   count=0
   for appid,(name,folder) in sorted(library.items(),key=lambda x:x[1][0].casefold()):
    if appid not in existing:
     add([name,appid,'','']);count+=1
   status.setText(f'Added {count} installed games. Save game mappings to keep them.' if library else 'No Steam library found yet. Open Steam and try again.')
  button=QPushButton('Import installed Steam games');button.clicked.connect(discover);layout.addWidget(button)
  button=QPushButton('Refresh Steam library');button.clicked.connect(lambda:request('discover'));layout.addWidget(button)
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
  action=None
  try:
   if self.editor.active:
    options=[('Finish',self.editor.toggle),('Reset layout',self.editor.reset),('Cancel',lambda:None)]
   else:
    choice=Bloom(self,self.accent,['Lighting','Games','Connections','Appearance','System','Hide to tray'],main_menu=True).exec()-2
    if choice==5:
     QTimer.singleShot(0,self.hide_to_tray);return
    groups=[
     [('Lighting settings',lambda:self.open_settings(1))],
     [('Game settings',lambda:self.open_settings(0)),('Game profiles',self.open_profiles),('Advanced',self.open_sync_settings)],
     [('Spotify',self.open_player),('Discord',self.open_discord)],
     [('Display settings',lambda:self.open_settings(2)),('Hide lyrics' if getattr(self,'lyrics_window',None) else 'Show lyrics',self.open_lyrics),('Edit layout',self.editor.toggle),('Windowed' if self.isFullScreen() else 'Fullscreen',self.toggle_fullscreen)],
     [('System settings',self.open_system),('Updates',self.open_updates),('Exit Sakura',self.close)]
    ]
    if choice<0:return
    options=groups[choice]
   selection=Bloom(self,self.accent,[label for label,fn in options]).exec()-2
   if selection==-1 and not self.editor.active:action=self.bloom_again
   elif 0<=selection<len(options):action=options[selection][1]
  finally:self.panel_active=False
  if action:action()
 def hide_to_tray(self):
  if not QSystemTrayIcon.isSystemTrayAvailable():
   QMessageBox.information(self,'Sakura','System tray is unavailable. Sakura will stay visible.');return
  if self.tray is None:
   pix=QPixmap(64,64);pix.fill(Qt.GlobalColor.transparent)
   p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing);paint_settings_petal(p,32,32,27,QColor('#f478d7'));p.end()
   self.tray=QSystemTrayIcon(QIcon(pix),self);self.tray.setToolTip('Sakura Dashboard')
   self.tray_menu=QMenu(self)
   self.tray_menu.addAction('Restore Sakura',self.restore_from_tray)
   self.tray_menu.addAction('Exit Sakura',self.exit_from_tray)
   self.tray.setContextMenu(self.tray_menu)
   self.tray.activated.connect(self.tray_activated)
  self.tray_hidden=True
  self.game_autohide.hidden=False;self.game_autohide.misses=0
  QApplication.instance().setQuitOnLastWindowClosed(False)
  self.tray.show()
  lyrics=getattr(self,'lyrics_window',None)
  self.tray_lyrics=bool(lyrics and lyrics.isVisible())
  if self.tray_lyrics:lyrics.hide()
  self.hide()
 def tray_activated(self,reason):
  if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick):self.restore_from_tray()
 def restore_from_tray(self):
  if not self.tray_hidden:return
  self.tray_hidden=False
  self.tray_restore_until=time.monotonic()+5
  self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,False)
  self.show();self.raise_();self.activateWindow()
  QApplication.instance().setQuitOnLastWindowClosed(True)
  lyrics=getattr(self,'lyrics_window',None)
  if self.tray_lyrics and lyrics:lyrics.show()
  self.tray_lyrics=False
  if self.tray:self.tray.hide()
 def exit_from_tray(self):
  if self.close():QApplication.instance().quit()
 def bloom_again(self):QTimer.singleShot(0,self.bloom_menu)
 def toggle_fullscreen(self):
  self.showNormal() if self.isFullScreen() else self.showFullScreen()

 def open_system(self):
  dlg=InlinePanel(self);dlg.setWindowTitle('Sakura / System');layout=QVBoxLayout(dlg)
  info=QLabel();info.setWordWrap(True);layout.addWidget(info)
  log=QLabel();log.setWordWrap(True);layout.addWidget(log)
  state=self.sync_root
  def update():
   info.setText('Game Sync: '+('Running' if self.sync_status else 'Offline')+'\nSpotify: '+(self.connect.state.get('device_error') or ('Connected' if self.connect.state.get('time') else 'Connecting'))+'\n'+self.audio_status+'\n'+str(self.sync_status.get('scanner','Scanner offline'))+'\n'+str(self.sync_status.get('rgb','Lighting offline')))
  def restart():
   if self.sync_status:self.write_setting('dashboard-advanced.request',dict(action='quit'));self.sync_started=False;QTimer.singleShot(2500,self.ensure_sync)
   else:self.sync_started=False;self.ensure_sync()
   log.setText('Game Sync restart requested.')
  def logs():
   try:log.setText('\n'.join((state/'update.log').read_text().splitlines()[-12:]))
   except OSError:log.setText('No update log available.')
  def relaunch():
   try:
    subprocess.Popen([sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve())],creationflags=subprocess.CREATE_NO_WINDOW,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    dlg.accept();self.close()
   except OSError as e:log.setText(str(e))
  def history():
   panel=InlinePanel(self);panel.setWindowTitle('Notifications');items=QVBoxLayout(panel)
   toggle=QCheckBox('Mirror Windows notifications');toggle.setChecked(self.notifications.enabled);items.addWidget(toggle)
   def change(value):
    self.notifications.enabled=value
    if value:self.notifications.backend.enable()
    else:self.notifications.backend.close()
   toggle.toggled.connect(change)
   status=QLabel();status.setWordWrap(True);items.addWidget(status)
   timer=QTimer(panel);timer.timeout.connect(lambda:status.setText(self.notifications.backend.status));timer.start(500);status.setText(self.notifications.backend.status)
   for app,title,body,stamp in self.notifications.history:
    label=QLabel(time.strftime('%H:%M',time.localtime(stamp))+'  ·  '+app+'\n'+title+'\n'+body);label.setTextFormat(Qt.TextFormat.PlainText);label.setWordWrap(True);items.addWidget(label)
   panel.exec();timer.stop()
  for label,fn in [('Notifications',history),('Restart Game Sync',restart),('Relaunch Sakura',relaunch),('Updates',lambda:dlg.done(3)),('Getting started',lambda:dlg.done(4)),('View update log',logs),('Copy diagnostics',lambda:QApplication.clipboard().setText(info.text()+'\n'+log.text())),('Exit Sakura',lambda:(dlg.accept(),self.close()))]:
   button=QPushButton(label);button.clicked.connect(fn);layout.addWidget(button)
  timer=QTimer(dlg);timer.timeout.connect(update);timer.start(1000);update();result=dlg.exec();timer.stop()
  if result==3:self.open_updates()
  elif result==4:self.welcome()
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
  return bool(self.media.state.get('playing')) if self.media.state else bool(self.player.get('is_playing'))
 def command(self,action,**data):
  if action in ('play','pause','previous','next') and self.media.state:self.media.submit(action)
  else:self.connect.submit(action,**data)
 def open_player(self):
  dlg=InlinePanel(self);dlg.setWindowTitle('Connections / Spotify');layout=QFormLayout(dlg)
  hint=QLabel('Local playback works without an account. Remote Spotify devices and automatic playlists require Premium.');hint.setWordWrap(True);layout.addRow(hint)
  status=QLabel('Discovering Spotify Connect devices…');status.setWordWrap(True);layout.addRow(status)
  devices=QComboBox();layout.addRow('Playback device',devices)
  transfer=QPushButton('Transfer playback');transfer.setEnabled(False);layout.addRow(transfer)
  refresh=QPushButton('Refresh devices');layout.addRow(refresh)
  volume=QSlider(Qt.Orientation.Horizontal);volume.setRange(0,100);volume.setValue(int((self.player.get('device') or {}).get('volume_percent') or 0));layout.addRow('Volume',volume)
  playlist=QLineEdit();playlist.setPlaceholderText('Spotify playlist link or ID');layout.addRow('Playlist',playlist)
  play=QPushButton('Play playlist');layout.addRow(play)
  shuffle=QCheckBox('Shuffle');shuffle.setChecked(bool(self.player.get('shuffle_state',False)));layout.addRow(shuffle)
  repeat=QComboBox();repeat.addItems(['off','context','track']);repeat.setCurrentText(self.player.get('repeat_state','off'));layout.addRow('Repeat',repeat)
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
  timer=QTimer(dlg);timer.timeout.connect(update);timer.start(500);update()
  if self.connect.read('token.json').get('refresh_token'):send('refresh')
  else:status.setText('Optional Spotify connection: use account settings to sign in.')
  result=dlg.exec();timer.stop()
  if result==2:self.open_account()
  elif result==3:self.open_discord()
 def poll_player(self):
  try:
   state=self.connect.state
   if abs(time.time()-state.get('time',0))<45:self.player=state.get('player') or {};self.devices=state.get('devices',[])
   else:self.player={};self.devices=[]
   local=self.media.state
   if local:
    self.track=(local.get('title') or 'Nothing playing',local.get('artist',''))
    if (local.get('key'),local.get('art'))!=self.media_key:
     self.media_key=(local.get('key'),local.get('art'));self.art=QImage.fromData(local.get('art',b''));self.art_url=''
     if not self.art.isNull():
      c=self.art.scaled(1,1,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation).pixelColor(0,0);h,s,v,_=c.getHsvF();self.art_accent=QColor.fromHsvF(max(0,h),max(.35,min(.8,s)),.95)
    return
   self.media_key=None;self.track=('Nothing playing','')
   item=self.player.get('item') or {};images=(item.get('album') or {}).get('images',[]);url=images[0].get('url','') if images else ''
   if url.startswith('https://open.spotify.com/image/'):url=url.replace('https://open.spotify.com/image/','https://i.scdn.co/image/',1)
   if url and url!=self.art_url and url.startswith(('https://','http://','file://')):
    with urllib.request.urlopen(url,timeout=4) as response:raw=response.read(4000000)
    image=QImage.fromData(raw)
    if not image.isNull():
     small=image.scaled(24,24);colors=[small.pixelColor(x,y) for x in range(24) for y in range(24)];colors.sort(key=lambda c:c.saturationF()*min(1,c.valueF()*2),reverse=True);c=colors[:100];avg=QColor(*(int(sum(getattr(v,k)() for v in c)/len(c)) for k in ('red','green','blue')));h,s,v,_=avg.getHsvF();self.art_accent=QColor.fromHsvF(max(0,h),max(.35,min(.8,s)),.95);self.art=image;self.art_url=url
   if not url:self.art=QImage();self.art_url='';self.art_accent=QColor('#f478d7')
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
  edit_layout=QPushButton('Edit layout');edit_layout.clicked.connect(lambda:dlg.done(4));dform.addRow(edit_layout)
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
  auto_hide=QCheckBox();auto_hide.setChecked(bool(view.get('game_autohide',True)));dform.addRow('Hide dashboard when a game is on this monitor',auto_hide)
  petals=QCheckBox();petals.setChecked(bool(view.get('petals',True)));dform.addRow('Animated petals',petals)
  visual=QCheckBox();visual.setChecked(bool(view.get('visualiser',False)));dform.addRow('System audio visualiser (WASAPI)',visual)
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
  if result==4:self.editor.toggle();return
  if result!=QDialog.DialogCode.Accepted:return
  data=dict(mode=('auto','manual','off')[mode.currentIndex()],brightness=brightness.value())
  data.update({k:[v.red(),v.green(),v.blue()] for k,v in colors.items()});data.update({k:v.isChecked() for k,v in checks.items()})
  try:
   self.sync_root.mkdir(parents=True,exist_ok=True);tmp=self.sync_root/'dashboard-rgb.tmp';tmp.write_text(json.dumps(data,indent=2));tmp.replace(self.sync_root/'dashboard-rgb.json')
   game={k:v.isChecked() for k,v in controls.items()};game.update(combat=combat.text().strip(),device=device.currentText().strip(),threshold=threshold.value())
   self.write_setting('dashboard-game.request',game)
   self.write_setting('dashboard-display.json',dict(self.display_options,petals=petals.isChecked(),game_autohide=auto_hide.isChecked(),visualiser=visual.isChecked(),fps=30 if fps.currentIndex()==0 else 60,album_theme=adaptive_theme.isChecked()));self.load_display()
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
 def audio(self):pass
 def audio_error(self):pass
 def update_spectrum(self):
  self.win_audio.enabled=bool(self.display_options.get('visualiser',False))
  if not self.win_audio.enabled:
   self.spectrum.reset();self.bars=[0]*80;self.audio_status='System audio visualiser disabled';return
  self.spectrum.feed(self.win_audio.read());self.bars=self.spectrum.tick();self.audio_status=self.win_audio.status

 def closeEvent(self, event):
  QApplication.instance().setQuitOnLastWindowClosed(True)
  if self.tray:self.tray.hide()
  self.poll_stop.set();self.notifications.close()
  if getattr(self,'lyrics_window',None):self.lyrics_window.close()
  self.discord.disconnect();self.connect.closed=True;self.win_audio.closed=True;self.media.closed=True
  if self.sync_status:
   try:self.write_setting('dashboard-advanced.request',dict(action='quit'))
   except OSError:pass
  self.sync_timer.stop()
  self.audio_timer.stop()
  if self.capture.state() != QProcess.NotRunning:
   self.capture.kill()
   self.capture.waitForFinished(500)
  super().closeEvent(event)

 def theme_target(self):
  return QColor(self.game_profile.get('accent','#f478d7')) if self.game_profile else self.art_accent if self.display_options.get('album_theme',False) else QColor('#f478d7')
 def now_playing(self):
  local=self.media.state
  if local:return (local.get('title') or 'Nothing playing',local.get('artist',''))
  state=self.connect.state
  item=(state.get('player') or {}).get('item') or {} if abs(time.time()-state.get('time',0))<45 else {}
  return (item.get('name') or 'Nothing playing',', '.join(a.get('name','') for a in item.get('artists',[])))
 def poll_artwork(self):
  while not self.poll_stop.is_set():
   self.poll_player();self.poll_stop.wait(.25)
 def poll(self):
  while not self.poll_stop.is_set():
   try:self.stats=(psutil.cpu_percent(),psutil.virtual_memory().percent,'—',self.gpu_stats.read())
   except Exception:pass
   self.poll_stop.wait(2)
 def open_lyrics(self):
  panel=getattr(self,'lyrics_window',None)
  if panel is not None:
   self.lyrics_window=None;panel.close();self.update();return
  panel=LyricsWindow(self);self.lyrics_window=panel
  self.update()
 def mousePressEvent(self,e):
  if self.editor.active:
   if e.button()==Qt.MouseButton.LeftButton:
    if self.settings_hit.contains(e.position()):self.bloom_menu()
    else:self.editor.press(e.position())
   return
  if e.button()==Qt.MouseButton.LeftButton and self.notifications.hit.contains(e.position()):
   self.notifications.dismiss();self.update();return
  if any(isinstance(c,InlinePanel) and c.isVisible() for c in self.children()):return
  if self.responsive():
   for action,rect in self.hit_regions.items():
    if rect.contains(e.position()):
     if action=='settings':self.bloom_menu()
     elif action=='connections':self.open_player()
     elif action=='discord':self.open_discord()
     elif action=='toggle':self.command('pause' if self.playing() else 'play')
     else:self.command(action)
     return
   return
  x=e.position().x()*1920/max(1,self.width());y=e.position().y()*720/max(1,self.height())
  if e.button()==Qt.MouseButton.RightButton:self.circle_points=[(x,y)]
  elif math.hypot(x-1850,y-665)<32:self.bloom_menu()
  else:
   for action,rect in self.hit_regions.items():
    if rect.contains(e.position()):
     if action=='connections':self.open_player()
     else:self.command(('pause' if self.playing() else 'play') if action=='toggle' else action)
     return
  super().mousePressEvent(e)
 def mouseMoveEvent(self,e):
  if self.editor.move(e.position()):return
  if self.circle_points:self.circle_points.append((e.position().x()*1920/max(1,self.width()),e.position().y()*720/max(1,self.height())))
 def mouseReleaseEvent(self,e):
  if self.editor.release():return
  pts=self.circle_points;self.circle_points=[]
  if len(pts)<12:return
  cx=sum(x for x,y in pts)/len(pts);cy=sum(y for x,y in pts)/len(pts);r=[math.hypot(x-cx,y-cy) for x,y in pts];avg=sum(r)/len(r)
  angles=[math.atan2(y-cy,x-cx) for x,y in pts];travel=sum(math.atan2(math.sin(b-a),math.cos(b-a)) for a,b in zip(angles,angles[1:]))
  if 65<avg<280 and abs(travel)>5.35 and max(r)-min(r)<avg*.85 and math.dist(pts[0],pts[-1])<avg*.5:self.bloom_menu()
 def paintEvent(self,e):
  self.editor.begin()
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
  text(70,40,900,55,'桜  /  SAKURA',23,self.accent,500)
  with self.editor.section(p,'clock',QRectF(1300,14,550,76)):
   text(1300,14,550,76,time.strftime('%H:%M'),46)
  with self.editor.section(p,'artwork',QRectF(70,150,200,200)) as artwork_map:
   if not self.art.isNull():p.drawImage(QRectF(70,150,200,200),self.art)
   else:p.fillRect(QRectF(70,150,200,200),QColor('#39253e'))
  title,artist=self.now_playing()
  with self.editor.section(p,'track',QRectF(300,195,880,130)) as track_map:
   text(300,195,880,90,title,40);text(300,280,880,45,artist,23,'#c393cc')
  with self.editor.section(p,'playback',QRectF(300,330,880,60)) as playback_map:
   p.setBrush(QColor('#f5d9ef'));p.setPen(Qt.NoPen)
   for x,direction in ((335,-1),(495,1)):
    path=QPainterPath();path.moveTo(x-12*direction,348);path.lineTo(x+9*direction,360);path.lineTo(x-12*direction,372);path.closeSubpath();p.drawPath(path);p.drawRoundedRect(QRectF(x+11*direction-2,348,4,24),1,1)
   if self.playing():
    p.drawRoundedRect(QRectF(405,347,7,26),2,2);p.drawRoundedRect(QRectF(419,347,7,26),2,2)
   else:
    path=QPainterPath();path.moveTo(405,345);path.lineTo(430,360);path.lineTo(405,375);path.closeSubpath();p.drawPath(path)
   text(550,330,630,60,(self.player.get('device') or {}).get('name','Spotify devices'),18,self.accent)
  self.hit_regions={a:playback_map.mapRect(QRectF(*r)) for a,r in [('previous',(300,330,70,60)),('toggle',(380,330,70,60)),('next',(460,330,70,60)),('connections',(550,330,630,60))]}
  lyrics=getattr(self,'lyrics_window',None)
  notice_active=(self.notifications.visible() or self.editor.active) and not self.editor.has_custom('notifications')
  if lyrics:
   with self.editor.section(p,'lyrics',QRectF(1270,135,600,310)):
    paint_lyrics(p,lyrics,QRectF(1270,135,600,310),self.accent)
  with self.editor.section(p,'visualiser',QRectF(70,410,1080,190)) as visualiser_map:
   for i,b in enumerate(self.bars):
    base=505 if lyrics and notice_active else 600;h=max(2,min(1,b)*(95 if lyrics and notice_active else 190));c=QColor(self.accent);c.setAlpha(185);p.setBrush(c);p.setPen(Qt.NoPen);p.drawRoundedRect(QRectF(70+i*13.5,base-h,5,h),2,2)
  import re
  gpu=re.match(r'\s*(\d+(?:\.\d+)?)\s*/\s*(.*)',str(self.stats[3]))
  entries=[('CPU',self.stats[0],self.stats[2]),('GPU',float(gpu.group(1)) if gpu else float(str(self.stats[3]).rstrip('%')) if str(self.stats[3]).rstrip('%').isdigit() else None,gpu.group(2) if gpu else ''),('MEMORY',self.stats[1],'')]
  with self.editor.section(p,'resources',QRectF(1300,(460 if lyrics else 220),530,(135 if lyrics else 180))) as resources_map:
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
  if self.updater.asset:text(70,645,1100,35,'Update available — open System',13,self.accent)
  elif not sync:text(70,645,1100,35,'Game Sync offline',13,'#a982b5')
  text(1300,640,470,45,time.strftime('%A  •  %d %B'),16,'#a982b5')
  self.settings_hit=p.transform().mapRect(paint_settings_petal(p,1850,665,22,self.accent))
  slot=QRectF(70,515,1080,80) if lyrics else QRectF(1300,420,500,120)
  slot=p.transform().mapRect(slot)
  p.resetTransform();self.notifications.paint(p,slot,self.accent,self.editor)
  p.scale(self.width()/1920,self.height()/720)
  self.editor.overlay(p,self.accent)
  if self.circle_points:
   p.setPen(QPen(self.accent,2))
   for a,b in zip(self.circle_points,self.circle_points[1:]):p.drawLine(QPointF(*a),QPointF(*b))
app=QApplication(sys.argv)
from PySide6.QtCore import QLockFile
state=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Sakura'/'state';state.mkdir(parents=True,exist_ok=True)
lock=QLockFile(str(state/'dashboard.lock'));lock.setStaleLockTime(0)
if not lock.tryLock(0):sys.exit(0)
w=Dashboard();w.show();sys.exit(app.exec())
