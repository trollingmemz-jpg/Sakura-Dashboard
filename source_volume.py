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
import subprocess,json
def pulse(*args):
    return subprocess.check_output(['pactl',*args],text=True,stderr=subprocess.DEVNULL,timeout=1)
def streams():
    rows=json.loads(pulse('-f','json','list','sink-inputs'))
    return [r for r in rows if any(str(r.get('properties',{}).get(k,'')).lower()==v for k,v in [('application.process.binary','spotify'),('application.name','spotify'),('application.id','com.spotify.client')])]
def source(owner):
    if owner.track[0]=='Nothing playing' or not (owner.local_playing is True or owner.spotify_target or not owner.player.get('item')):
        return remote(owner)
    ss=streams()
    if not ss:return None
    values=[c.get('value_percent','0%') for r in ss for c in r.get('volume',{}).values()]
    return (('local','spotify'),'Spotify (local application)',min(100,round(max(float(v.rstrip('%')) for v in values))) if values else 0,all(r.get('mute',False) for r in ss))
def apply(owner,info,value,muted):
    if info[0][0]=='remote':return remote_apply(owner,info,value,muted)
    for r in streams():
        idx=str(r['index']);pulse('set-sink-input-volume',idx,str(value)+'%');pulse('set-sink-input-mute',idx,'1' if muted else '0')
