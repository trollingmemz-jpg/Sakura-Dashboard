"""Opt-in Windows render-endpoint loopback. Never opens a physical microphone."""
import threading
import time
import warnings

class WindowsAudio:
 def __init__(self):
  self.enabled=False
  self.closed=False
  self.data=b''
  self.status='Windows audio disabled'
  self.target=''
  self.outputs=()
  self.active_name=''
  self.generation=0
  self.lock=threading.Lock()
  threading.Thread(target=self.run,daemon=True).start()

 def read(self):
  with self.lock:
   data=self.data
   self.data=b''
  return data

 def clear(self):
  with self.lock:
   self.data=b''
   self.generation+=1

 def wait(self,seconds):
  until=time.monotonic()+seconds
  while not self.closed and time.monotonic()<until:
   time.sleep(.1)

 @staticmethod
 def pcm(frames,rate,np):
  frames=np.asarray(frames,dtype=np.float32)
  if frames.ndim==1:frames=frames[:,None]
  if frames.shape[1]==1:frames=np.repeat(frames,2,axis=1)
  elif frames.shape[1]>2:frames=frames[:,:2]
  if rate!=48000 and len(frames):
   positions=np.arange(round(len(frames)*48000/rate))*rate/48000
   frames=np.column_stack([np.interp(positions,np.arange(len(frames)),frames[:,i]) for i in range(2)])
  return (np.clip(np.nan_to_num(frames),-1,1)*32767).astype('<i2').tobytes()

 def run(self):
  preferred={}
  while not self.closed:
   try:
    import soundcard as sc
    import numpy as np
    speakers=sc.all_speakers()
    self.outputs=tuple((str(s.id),str(s.name)) for s in speakers)
    if not self.enabled:
     if self.active_name:self.clear()
     self.active_name=''
     self.status='System audio visualiser disabled'
     self.wait(1)
     continue
    selected=self.target
    speaker=next((s for s in speakers if str(s.id)==selected),None) if selected else sc.default_speaker()
    if speaker is None:
     self.status='Selected audio output unavailable; reconnect it or choose Automatic'
     self.wait(1)
     continue
    endpoint=str(speaker.id)
    # Exact matching is important: fuzzy matching can choose a physical microphone.
    mic=next((m for m in sc.all_microphones(include_loopback=True) if str(m.id)==endpoint and getattr(m,'isloopback',False)),None)
    if mic is None:raise RuntimeError('Render loopback endpoint unavailable')
    options=[(48000,2),(44100,2),(48000,None),(44100,None)]
    if endpoint in preferred:
     options.remove(preferred[endpoint]);options.insert(0,preferred[endpoint])
    failure=None
    for rate,channels in options:
     if self.closed or not self.enabled or self.target!=selected:break
     try:
      with mic.recorder(samplerate=rate,channels=channels,blocksize=1024) as rec:
       self.clear()
       self.active_name=str(speaker.name)
       self.status='WASAPI loopback: '+self.active_name
       check_at=time.monotonic()+1
       heard=False
       quiet_since=time.monotonic()
       while self.enabled and not self.closed and self.target==selected:
        frames=rec.record(numframes=1024)
        data=self.pcm(frames,rate,np)
        if data:
         preferred[endpoint]=(rate,channels)
         with self.lock:self.data=(self.data+data)[-65536:]
         if np.max(np.abs(frames),initial=0)>0.0001:
          heard=True;quiet_since=time.monotonic()
          self.status='WASAPI loopback: '+self.active_name
         elif time.monotonic()-quiet_since>2:
          self.status='WASAPI connected (no audio signal): '+self.active_name
        now=time.monotonic()
        if now>=check_at:
         check_at=now+1
         current=sc.all_speakers()
         self.outputs=tuple((str(s.id),str(s.name)) for s in current)
         if not any(str(s.id)==endpoint for s in current):break
         if not selected and str(sc.default_speaker().id)!=endpoint:break
      failure=None
      break
     except Exception as e:
      failure=e
      if preferred.get(endpoint)==(rate,channels):preferred.pop(endpoint,None)
     finally:
      self.active_name=''
      self.clear()
    if failure is not None:
     self.status='Audio capture unavailable: '+type(failure).__name__
     self.wait(1)
   except Exception as e:
    self.active_name=''
    self.clear()
    self.status='Audio output unavailable: '+type(e).__name__
    self.wait(1)
