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
     import datetime
     timeline=session.get_timeline_properties()
     position=timeline.position.total_seconds()
     playing=int(info.playback_status)==4
     if playing:
      try:position+=max(0,(datetime.datetime.now(datetime.timezone.utc)-timeline.last_updated_time).total_seconds())
      except (TypeError,AttributeError):pass
     duration=timeline.end_time.total_seconds()
     position=max(0,min(duration,position)) if duration>0 else max(0,position)
     changed=key!=old
     if changed:art=b'';old=key
     self.state=dict(title=props.title,artist=props.artist,album=props.album_title,app=session.source_app_user_model_id,playing=playing,art=art,key=key,position=position,duration=duration,sampled=time.monotonic())
     if changed and props.thumbnail:
      try:
       stream=await props.thumbnail.open_read_async()
       try:
        if 0<stream.size<=4000000:
         reader=DataReader(stream);await reader.load_async(int(stream.size))
         buf=bytearray(int(stream.size));reader.read_bytes(buf);art=bytes(buf)
       finally:stream.close()
      except Exception:pass
      self.state=dict(self.state,art=art)
    else:self.state={};old=None;art=b''
    while True:
     try:action=self.commands.get_nowait()
     except queue.Empty:break
     if session:
      method={'play':'try_play_async','pause':'try_pause_async','next':'try_skip_next_async','previous':'try_skip_previous_async'}.get(action)
      if method:await getattr(session,method)()
   except Exception:self.state={}
   await asyncio.sleep(.25)
