"""Check official GitHub beta releases and download only verified installer assets."""
import json,urllib.request,urllib.parse,threading,hashlib,os,re,subprocess
from pathlib import Path
class Updater:
 def __init__(self,root):
  self.root=Path(root);self.status='Checking for updates…';self.asset=None;self.ready=None;self.busy=False
  try:self.build=int((Path(__file__).parent/'build-id.txt').read_text().strip())
  except (OSError,ValueError):self.build=0
  self.check()
 def check(self):
  if self.busy:return
  self.busy=True;threading.Thread(target=self._check,daemon=True).start()
 def _check(self):
  try:
   req=urllib.request.Request('https://api.github.com/repos/trollingmemz-jpg/Sakura-Dashboard/releases?per_page=30',headers={'User-Agent':'Sakura-Windows'})
   with urllib.request.urlopen(req,timeout=15) as r:releases=json.load(r)
   options=[]
   for release in releases:
    m=re.fullmatch(r'windows-beta-(\d+)',release.get('tag_name',''))
    if not m or release.get('draft'):continue
    for asset in release.get('assets',[]):
     if asset.get('name')=='Sakura-Windows-Beta.exe' and asset.get('digest','').startswith('sha256:'):
      options.append((int(m[1]),asset))
   if not options:self.status='No verified beta installer found.';return
   build,asset=max(options,key=lambda a:a[0])
   self.asset=asset if build>self.build and self.build else None
   self.status='Update available' if self.asset else 'Up to date' if self.build else 'Development build — updates disabled'
  except Exception as e:self.status='Update check unavailable: '+str(e)
  finally:self.busy=False
 def download(self):
  if self.busy or not self.asset:return
  self.busy=True;threading.Thread(target=self._download,daemon=True).start()
 def _download(self):
  target=self.root/'Sakura-Windows-Beta.exe';tmp=target.with_suffix('.part')
  try:
   asset=self.asset;url=asset['browser_download_url']
   if not url.startswith('https://github.com/trollingmemz-jpg/Sakura-Dashboard/releases/download/'):raise ValueError('Unexpected download source')
   digest=hashlib.sha256();total=0;size=int(asset['size'])
   with urllib.request.urlopen(url,timeout=30) as r,open(tmp,'wb') as f:
    while True:
     data=r.read(1024*1024)
     if not data:break
     total+=len(data)
     if total>size:raise ValueError('Unexpected installer size')
     digest.update(data);f.write(data);self.status=f'Downloading update: {100*total//max(1,size)}%'
   if total!=size or 'sha256:'+digest.hexdigest()!=asset['digest']:raise ValueError('Installer verification failed')
   os.replace(tmp,target);self.ready=target;self.status='Update downloaded and verified. Ready to install.'
  except Exception as e:self.status='Update failed: '+str(e)
  finally:
   if tmp.exists():tmp.unlink()
   self.busy=False
 def launch(self):
  if not self.ready:raise RuntimeError('Download an update first.')
  subprocess.Popen([str(self.ready)],cwd=str(self.root))
