"""WASAPI default-output loopback, opt-in; captures system mix, not just Spotify."""
import threading,time
class WindowsAudio:
 def __init__(self):
  self.enabled=False;self.closed=False;self.data=b'';self.status='Windows audio disabled'
  self.lock=threading.Lock();threading.Thread(target=self.run,daemon=True).start()
 def read(self):
  with self.lock:data=self.data;self.data=b''
  return data
 def run(self):
  while not self.closed:
   if not self.enabled:time.sleep(.2);continue
   try:
    import soundcard as sc,numpy as np
    speaker=sc.default_speaker()
    mic=sc.get_microphone(speaker.id,include_loopback=True)
    with mic.recorder(samplerate=48000,channels=2,blocksize=1024) as rec:
     self.status='Windows WASAPI • system audio'
     while self.enabled and not self.closed:
      frames=rec.record(numframes=1024)
      data=(np.clip(frames,-1,1)*32767).astype('<i2').tobytes()
      with self.lock:self.data=(self.data+data)[-32768:]
   except Exception as e:
    self.status='Audio unavailable: '+str(e);time.sleep(3)
