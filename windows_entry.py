"""Single executable entry for the packaged Dashboard and background Game Sync."""
import sys,os,runpy,traceback
from pathlib import Path
def main():
 root=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Sakura'/'state';root.mkdir(parents=True,exist_ok=True)
 if '--smoke-test' in sys.argv:
  import PySide6,psutil,numpy,soundcard,cv2,PIL,openrgb
  return
 try:
  if '--game-sync' in sys.argv:
   sys.argv.remove('--game-sync')
   base=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
   sys.path.insert(0,str(base/'game_sync'))
   runpy.run_path(str(base/'game_sync'/'app.py'),run_name='__main__')
  else:
   from PySide6.QtWidgets import QApplication
   from PySide6.QtCore import QLockFile
   # Dashboard creates the QApplication itself.
   import dashboard
 except Exception:
  (root/'crash.log').write_text(traceback.format_exc(),encoding='utf-8')
  import ctypes
  ctypes.windll.user32.MessageBoxW(None,'Sakura encountered an error. See '+str(root/'crash.log'),'Sakura',0x10)
if __name__=='__main__':main()
