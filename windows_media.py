"""Local Windows media sessions: no Spotify API account required."""
import asyncio,threading,time,queue
class LocalMedia:
 def __init__(self):
  self.state={};self.commands=queue.Queue();self.closed=False
  threading.Thread(target=self.run,daemon=True).start()
 def submit(self,action):self.commands.put(action)
 def run(self):
  try:asyncio.run(self.loop())
  except Exception:self.state={}
 async def loop(self):
  from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
  from winrt.windows.storage.streams import DataReader
  manager=await Manager.request_async()
  old=None;art=b''
  while not self.closed:
   try:
    session=manager.get_current_session()
    if session:
     props=await session.try_get_media_properties_async()
     info=session.get_playback_info()
     key=(session.source_app_user_model_id,props.title,props.artist)
     if key!=old:
      art=b'';old=key
      if props.thumbnail:
       try:
        stream=await props.thumbnail.open_read_async()
        if 0<stream.size<=4000000:
         reader=DataReader(stream);await reader.load_async(int(stream.size))
         buf=bytearray(int(stream.size));reader.read_bytes(buf);art=bytes(buf)
        stream.close()
       except Exception:pass
     self.state=dict(title=props.title,artist=props.artist,app=session.source_app_user_model_id,playing=int(info.playback_status)==4,art=art,key=key)
    else:self.state={};old=None;art=b''
    while True:
     try:action=self.commands.get_nowait()
     except queue.Empty:break
     if session:
      method={'play':'try_play_async','pause':'try_pause_async','next':'try_skip_next_async','previous':'try_skip_previous_async'}.get(action)
      if method:await getattr(session,method)()
   except Exception:self.state={}
   await asyncio.sleep(.75)
