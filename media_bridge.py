"""Loopback-only, paired browser media bridge."""
import json,secrets,threading,time,hmac
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
class MediaBridge:
 def __init__(self):
  self.token=secrets.token_urlsafe(24);self.data={};self.pending=None;self.lock=threading.Lock();self.server=None;self.status='Ready'
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
     state={k:str(d.get(k,''))[:300] for k in ('title','episode','source','artist')}
     state.update(playing=bool(d.get('playing')),position=max(0,float(d.get('position',0))),duration=max(0,float(d.get('duration',0))),time=time.monotonic())
     with owner.lock:
      owner.data=state;command=owner.pending;owner.pending=None
     self.reply(200,{'command':command})
    except (ValueError,TypeError,OverflowError):self.reply(400,{})
  try:
   self.server=ThreadingHTTPServer(('127.0.0.1',8765),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start()
  except OSError:self.status='Port 8765 unavailable'
 def current(self):
  with self.lock:return dict(self.data) if time.monotonic()-self.data.get('time',0)<8 else {}
 def command(self,action):
  if action in ('play','pause','toggle'):
   with self.lock:self.pending=action
 def stop(self):
  if self.server:self.server.shutdown();self.server.server_close()
