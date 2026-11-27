"""Dashboard-owned Spotify Connect worker. No Game Sync process dependency."""
import os,json,time,queue,threading,tempfile,urllib.request,urllib.parse,urllib.error
from pathlib import Path
from token_lock import token_lock
class Connect:
 def __init__(self,root):
  self.root=Path(root);self.queue=queue.Queue();self.state={};self.result={};self.closed=False
  threading.Thread(target=self.run,daemon=True).start()
 def read(self,name):
  try:return json.loads((self.root/name).read_text())
  except (OSError,ValueError):return {}
 def submit(self,action,**data):
  self.queue.put((action,data))
 def token(self):
  # Share the existing PKCE login; keep refresh-token writes atomic.
  self.root.mkdir(parents=True,exist_ok=True)
  with token_lock(self.root/'spotify-token.lock'):
   token=self.read('token.json');client=self.read('settings.json').get('client','')
   if not client or not token.get('refresh_token'):raise RuntimeError('Connect Spotify in account settings first.')
   if time.time()>=token.get('expires_at',0)-60:
    req=urllib.request.Request('https://accounts.spotify.com/api/token',data=urllib.parse.urlencode(dict(client_id=client,grant_type='refresh_token',refresh_token=token['refresh_token'])).encode())
    with urllib.request.urlopen(req,timeout=8) as r:new=json.load(r)
    token.update(new);token['expires_at']=time.time()+new['expires_in']
    fd,path=tempfile.mkstemp(dir=self.root,prefix='spotify-token-')
    try:
     with os.fdopen(fd,'w') as f:json.dump(token,f)
     os.replace(path,self.root/'token.json')
    finally:
     if os.path.exists(path):os.unlink(path)
   return token['access_token']
 def login(self,client):
  import secrets,hashlib,base64,http.server,webbrowser
  client=client.strip()
  if not client:raise ValueError('Enter your Spotify developer client ID.')
  verifier=secrets.token_urlsafe(64);state=secrets.token_urlsafe(24);challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
  redirect='http://127.0.0.1:8700/callback';result={}
  class Handler(http.server.BaseHTTPRequestHandler):
   def do_GET(self):
    url=urllib.parse.urlsplit(self.path);q=urllib.parse.parse_qs(url.query)
    if url.path!='/callback' or q.get('state',[''])[0]!=state:self.send_error(400);return
    result.update(q);self.send_response(200);self.end_headers();self.wfile.write(b'Return to Sakura.')
   def log_message(self,*args):pass
  with http.server.HTTPServer(('127.0.0.1',8700),Handler) as server:
   server.timeout=1
   webbrowser.open('https://accounts.spotify.com/authorize?'+urllib.parse.urlencode(dict(client_id=client,response_type='code',redirect_uri=redirect,code_challenge_method='S256',code_challenge=challenge,state=state,scope='user-read-playback-state user-modify-playback-state user-read-currently-playing')))
   deadline=time.monotonic()+180
   while not result and not self.closed and time.monotonic()<deadline:server.handle_request()
  if 'code' not in result:raise RuntimeError('Spotify sign-in cancelled or timed out.')
  req=urllib.request.Request('https://accounts.spotify.com/api/token',data=urllib.parse.urlencode(dict(client_id=client,grant_type='authorization_code',code=result['code'][0],redirect_uri=redirect,code_verifier=verifier)).encode())
  with urllib.request.urlopen(req,timeout=12) as r:token=json.load(r)
  token['expires_at']=time.time()+token['expires_in']
  self.root.mkdir(parents=True,exist_ok=True)
  with token_lock(self.root/'spotify-token.lock'):
   cfg=self.read('settings.json');cfg['client']=client
   for name,data in [('token.json',token),('settings.json',cfg)]:
    fd,path=tempfile.mkstemp(dir=self.root,prefix='sakura-auth-')
    try:
     with os.fdopen(fd,'w') as f:json.dump(data,f)
     os.replace(path,self.root/name)
    finally:
     if os.path.exists(path):os.unlink(path)
 def call(self,path,method='GET',body=None):
  req=urllib.request.Request('https://api.spotify.com/v1/me/player'+path,method=method,headers={'Authorization':'Bearer '+self.token(),'Content-Type':'application/json'},data=json.dumps(body).encode() if body is not None else None)
  try:
   with urllib.request.urlopen(req,timeout=8) as r:
    raw=r.read();return json.loads(raw) if raw.strip() else {}
  except urllib.error.HTTPError as e:
   if e.code==429:self.backoff=time.monotonic()+min(300,max(10,int(e.headers.get('Retry-After','30'))))
   raise RuntimeError('Spotify HTTP '+str(e.code)+': '+e.read().decode(errors='replace')[:240]) from e
 def refresh(self):
  state=dict(time=time.time(),player=self.state.get('player',{}),devices=self.state.get('devices',[]),device_error='',player_error='')
  try:state['devices']=self.call('/devices').get('devices',[])
  except Exception as e:state['device_error']=str(e)
  if time.monotonic()>=self.backoff:
   try:state['player']=self.call('')
   except Exception as e:state['player_error']=str(e)
  self.state=state
 def run(self):
  self.backoff=0.;next_poll=0.
  while not self.closed:
   try:action,data=self.queue.get(timeout=.5)
   except queue.Empty:
    if time.monotonic()>=max(next_poll,self.backoff):
     self.refresh();next_poll=time.monotonic()+12
    continue
   error=''
   try:
    if time.monotonic()<self.backoff:raise RuntimeError('Spotify rate limit: retry shortly.')
    if action=='login':self.login(data['client'])
    elif action=='transfer':self.call('','PUT',{'device_ids':[str(data['device'])],'play':True})
    elif action in ('play','pause'):self.call('/'+action,'PUT')
    elif action in ('next','previous'):self.call('/'+action,'POST')
    elif action=='volume':self.call('/volume?volume_percent='+str(max(0,min(100,int(data['value']))))+('&device_id='+urllib.parse.quote(str(data['device']),safe='') if data.get('device') else ''),'PUT')
    elif action=='shuffle':self.call('/shuffle?state='+str(bool(data['value'])).lower(),'PUT')
    elif action=='repeat':self.call('/repeat?state='+str(data['value']),'PUT')
    elif action=='playlist':
     value=str(data['value']).strip().split('?')[0].split('/')[-1].split(':')[-1]
     if len(value)!=22 or not value.isalnum():raise ValueError('Enter a Spotify playlist link or ID.')
     self.call('/play','PUT',{'context_uri':'spotify:playlist:'+value})
    self.refresh()
    if action=='refresh':error=self.state.get('device_error','')
   except Exception as e:error=str(e)
   self.result=dict(time=time.time(),action=action,error=error)
   next_poll=time.monotonic()+12
