import ctypes
from ctypes import wintypes
import psutil
import json
import re
from pathlib import Path
from PySide6.QtCore import QObject, QTimer
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
 def restore(self):
  if self.hidden:
   self.hidden=False
   if getattr(self.window,'tray_hidden',False):return
   self.window.setAttribute(__import__('PySide6.QtCore',fromlist=['Qt']).Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
   self.window.show()
 def tick(self):
  w=self.window
  if getattr(w,'tray_hidden',False):
   self.hidden=False;self.misses=0;return
  if getattr(w,'panel_active',False) or getattr(w,'tray_restore_until',0)>__import__('time').monotonic():return
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

 def on_monitor(self,names):
  if not names:return False
  u=ctypes.WinDLL('user32',use_last_error=True)
  u.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];u.MonitorFromWindow.restype=wintypes.HMONITOR
  u.IsWindowVisible.argtypes=[wintypes.HWND];u.IsIconic.argtypes=[wintypes.HWND]
  u.GetWindowTextLengthW.argtypes=[wintypes.HWND];u.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
  u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
  u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
  if not self.hidden:self.monitor=u.MonitorFromWindow(int(self.window.winId()),2)
  found=False
  callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
  @callback
  def visit(hwnd,_):
   nonlocal found
   if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd) or u.MonitorFromWindow(hwnd,2)!=self.monitor:return True
   rect=wintypes.RECT()
   if not u.GetWindowRect(hwnd,ctypes.byref(rect)) or rect.right-rect.left<160 or rect.bottom-rect.top<100:return True
   length=u.GetWindowTextLengthW(hwnd)
   if not length:return True
   title=ctypes.create_unicode_buffer(min(length+1,4096));u.GetWindowTextW(hwnd,title,len(title))
   pid=wintypes.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
   try:exe=Path(psutil.Process(pid.value).name()).stem
   except (psutil.Error,OSError):return True
   if matches(names,exe) or (exe.casefold() in ('java','javaw') and matches(names,title.value)):
    found=True;return False
   return True
  u.EnumWindows.argtypes=[callback,wintypes.LPARAM];u.EnumWindows(visit,0)
  return found
