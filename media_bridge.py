"""Loopback-only, paired browser media bridge."""
import json,secrets,threading,time,hmac
from media_library import Library,normalize
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
class MediaBridge:
 def __init__(self,root):
  self.token=secrets.token_urlsafe(24);self.data={};self.pending=None;self.lock=threading.Lock();self.server=None;self.status='Ready';self.library=Library(root/'media-history.sqlite3');self.enabled=False;self.last_key=None;self.last_save=0
 def start(self):
  owner=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def reply(self,code,data):
    payload=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
   def do_POST(self):
    if self.path!='/media' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+owner.token):self.reply(403,{});return
    try:
     n=int(self.headers.get('Content-Length','0'))
     if not 0<n<=8192:raise ValueError()
     d=json.loads(self.rfile.read(n))
     if not isinstance(d,dict):raise ValueError()
     state=normalize(d);state['time']=time.monotonic()
     with owner.lock:
      if not owner.enabled:self.reply(200,{'command':None});return
      owner.data=state
      key=(state['url'],state['part'])
      now=time.monotonic()
      if owner.last_key!=key or now-owner.last_save>=15:
       owner.library.record(state);owner.last_save=now;owner.last_key=key
      command=owner.pending;owner.pending=None
     self.reply(200,{'command':command})
    except (ValueError,TypeError,OverflowError):self.reply(400,{})
  try:
   self.server=ThreadingHTTPServer(('127.0.0.1',8770),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start()
  except OSError:self.status='Port 8770 unavailable'
 def current(self):
  with self.lock:return dict(self.data) if self.enabled and time.monotonic()-self.data.get('time',0)<8 else {}
 def privacy(self,enabled):
  with self.lock:
   self.enabled=enabled
   if not enabled:self.data={};self.pending=None;self.last_key=None
 def command(self,action):
  if action in ('play','pause','toggle'):
   with self.lock:self.pending=action
 def stop(self):
  if self.server:self.server.shutdown();self.server.server_close()
