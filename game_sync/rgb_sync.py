"""Windows RGB discovery and synchronisation through the existing OpenRGB SDK."""
import json
import math
import os
import time
import threading
from pathlib import Path
from PySide6.QtCore import QObject, Signal

CATEGORIES = {1:'ram',2:'gpu',5:'keyboard',6:'mouse'}
def selected_devices(devices, profile, keyboard=True, ram=True, mouse=True):
 flags = {1:ram,2:bool(profile.get('gpu',True)),5:keyboard,6:mouse}
 return [d for d in devices if flags.get(int(d.type),False) and len(d.leds)>0]

class RGBSync(QObject):
 report=Signal(str)
 def __init__(self,parent=None):
  super().__init__(parent)
  self.state=(False,False,True,True,True,False,{})
  self.stop=threading.Event()
  self.root=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Sakura'/'state'
  threading.Thread(target=self.run,daemon=True).start()
 def update(self,enabled,locked,keyboard,ram,mouse,scanning=True,profile=None):
  self.state=(enabled,locked,keyboard,ram,mouse,scanning,profile or {})
 def inventory(self,devices,status):
  try:
   self.root.mkdir(parents=True,exist_ok=True)
   data={'time':time.time(),'status':status,'devices':[{'name':str(d.name),'type':int(d.type),'category':CATEGORIES.get(int(d.type),'other'),'leds':len(d.leds)} for d in devices]}
   tmp=self.root/'rgb-inventory.tmp'
   tmp.write_text(json.dumps(data),encoding='utf-8');tmp.replace(self.root/'rgb-inventory.json')
  except (OSError,ValueError,TypeError,AttributeError):pass
 def run(self):
  client=None;devices=[];last_sdk=None;last_status='';previous=None;retry=0.;scan=0.;mix=0.;base=(244.,120.,215.)
  def report(msg):
   nonlocal last_status
   if msg!=last_status:self.report.emit(msg);last_status=msg
  def disconnect():
   nonlocal client,devices,last_sdk
   if client:
    try:client.disconnect()
    except Exception:pass
   client=None;devices=[];last_sdk=None
  try:
   while not self.stop.wait(.10):
    enabled,locked,keyboard,ram,mouse,scanning,profile=self.state
    now=time.monotonic()
    if client is None and now>=retry:
     retry=now+8
     try:
      from openrgb import OpenRGBClient
      # Keep Sakura's existing port first, then the standard SDK port.
      for port in (6743,6742):
       try:
        client=OpenRGBClient('127.0.0.1',port)
        break
       except Exception:client=None
      if client is None:raise RuntimeError('Start the OpenRGB SDK server')
      scan=0.
     except Exception as e:
      disconnect();self.inventory([],str(e));report('RGB discovery: '+str(e));continue
    if client is None:continue
    selection=(keyboard,ram,mouse,bool(profile.get('gpu',True)),enabled)
    if now>=scan:
     scan=now+15
     try:
      client.update()
      devices=list(client.devices)
      self.inventory(devices,'Connected')
      last_sdk=None
     except Exception as e:
      disconnect();self.inventory([],str(e));report('RGB discovery: '+str(e));retry=now+8;continue
    if selection!=previous:last_sdk=None;previous=selection
    targets=selected_devices(devices,profile,keyboard,ram,mouse)
    if not enabled:
     report(f'RGB sync off · {len(devices)} devices discovered');continue
    locked=locked and profile.get('mode','auto')=='auto'
    mix+=((1. if locked else 0.)-mix)*.35
    if abs(mix-(1. if locked else 0.))<.01:mix=1. if locked else 0.
    strength=.40+.60*(1+math.sin(now*math.tau/2.4))/2
    target=profile.get('manual',(244,120,215)) if profile.get('mode')=='manual' else profile.get('scanning',(179,108,255)) if scanning else profile.get('idle',(244,120,215))
    base=tuple(a+(b-a)*.35 if abs(b-a)>=.5 else float(b) for a,b in zip(base,target))
    rgb=tuple(round((a*(1-mix)+b*mix*strength)*profile.get('brightness',100)/100) for a,b in zip(base,profile.get('combat',(240,24,134))))
    if rgb!=last_sdk:
     try:
      from openrgb.utils import RGBColor
      for d in targets:d.set_colors([RGBColor(*rgb) for _ in d.leds],fast=True)
      last_sdk=rgb
     except Exception as e:
      disconnect();self.inventory([],str(e));retry=now+8;report('SDK: '+str(e));continue
    report(f'OpenRGB: {len(targets)} selected / {len(devices)} discovered')
  finally:disconnect()
