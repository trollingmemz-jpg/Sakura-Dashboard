"""Optional bundled lifecycle chimes, played locally at reduced volume."""
from pathlib import Path
from PySide6.QtCore import QUrl,QEventLoop,QTimer
class SakuraSounds:
 def __init__(self,owner):
  self.owner=owner;self.effect=None;self.closed=False
  try:
   from PySide6.QtMultimedia import QSoundEffect
   self.effect=QSoundEffect(owner)
  except Exception:pass
 def play(self,name,wait=False):
  if not self.effect or not self.owner.display_options.get('sounds_enabled',True):return False
  path=Path(__file__).resolve().parent/'sounds'/(name+'.wav')
  if not path.is_file():return False
  try:
   from PySide6.QtMultimedia import QSoundEffect
   self.effect.stop()
   self.effect.setVolume(max(0,min(100,int(self.owner.display_options.get('sounds_volume',70))))/100)
   self.effect.setSource(QUrl.fromLocalFile(str(path)))
   self.effect.setLoopCount(1)
   if not wait:self.effect.play();return True
   # Shutdown must not truncate the chime; bounded event loop keeps Qt responsive.
   loop=QEventLoop();timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit)
   started=[False]
   def changed():
    if self.effect.isPlaying():started[0]=True
    elif started[0] or self.effect.status()==QSoundEffect.Status.Error:loop.quit()
   self.effect.playingChanged.connect(changed);self.effect.statusChanged.connect(changed)
   try:
    self.effect.play();changed()
    if self.effect.status()!=QSoundEffect.Status.Error:
     timer.start(5200);loop.exec()
   finally:
    timer.stop();self.effect.playingChanged.disconnect(changed);self.effect.statusChanged.disconnect(changed);self.effect.stop()
   return True
  except Exception:return False
 def startup(self):
  if self.closed:return
  first=not self.owner.display_options.get('sounds_welcomed',False)
  if self.play('welcome' if first else 'open') and first:
   self.owner.display_options['sounds_welcomed']=True
   try:self.owner.write_setting('dashboard-display.json',self.owner.display_options)
   except OSError:pass
 def shutdown(self):
  if self.closed:return
  self.closed=True;self.play('close',wait=True)
