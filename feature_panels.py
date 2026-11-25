from PySide6.QtWidgets import QVBoxLayout,QFormLayout,QLabel,QPushButton,QLineEdit,QComboBox,QCheckBox,QSpinBox,QMessageBox
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QColor
import json
from inline_panel import InlinePanel
def read_profiles(root):
 try:
  data=json.loads((root/'game-profiles.json').read_text())
  return data if isinstance(data,dict) else {}
 except (OSError,ValueError):return {}
def profiles_panel(owner):
 dlg=InlinePanel(owner);dlg.setWindowTitle('Game profiles');layout=QFormLayout(dlg)
 profiles=read_profiles(owner.sync_root)
 games={'Desktop','Trailmakers','ULTRAKILL','Minecraft','Rocket League',*profiles}
 try:games.update(row[0] for row in json.loads((owner.sync_root/'games.json').read_text()))
 except (OSError,ValueError,TypeError):pass
 try:games.update(row[0] for row in json.loads((owner.sync_root/'steam-library.json').read_text()).values())
 except (OSError,ValueError,TypeError):pass
 game=QComboBox();game.setEditable(True);game.addItems(sorted(games));layout.addRow('Game',game)
 enabled=QCheckBox('Apply custom profile when game is detected');layout.addRow(enabled)
 accent=QLineEdit();layout.addRow('Dashboard colour (hex)',accent)
 rgb=QCheckBox('Override automatic RGB colour');layout.addRow(rgb)
 color=QLineEdit();layout.addRow('RGB colour (hex)',color)
 fps=QComboBox();fps.addItems(['Use normal setting','30 FPS','60 FPS']);layout.addRow('Dashboard refresh rate',fps)
 petals=QComboBox();petals.addItems(['Use normal setting','On','Off']);layout.addRow('Animated petals',petals)
 hint=QLabel('Music playlists are configured under game mappings. Manual lighting and Off mode always take priority. Default display settings return when the game closes.');hint.setWordWrap(True);layout.addRow(hint)
 def load(*_):
  p=profiles.get(game.currentText(),{})
  enabled.setChecked(bool(p.get('enabled',False)));accent.setText(p.get('accent','#f478d7'));rgb.setChecked(bool(p.get('rgb_enabled',False)));color.setText(p.get('rgb','#f478d7'));fps.setCurrentIndex({30:1,60:2}.get(p.get('fps'),0));petals.setCurrentIndex({True:1,False:2}.get(p.get('petals'),0))
 game.currentTextChanged.connect(load);load()
 def save():
  name=game.currentText().strip();a=QColor(accent.text());c=QColor(color.text())
  if not name or not a.isValid() or not c.isValid():hint.setText('Enter a game name and valid hex colours, such as #ff3366.');return
  profiles[name]=dict(enabled=enabled.isChecked(),accent=a.name(),rgb_enabled=rgb.isChecked(),rgb=c.name(),fps={1:30,2:60}.get(fps.currentIndex()),petals={1:True,2:False}.get(petals.currentIndex()))
  try:owner.write_setting('game-profiles.json',profiles);hint.setText('Saved profile for '+name)
  except OSError as e:hint.setText(str(e))
 button=QPushButton('Save profile');button.clicked.connect(save);layout.addRow(button);dlg.exec()
def discord_panel(owner):
 dlg=InlinePanel(owner);dlg.setWindowTitle('Discord • Read-only connection');layout=QFormLayout(dlg)
 hint=QLabel('Create a Discord bot, invite it to your server, then enter its bot token and your user/server IDs. Enable Message Content Intent only if you want messages from one selected channel. Tokens are kept in memory for this session only.');hint.setWordWrap(True);layout.addRow(hint)
 import importlib.util
 if importlib.util.find_spec('discord') is None:
  install=QPushButton('Install optional Discord support');layout.addRow(install)
  def install_discord():
   import sys,subprocess,threading
   install.setEnabled(False);hint.setText('Installing Discord support. Reopen this panel after installation.')
   def work():
    try:subprocess.run([sys.executable,'-m','pip','install','discord.py>=2.5,<3'],check=True,timeout=120)
    except Exception:pass
   threading.Thread(target=work,daemon=True).start()
  install.clicked.connect(install_discord)
 token=QLineEdit();token.setEchoMode(QLineEdit.EchoMode.Password);layout.addRow('Bot token',token)
 user=QLineEdit();guild=QLineEdit();channel=QLineEdit()
 for name,field in [('Your Discord user ID',user),('Server ID',guild),('Text channel ID (optional)',channel)]:layout.addRow(name,field)
 link=QPushButton('Discord developer portal');link.clicked.connect(lambda:__import__('webbrowser').open('https://discord.com/developers/applications'));layout.addRow(link)
 status=QLabel();status.setWordWrap(True);status.setTextFormat(Qt.TextFormat.PlainText);layout.addRow(status)
 voice=QLabel();voice.setWordWrap(True);voice.setTextFormat(Qt.TextFormat.PlainText);layout.addRow(voice)
 messages=QLabel();messages.setWordWrap(True);messages.setTextFormat(Qt.TextFormat.PlainText);layout.addRow(messages)
 def connect():
  if not token.text().strip() or not user.text().isdigit() or not guild.text().isdigit() or (channel.text() and not channel.text().isdigit()):status.setText('Enter valid numeric IDs and a bot token.');return
  owner.discord.connect(token.text().strip(),int(user.text()),int(guild.text()),int(channel.text() or '0'));token.clear()
 button=QPushButton('Connect bot');button.clicked.connect(connect);layout.addRow(button)
 button=QPushButton('Disconnect');button.clicked.connect(owner.discord.disconnect);layout.addRow(button)
 def update():
  s=owner.discord.state;status.setText(s.get('status',''));voice.setText(('Voice: '+s['channel']+'\n'+'\n'.join(n+(' • muted' if m else '')+(' • deafened' if d else '') for n,m,d in s.get('voice',[]))) if s.get('channel') else 'Not in a visible server voice channel');messages.setText('\n'.join(n+': '+m for n,m in s.get('messages',[])[-8:]))
 timer=QTimer(dlg);timer.timeout.connect(update);timer.start(500);update();dlg.exec();timer.stop()
