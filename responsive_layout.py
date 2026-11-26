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
  r=QRectF(x,y,ww,hh);p.setPen(QPen(accent,1));p.setBrush(QColor('#211329'));p.drawRoundedRect(r,8,8);text(x+4,y,ww-8,hh,label,min(18,hh*.45),accent,Qt.AlignHCenter);o.hit_regions[action]=r
 def stats(x,y,ww,hh):
  for i,(label,val) in enumerate([('CPU',f'{o.stats[0]:.0f}%'),('GPU',o.stats[3]),('Memory',f'{o.stats[1]:.0f}%')]):
   yy=y+i*hh/3;text(x,yy,ww*.48,hh/3,label,min(20,hh/8),'#c393cc');text(x+ww*.48,yy,ww*.52,hh/3,val,min(29,hh/6),align=Qt.AlignRight)
 item=o.player.get('item') or {};local=getattr(getattr(o,'media',None),'state',{})
 title=o.track[0] if local else item.get('name') or o.track[0];artist=o.track[1] if local else ', '.join(a.get('name','') for a in item.get('artists',[])) or o.track[1]
 text(pad,pad,w*.5-pad,40,'桜 / SAKURA',min(25,w*.055),accent);text(w*.5,pad,w*.5-pad,40,time.strftime('%H:%M'),min(38,w*.075),align=Qt.AlignRight)
 top=pad+56;bottom=h-pad-48;space=max(100,bottom-top)
 if portrait:
  aw=min(w-2*pad,space*.34,360);ax=(w-aw)/2;ay=top
  tx=pad;ty=ay+aw+8;tw=w-2*pad
  sy=ty+110;sh=max(45,(bottom-sy)*.58);sx=pad;sw=tw
  vy=sy+sh+4;vh=max(0,bottom-vy-38);vx=pad;vw=tw
 else:
  aw=min(space*.48,w*.20);ax=pad;ay=top
  tx=ax+aw+pad;ty=top;tw=max(50,w*.59-tx)
  sx=w*.64;sy=top;sw=w-pad-sx;sh=space*.70
  vx=pad;vy=top+max(aw,110)+16;vw=w*.59-pad;vh=max(0,bottom-vy-38)
 art=o.art
 if not art.isNull():
  scaled=art.scaled(int(aw),int(aw),Qt.KeepAspectRatio,Qt.SmoothTransformation);p.drawImage(QPointF(ax+(aw-scaled.width())/2,ay+(aw-scaled.height())/2),scaled)
 else:p.fillRect(QRectF(ax,ay,aw,aw),QColor('#39253e'))
 text(tx,ty,tw,22,'NOW PLAYING',13,accent);text(tx,ty+24,tw,32,title,min(28,tw*.085));text(tx,ty+56,tw,22,artist,min(17,tw*.06),'#c393cc')
 bw=min(70,(tw-12)/3)
 for i,(label,action) in enumerate([('‹','previous'),('Ⅱ' if o.playing() else '▶','toggle'),('›','next')]):button(tx+i*(bw+6),ty+82,bw,30,label,action)
 lyrics=getattr(o,'lyrics_window',None)
 if lyrics:
  if portrait:
   paint_lyrics(p,lyrics,QRectF(sx,sy,sw,sh),accent)
  else:
   lyric_h=space*.52
   paint_lyrics(p,lyrics,QRectF(sx,sy,sw,lyric_h),accent)
   stats(sx,sy+lyric_h+pad*.4,sw,max(45,min(space*.23,bottom-sy-lyric_h-pad*.4-30)))
 else:stats(sx,sy,sw,sh)
 if vh>8:
  for i,b in enumerate(o.bars):
   bh=max(2,min(1,b)*vh);p.setPen(Qt.NoPen);p.setBrush(accent);p.drawRoundedRect(QRectF(vx+i*vw/80,vy+vh-bh,max(1,vw/80*.65),bh),2,2)
 game=o.sync_status.get('detected_game','Desktop');voice=o.discord.state.get('channel','')
 text(pad,bottom-30,w-2*pad,24,('Game: '+game)+('  •  Voice: '+voice if voice else ''),14,accent)
 bw=min(145,(w-2*pad-18)/4)
 for i,(label,action) in enumerate([('Music','connections'),('Media','media'),('Discord','discord'),('桜 Settings','settings')]):button(pad+i*(bw+6),h-pad-36,bw,36,label,action)
 p.end()
