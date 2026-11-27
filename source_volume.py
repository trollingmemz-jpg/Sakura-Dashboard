"""Source-scoped volume controls. Never change the master output."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QLabel,QSlider,QPushButton
def add_volume(owner,layout):
    label=QLabel('Detecting active source…');label.setWordWrap(True);layout.addRow('Current source',label)
    slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(0,100);slider.setEnabled(False);layout.addRow('Source volume',slider)
    mute=QPushButton('Mute');mute.setEnabled(False);layout.addRow(mute)
    target=[None];drag=[None];restore={};last=[None]
    def refresh():
        if slider.isSliderDown():return
        try:
            info=source(owner)
            target[0]=info[0] if info else None
            if not info:
                label.setText('No uniquely matched audio source');slider.setEnabled(False);mute.setEnabled(False);return
            key,name,value,muted=info
            label.setText(name+' • '+str(value)+'%'+(' • muted' if muted else ''))
            slider.setValue(value);slider.setEnabled(True);mute.setEnabled(True);mute.setText('Unmute' if muted or value==0 else 'Mute');last[0]=info
        except Exception:
            target[0]=None;slider.setEnabled(False);mute.setEnabled(False);label.setText('Source volume unavailable')
    def change():
        key=drag[0] or target[0];drag[0]=None
        try:
            current=source(owner)
            if current and current[0]==key:apply(owner,current,slider.value(),False)
        except Exception:label.setText('Unable to change source volume')
        QTimer.singleShot(350,refresh)
    def toggle():
        try:
            current=source(owner)
            if not current or current[0]!=target[0]:return
            key,name,value,muted=current
            if muted or value==0:apply(owner,current,restore.get(key,50) if value==0 else value,False)
            else:restore[key]=value;apply(owner,current,value,True)
        except Exception:label.setText('Unable to change source mute')
        QTimer.singleShot(350,refresh)
    slider.sliderPressed.connect(lambda:drag.__setitem__(0,target[0]))
    slider.sliderReleased.connect(change);mute.clicked.connect(toggle)
    timer=QTimer(label);timer.timeout.connect(refresh);timer.start(1000);refresh()

def remote(owner):
    p=owner.player;d=p.get('device') or {};value=d.get('volume_percent')
    if d.get('id') and isinstance(value,int) and d.get('supports_volume',True):
        return (('remote',d['id']),d.get('name','Spotify Connect'),value,value==0)

def remote_apply(owner,info,value,muted):
    owner.connect.submit('volume',value=0 if muted else value,device=info[0][1])
import os,re
def sessions(app):
    from pycaw.pycaw import AudioUtilities
    raw=app.casefold()
    known={'spotify':'spotify','firefox':'firefox','chrome':'chrome','msedge':'msedge','brave':'brave','opera':'opera','vlc':'vlc','itunes':'itunes','applemusic':'applemusic'}
    exact=os.path.basename(raw.replace('\\','/')).removesuffix('.exe')
    matches=[v for k,v in known.items() if re.search(r'(?<![a-z0-9])'+re.escape(k)+r'(?![a-z0-9])',raw)]
    names=set(matches) or ({exact} if exact and re.fullmatch(r'[a-z0-9_-]+',exact) else set())
    if len(names)!=1:return []
    name=next(iter(names))
    out=[]
    for session in AudioUtilities.GetAllSessions():
        try:
            if session.Process and session.Process.name().casefold().removesuffix('.exe')==name:out.append(session)
        except Exception:pass
    return out
def source(owner):
    local=owner.selected_local_media()
    if not local:return remote(owner)
    app=local.get('app','')
    ss=sessions(app)
    if not ss:return None
    volumes=[s.SimpleAudioVolume for s in ss]
    return (('local',app),app,round(max(v.GetMasterVolume() for v in volumes)*100),all(v.GetMute() for v in volumes))
def apply(owner,info,value,muted):
    if info[0][0]=='remote':return remote_apply(owner,info,value,muted)
    for s in sessions(info[0][1]):
        v=s.SimpleAudioVolume
        v.SetMasterVolume(value/100,None);v.SetMute(int(muted),None)
