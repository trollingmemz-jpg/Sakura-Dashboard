"""Local, opt-in media history. Never store browser cookies or query tokens."""
import sqlite3,time,math,re
from urllib.parse import urlsplit,urlunsplit
def clean_url(url):
 p=urlsplit(str(url))
 host=(p.hostname or '').lower()
 allowed=any(host==x or host.endswith('.'+x) for x in ('miruro.cx','miruro.tv','mangadex.org'))
 if not allowed or p.scheme!='https' or p.username or p.password:return ''
 return urlunsplit(('https',host,p.path,'',''))
def normalize(d):
 url=clean_url(d.get('url',''))
 if not url:raise ValueError('Unsupported media URL')
 source='MangaDex' if 'mangadex.org' in urlsplit(url).hostname else 'Miruro'
 kind='manga' if source=='MangaDex' else 'anime'
 title=str(d.get('title','')).strip()[:250]
 part=str(d.get('episode','')).strip()[:80]
 if not title or not part:raise ValueError('Title and episode/chapter required')
 def num(k):
  n=float(d.get(k,0))
  if not math.isfinite(n):raise ValueError('Invalid progress')
  return max(0,min(n,10000000))
 pos,duration=num('position'),num('duration')
 return dict(url=url,source=source,kind=kind,title=title,part=part,position=min(pos,duration) if duration else pos,duration=duration,playing=bool(d.get('playing')),genres=','.join(str(x)[:40] for x in d.get('genres',[])[:12]) if isinstance(d.get('genres'),list) else '')
class Library:
 def __init__(self,path):
  self.path=path
  with self.db() as db:
   db.execute('CREATE TABLE IF NOT EXISTS history (url TEXT, part TEXT, source TEXT, kind TEXT, title TEXT, position REAL, duration REAL, genres TEXT, updated REAL, PRIMARY KEY(url,part))')
 def db(self):return sqlite3.connect(self.path,timeout=5)
 def record(self,d):
  with self.db() as db:
   db.execute('INSERT INTO history VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(url,part) DO UPDATE SET title=excluded.title,position=excluded.position,duration=excluded.duration,genres=CASE WHEN excluded.genres="" THEN history.genres ELSE excluded.genres END,updated=excluded.updated',(d['url'],d['part'],d['source'],d['kind'],d['title'],d['position'],d['duration'],d['genres'],time.time()))
 def recent(self,kind=None):
  with self.db() as db:
   db.row_factory=sqlite3.Row
   return [dict(x) for x in db.execute('SELECT * FROM history WHERE (? IS NULL OR kind=?) ORDER BY updated DESC LIMIT 100',(kind,kind))]
 def clear(self):
  with self.db() as db:db.execute('DELETE FROM history')
 def remove(self,url,part):
  with self.db() as db:db.execute('DELETE FROM history WHERE url=? AND part=?',(url,part))
 def preferences(self):
  weights={}
  for r in self.recent():
   for g in filter(None,r['genres'].split(',')):weights[g]=weights.get(g,0)+1+(r['position']/r['duration'] if r['duration'] else 0)
  return sorted(weights,key=weights.get,reverse=True)[:4]
