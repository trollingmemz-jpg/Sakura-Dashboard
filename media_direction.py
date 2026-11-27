"""Observe MPRIS transport calls on the session bus, without grabbing input."""
import re,subprocess,threading,time
class MediaDirection:
 def __init__(self,callback):
  self.callback=callback;self.closed=False;self.process=None;self.status='Starting'
  threading.Thread(target=self.run,daemon=True).start()
 def run(self):
  while not self.closed:
   try:
    self.process=subprocess.Popen(['dbus-monitor','--session',"type='method_call',interface='org.mpris.MediaPlayer2.Player',member='Previous'","type='method_call',interface='org.mpris.MediaPlayer2.Player',member='Next'"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    self.status='Monitoring MPRIS transport'
    if self.closed:self.process.terminate()
    for line in self.process.stdout:
     if self.closed:break
     if not line.startswith('method call '):continue
     match=re.search(r'\bmember=(Previous|Next)\s*$',line)
     if match:self.callback(-1 if match.group(1)=='Previous' else 1)
    self.process.wait();self.status='Session bus monitor unavailable'
   except OSError:self.status='dbus-monitor unavailable'
   finally:
    if self.process and self.process.poll() is None:self.process.terminate()
    self.process=None
   if not self.closed:time.sleep(3)
 def close(self):
  self.closed=True
  if self.process and self.process.poll() is None:
   try:self.process.terminate()
   except OSError:pass
