import json
import re
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtWidgets import QApplication

def normalized(value):
 return re.sub(r'[^a-z0-9]', '', str(value).casefold())

def aliases(root,name):
 names={normalized(name)}
 try:
  rows=json.loads((Path(root)/'games.json').read_text())
  for row in rows:
   if isinstance(row,list) and len(row)>=3 and normalized(row[0])==normalized(name):
    names.add(normalized(Path(str(row[2]).replace('\\','/')).stem))
 except (OSError,ValueError,TypeError):pass
 return {n for n in names if len(n)>=4}

def matches(names,*values):
 return any(n==normalized(v) or (len(n)>=5 and n in normalized(v)) for n in names for v in values)

class AutoHide(QObject):
 def __init__(self,window):
  super().__init__(window);self.window=window;self.hidden=False;self.monitor=None;self.misses=0
  self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(900)
  self.windows=[];self.ready=False;self.script=None
  self.setup_kwin()
  QApplication.instance().aboutToQuit.connect(self.cleanup)
 def restore(self):
  if self.hidden:
   self.hidden=False
   self.window.setAttribute(__import__('PySide6.QtCore',fromlist=['Qt']).Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
   self.window.show()
 def tick(self):
  w=self.window
  if not w.display_options.get('game_autohide',True):
   self.restore();return
  name=w.sync_status.get('detected_game','Desktop')
  if not name or name=='Desktop':
   self.restore();return
  if not self.hidden and (not w.isVisible() or w.isMinimized() or QApplication.activeModalWidget() or getattr(getattr(w,'editor',None),'active',False)):return
  try:
   hit=self.on_monitor(aliases(w.sync_root,name))
  except Exception:hit=None
  if hit is True:
   self.misses=0
   if not self.hidden:
    self.hidden=True;w.hide()
  elif self.hidden:
   self.misses+=1
   if self.misses>=2:self.restore()

 def setup_kwin(self):
  import os,tempfile
  from PySide6.QtDBus import QDBusConnection,QDBusInterface,QDBusMessage
  self.bus=QDBusConnection.sessionBus()
  self.service='local.Sakura.AutoHide.p'+str(os.getpid())
  self.plugin='sakura-autohide-'+str(os.getpid())
  if not self.bus.registerService(self.service):return
  if not self.bus.registerObject('/AutoHide',self,QDBusConnection.RegisterOption.ExportAllSlots):return
  self.scripting=QDBusInterface('org.kde.KWin','/Scripting','org.kde.kwin.Scripting',self.bus)
  script="""
function publish(){
 var rows=[];
 for (var w of workspace.windowList()){
  if (!w.normalWindow || w.minimized || !w.output) continue;
  rows.push([String(w.resourceClass),String(w.desktopFileName),String(w.caption),String(w.output.name)]);
 }
 callDBus(SERVICE,'/AutoHide','','receiveWindows',JSON.stringify(rows));
}
function watch(w){
 w.frameGeometryChanged.connect(publish);
 w.minimizedChanged.connect(publish);
 w.captionChanged.connect(publish);
 if(w.outputChanged) w.outputChanged.connect(publish);
}
workspace.windowAdded.connect(function(w){watch(w);publish();});
workspace.windowRemoved.connect(publish);
workspace.windowActivated.connect(publish);
workspace.windowList().forEach(watch);
publish();
""".replace('SERVICE',json.dumps(self.service))
  try:
   with tempfile.NamedTemporaryFile(mode='w',suffix='.js',delete=False) as f:
    f.write(script);self.script=f.name
   reply=self.scripting.call('loadScript',self.script,self.plugin)
   args=reply.arguments()
   if reply.type()==QDBusMessage.MessageType.ErrorMessage or not args or int(args[0])<0:return
   self.runner=QDBusInterface('org.kde.KWin','/Scripting/Script'+str(args[0]),'org.kde.kwin.Script',self.bus)
   self.runner.call('run')
  except (OSError,ValueError,TypeError):pass
 @Slot(str)
 def receiveWindows(self,payload):
  try:
   if len(payload)>1000000:return
   rows=json.loads(payload)
   if isinstance(rows,list):
    self.windows=[r for r in rows if isinstance(r,list) and len(r)==4 and all(isinstance(v,str) for v in r)]
    self.ready=True
  except ValueError:pass
 def on_monitor(self,names):
  if not self.ready:return None
  if not self.hidden:
   screen=self.window.screen()
   self.monitor=screen.name() if screen else None
  if not self.monitor:return None
  return any(output==self.monitor and matches(names,resource,desktop) for resource,desktop,title,output in self.windows)
 def cleanup(self):
  try:
   if hasattr(self,'scripting'):self.scripting.call('unloadScript',self.plugin)
   if self.script:Path(self.script).unlink(missing_ok=True)
   if hasattr(self,'bus'):self.bus.unregisterService(self.service)
  except Exception:pass
