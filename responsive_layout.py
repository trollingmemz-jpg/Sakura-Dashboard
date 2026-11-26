"""Adaptive dashboard layout in actual widget coordinates, with matching hit regions."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QColor,QFont,QLinearGradient,QPen
import time
from live_lyrics import paint_lyrics
def paint_responsive(o):
 p=QPainter(o);p.setRenderHint(QPainter.Antialiasing)
 w,h=o.width(),o.height();portrait=w<h;pad=max(12,min(w,h)*.045)
 accent=o.accent;g=QLinearGradient(0,0,w,h);g.setColorAt(0,QColor('#100b20'));g.setColorAt(1,accent.darker(430));p.fillRect(o.rect(),g)
 o.hit_regions={}
 def text(x,y,ww,hh,s,size,color='#f5d9ef',align=Qt.AlignLeft):
  f=QFont('Sans Serif');f.setPixelSize(max(10,int(size)));p.setFont(f);p.setPen(QColor(color));p.drawText(QRectF(x,y,max(1,ww),hh),Qt.AlignVCenter|align,p.fontMetrics().elidedText(str(s),Qt.ElideRight,max(1,int(ww))))
 def button(x,y,ww,hh,label,action):
  r=QRectF(x,y,ww,hh);text(x+4,y,ww-8,hh,label,min(18,hh*.55),accent,Qt.AlignHCenter);o.hit_regions[action]=r
 def stats(x,y,ww,hh):
  import re
  gpu=str(o.stats[3]);match=re.match(r'\s*(\d+(?:\.\d+)?)\s*/\s*(.*)',gpu)
  gpu_pct=float(match.group(1)) if match else None
  gpu_temp=match.group(2) if match else '—'
  entries=[('CPU',o.stats[0],str(o.stats[2])),('GPU',gpu_pct,gpu_temp),('MEMORY',o.stats[1],'')]
  row=min(hh/3, max(42,min(100,h*.105)))
  for i,(label,val,detail) in enumerate(entries):
   yy=y+i*row
   label_size=max(10,min(19,row*.23));value_size=max(12,min(29,row*.35))
   text(x,yy,ww*.43,row*.43,label,label_size,'#c393cc')
   reading=(f'{val:.0f}%' if val is not None else '—')+('  •  '+detail if detail and detail!='—' else '')
   text(x+ww*.43,yy,ww*.57,row*.43,reading,value_size,align=Qt.AlignRight)
   bar=QRectF(x,yy+row*.60,ww,max(1.5,min(3,row*.045)))
   p.setPen(Qt.NoPen);p.setBrush(QColor('#352b40'));p.drawRoundedRect(bar,3,3)
   if val is not None:
    p.setBrush(accent);p.drawRoundedRect(QRectF(bar.x(),bar.y(),bar.width()*max(0,min(100,val))/100,bar.height()),3,3)
 item=o.player.get('item') or {};local=getattr(getattr(o,'media',None),'state',{})
 title=o.track[0] if local else item.get('name') or o.track[0];artist=o.track[1] if local else ', '.join(a.get('name','') for a in item.get('artists',[])) or o.track[1]
 text(pad,pad,w*.5-pad,40,'桜 / SAKURA',min(25,w*.055),accent)
 with o.editor.section(p,'clock',QRectF(w*.5,pad,w*.5-pad,40)):
  text(w*.5,pad,w*.5-pad,40,time.strftime('%H:%M'),min(38,w*.075),align=Qt.AlignRight)
 top=pad+56;bottom=h-pad-48;space=max(100,bottom-top)
 lyrics=getattr(o,'lyrics_window',None)
 notice=getattr(o,'notifications',None)
 active=bool(notice and notice.visible())
 cap_h=min(100,max(32,space*.19))
 cap_gap=min(12,space*.025)
 cap_y=bottom-30-cap_h
 cap_rect=None
 if portrait:
  aw=min(w-2*pad,space*.34,360);ax=(w-aw)/2;ay=top
  tx=pad;ty=ay+aw+8;tw=w-2*pad
  sy=ty+max(110,134*max(.75,min(1.45,h/720)));sh=max(45,(bottom-sy)*.58);sx=pad;sw=tw
  vy=sy+sh+4;vh=max(0,bottom-vy-38);vx=pad;vw=tw
 else:
  aw=min(space*.32,w*.16);ax=pad;ay=top
  tx=ax+aw+pad;ty=top;tw=max(50,w*.59-tx)
  sx=w*.64;sy=top;sw=w-pad-sx;sh=space*.70
  vx=pad;vy=top+max(aw,134*max(.75,min(1.45,h/720)))+16;vw=w*.59-pad;vh=max(0,bottom-vy-38)
 with o.editor.section(p,'artwork',QRectF(ax,ay,aw,aw)) as artwork_map:
  art=o.art
  if not art.isNull():
   scaled=art.scaled(int(aw),int(aw),Qt.KeepAspectRatio,Qt.SmoothTransformation);p.drawImage(QPointF(ax+(aw-scaled.width())/2,ay+(aw-scaled.height())/2),scaled)
  else:p.fillRect(QRectF(ax,ay,aw,aw),QColor('#39253e'))
 unit=max(.75,min(1.45,h/720))
 with o.editor.section(p,'track',QRectF(tx,ty,tw,96*unit)) as track_map:
  text(tx,ty,tw,24*unit,'',15*unit,accent)
  text(tx,ty+26*unit,tw,40*unit,title,min(36*unit,tw*.10))
  text(tx,ty+68*unit,tw,28*unit,artist,min(22*unit,tw*.07),'#c393cc')
 with o.editor.section(p,'playback',QRectF(tx,ty+98*unit,tw,36*unit)) as playback_map:
  bw=min(48*unit,(tw-12)/3)
  for i,(label,action) in enumerate([('‹','previous'),('Ⅱ' if o.playing() else '▶','toggle'),('›','next')]):button(tx+i*(bw+6),ty+98*unit,bw,36*unit,label,action)
 for action in ('previous','toggle','next'):
  if action in o.hit_regions:o.hit_regions[action]=playback_map.mapRect(o.hit_regions[action])
 if active:
  if portrait or lyrics:
   if portrait and sy+sh>cap_y-cap_gap:sh=max(1,cap_y-cap_gap-sy);vy=sy+sh+4
   vh=max(0,min(vh,cap_y-cap_gap-vy))
   cap_rect=QRectF(vx,cap_y,vw,cap_h)
  else:
   sh=max(1,min(sh,cap_y-cap_gap-sy))
   cap_rect=QRectF(sx,cap_y,sw,cap_h)
 if lyrics:
  if portrait:
   with o.editor.section(p,'lyrics',QRectF(sx,sy,sw,sh*.56)):
    paint_lyrics(p,lyrics,QRectF(sx,sy,sw,sh*.56),accent)
   with o.editor.section(p,'resources',QRectF(sx,sy+sh*.56,sw,sh*.44)):
    stats(sx,sy+sh*.56,sw,sh*.44)
  else:
   lyric_h=space*.52
   with o.editor.section(p,'lyrics',QRectF(sx,sy,sw,lyric_h)):
    paint_lyrics(p,lyrics,QRectF(sx,sy,sw,lyric_h),accent)
   rh=max(45,min(space*.36,bottom-sy-lyric_h-pad*.4-30))
   with o.editor.section(p,'resources',QRectF(sx,sy+lyric_h+pad*.4,sw,rh)):
    stats(sx,sy+lyric_h+pad*.4,sw,rh)
 else:
  with o.editor.section(p,'resources',QRectF(sx,sy,sw,sh)):
   stats(sx,sy,sw,sh)
 with o.editor.section(p,'visualiser',QRectF(vx,vy,vw,vh)) as visualiser_map:
  if vh>8:
   for i,b in enumerate(o.bars):
    bh=max(2,min(1,b)*vh);p.setPen(Qt.NoPen);c=QColor(accent);c.setAlpha(185);p.setBrush(c);p.drawRoundedRect(QRectF(vx+i*vw/80,vy+vh-bh,max(1,vw/80*.38),bh),2,2)
 game=o.sync_status.get('detected_game','Desktop');voice=o.discord.state.get('channel','')
 text(pad,bottom-30,w-2*pad,24,('Game: '+game if game!='Desktop' else '')+('  •  Voice: '+voice if voice else ''),12,'#a982b5')
 bw=min(95,(w-2*pad-60)/3)
 for i,(label,action) in enumerate([('Music','connections'),('Media','media'),('Discord','discord')]):button(pad+i*(bw+6),h-pad-36,bw,36,label,action)
 from bloom import paint_settings_petal
 o.hit_regions['settings']=o.settings_hit=paint_settings_petal(p,w-pad-18,h-pad-18,18,accent)
 if notice:
  notice.paint(p,cap_rect if cap_rect is not None else QRectF(),accent)
 o.editor.overlay(p,accent)
 p.end()
