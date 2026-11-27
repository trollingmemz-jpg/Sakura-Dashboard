"""Sakura Lighting: standalone user-space RGB controller."""
import sys, os, json, math, time, colorsys, stat, shutil, threading, fcntl, socket
from pathlib import Path
HOME=Path.home()
ROOT=HOME/'.local/share/sakura-lighting'
CONFIG=HOME/'.config/sakura-lighting'
SYNC=HOME/'.config/sakura-game-sync/dashboard-rgb.json'
CHROMA=SYNC.with_name('dashboard-chroma.json')
ENTRY=ROOT/'lighting.py'
DESKTOP=HOME/'.local/share/applications/sakura-lighting.desktop'
def install():
    ROOT.mkdir(parents=True,exist_ok=True)
    if Path(__file__).resolve()!=ENTRY.resolve():
        tmp=ENTRY.with_suffix('.tmp'); shutil.copyfile(__file__,tmp); tmp.replace(ENTRY)
    DESKTOP.parent.mkdir(parents=True,exist_ok=True)
    def quote(s): return '"'+str(s).replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('`','\\`').replace('%','%%')+'"'
    DESKTOP.write_text('[Desktop Entry]\nType=Application\nName=Sakura Lighting\nExec='+quote(sys.executable)+' '+quote(ENTRY)+'\nIcon=preferences-desktop-color\nCategories=Settings;Utility;\nTerminal=false\n')
def uninstall():
    DESKTOP.unlink(missing_ok=True)
    ENTRY.unlink(missing_ok=True)
def read(path,default):
    try: return json.loads(path.read_text())
    except (OSError,ValueError): return default
def released(): return read(SYNC,{}).get('mode')=='off'
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,indent=2)); tmp.replace(path)
def chroma_data(now=None,data=None):
    if data is None:data=read(CHROMA,{})
    try:
        if not data.get('enabled') or abs((time.time() if now is None else now)-float(data['heartbeat']))>3:return None
        color=data['color']
        if not isinstance(color,str) or len(color)!=7 or color[0]!='#':return None
        rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
        # Keep the artwork hue, but remove the pastel washout on physical LEDs.
        h,s,v=colorsys.rgb_to_hsv(*(c/255 for c in rgb))
        if s>0.025:rgb=tuple(round(c*255) for c in colorsys.hsv_to_rgb(h,min(1.,max(.90,s*1.45)),v))
        bars=data.get('bars',[])
        if not isinstance(bars,list) or len(bars)!=80:return None
        bars=[max(0.,min(1.,float(x))) for x in bars]
        palette=[]
        for c in data.get('palette',[])[:4]:
            if isinstance(c,str) and len(c)==7 and c.startswith('#'):palette.append(tuple(int(c[i:i+2],16) for i in (1,3,5)))
        return rgb,bars,dict(effect=data.get('effect','Spectrum'),palette=palette,adaptive=bool(data.get('adaptive',True)),rate=60 if data.get('rate')==60 else 30,visor=bool(data.get('visor',True)),direction=-1 if data.get('visor_direction')==-1 else 1,command_at=float(data.get('visor_command_at',0)),heartbeat=float(data['heartbeat']))
    except (AttributeError,KeyError,TypeError,ValueError,OverflowError):return None
def reactive_frame(base,bars,key,count,brightness,effect='Spectrum',palette=(),beat_age=10.,now=0.):
    def level(lo,hi):
        values=bars[lo:hi]
        return sum(values)/len(values) if values else 0.
    def rgb(v,color=base):return tuple(round(c*brightness/100*(.08+.92*max(0.,min(1.,v)))) for c in color)
    if effect=='Ambient flow':
        energy=level(0,65);return [rgb(.2+.55*energy+.25*(1+math.sin(now*2-i*math.tau/max(1,count)))/2) for i in range(count)]
    if effect=='Bass shockwave':
        return [rgb(max(level(0,12)*.35,max(0.,1-abs(i/max(1,count-1)-beat_age*2.5)*5)*max(0.,1-beat_age))) for i in range(count)]
    if effect=='Album palette' and palette:
        return [rgb(level(i*80//count,max(i*80//count+1,(i+1)*80//count)),palette[min(len(palette)-1,i*len(palette)//count)]) for i in range(count)]
    if key=='mouse':return [rgb(level(0,12))]
    if key in ('ram1','ram2'):
        energy=level(0,20) if key=='ram1' else level(20,65)
        return [rgb(max(0.,min(1.,energy*count-i))) for i in range(count)]
    return [rgb(level(i*80//count,max(i*80//count+1,(i+1)*80//count))) for i in range(count)]
def visor_frame(old,new,progress,brightness,direction=1):
    """Sweep a narrow illuminated leading edge across the LED order."""
    if progress>=1 or len(old)!=len(new):return new
    t=max(0.,progress);u=(1-math.cos(math.pi*t))/2
    if len(new)==1:
        return [tuple(round(a+(b-a)*u) for a,b in zip(old[0],new[0]))]
    front=-.18+1.36*u
    result=[]
    for i,(a,b) in enumerate(zip(old,new)):
        x=i/(len(new)-1)
        if direction<0:x=1-x
        mix=max(0.,min(1.,(front-x)/.10+.5))
        edge=max(0.,1-abs(x-front)/.12)*math.sin(math.pi*t)*.48
        base=[v+(w-v)*mix for v,w in zip(a,b)]
        ceiling=max(max(a),max(b),min(255,brightness*2.55))
        result.append(tuple(max(0,min(255,round(v+(ceiling-v)*edge))) for v in base))
    return result
def frame(rgb,mode,brightness,t,index=0):
    if mode=='Rainbow': rgb=tuple(round(x*255) for x in colorsys.hsv_to_rgb((t/8+index*.12)%1,1,1))
    scale=brightness/100
    if mode=='Breathing': scale*=.15+.85*(1+math.sin(t*math.tau/3))/2
    if mode=='Blackout': scale=0
    return tuple(round(x*scale) for x in rgb)
def mouse_write(rgb):
    for p in Path('/dev/input').glob('ckb*/model'):
        if 'harpoon' not in p.read_text().lower(): continue
        path=p.parent/'cmd'
        if not stat.S_ISFIFO(path.stat().st_mode): raise RuntimeError('Not a ckb command FIFO')
        fd=os.open(path,os.O_WRONLY|os.O_NONBLOCK)
        try: os.write(fd,('rgb %02x%02x%02x\n'%rgb).encode())
        finally: os.close(fd)
        return
    raise RuntimeError('Harpoon not found')
def main():
    from PySide6.QtCore import Qt,QTimer
    from PySide6.QtDBus import QDBusConnection,QDBusInterface
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QSlider,QColorDialog,QCheckBox,QMessageBox
    headless='--visualiser' in sys.argv
    app=QApplication(sys.argv); CONFIG.mkdir(parents=True,exist_ok=True)
    lock=open(CONFIG/'instance.lock','a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        if headless:print('Sakura Lighting is already running; visualiser will retry.',file=sys.stderr)
        return
    receiver=None;socket_path=CONFIG/'chroma.sock'
    if headless:
        try:
            socket_path.unlink(missing_ok=True);receiver=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);receiver.bind(str(socket_path));socket_path.chmod(0o600);receiver.setblocking(False)
        except OSError:
            if receiver:receiver.close()
            receiver=None
    win=QWidget(); win.setWindowTitle('Sakura Lighting'); win.resize(720,540)
    win.setStyleSheet('QWidget{background:#19141f;color:#f4e5f1;font-size:14px} QPushButton,QComboBox{background:#38283f;border:1px solid #59415c;border-radius:8px;padding:10px} QPushButton:hover{background:#56334e} QPushButton:disabled{color:#817683} QSlider::groove:horizontal{height:6px;background:#514052;border-radius:3px} QSlider::handle:horizontal{background:#f478d7;width:16px;margin:-5px 0;border-radius:8px}')
    layout=QVBoxLayout(win);layout.setContentsMargins(28,24,28,24);layout.setSpacing(14)
    title=QLabel('SAKURA  /  LIGHTING');title.setStyleSheet('font-size:26px;font-weight:700;color:#f478d7');layout.addWidget(title)
    layout.addWidget(QLabel('Keyboard • Memory • Mouse'))
    hint=QLabel('Set Dashboard → Settings → Lighting to Off (release control) before starting.');hint.setWordWrap(True);layout.addWidget(hint)
    cfg=read(CONFIG/'profile.json',{}); rows={}
    for key,label in [('keyboard','K55 CORE keyboard'),('ram1','Vengeance RGB Pro — DIMM 1'),('ram2','Vengeance RGB Pro — DIMM 2'),('mouse','Harpoon mouse')]:
        row=QHBoxLayout(); check=QCheckBox(label);check.setChecked(cfg.get(key,{}).get('enabled',True));row.addWidget(check,1)
        color=QPushButton(); c=QColor(cfg.get(key,{}).get('color','#f478d7'))
        def paint(b,c): b.setText(c.name());b.setStyleSheet('background:'+c.name()+';color:'+('#17111c' if c.lightness()>130 else 'white')+';padding:10px;border-radius:8px')
        paint(color,c)
        def choose(_,b=color):
            c=QColorDialog.getColor(QColor(b.text()),win)
            if c.isValid(): paint(b,c)
        color.clicked.connect(choose);row.addWidget(color);layout.addLayout(row);rows[key]=(check,color)
    sync=QPushButton('Match all colours to keyboard');sync.clicked.connect(lambda:[paint(b,QColor(rows['keyboard'][1].text())) for _,b in rows.values()]);layout.addWidget(sync)
    mode=QComboBox();mode.addItems(['Static','Breathing','Rainbow','Blackout']);mode.setCurrentText(cfg.get('mode','Static'));layout.addWidget(mode)
    level=QLabel();brightness=QSlider(Qt.Orientation.Horizontal);brightness.setRange(0,100);brightness.setValue(cfg.get('brightness',100));brightness.valueChanged.connect(lambda v:level.setText('Brightness  '+str(v)+'%'));level.setText('Brightness  '+str(brightness.value())+'%');layout.addWidget(level);layout.addWidget(brightness)
    dim=QCheckBox('Dim existing lighting when PC locks');dim.setChecked(cfg.get('dim_on_lock',True));layout.addWidget(dim)
    dimlevel=QSlider(Qt.Orientation.Horizontal);dimlevel.setRange(0,100);dimlevel.setValue(cfg.get('locked_brightness',15))
    dimlabel=QLabel('Locked brightness multiplier: '+str(dimlevel.value())+'%');dimlevel.valueChanged.connect(lambda v:dimlabel.setText('Locked brightness multiplier: '+str(v)+'%'));layout.addWidget(dimlabel);layout.addWidget(dimlevel)
    visor=QCheckBox('Visor sweep on colour changes');visor.setChecked(cfg.get('visor',True));layout.addWidget(visor)
    status=QLabel('Idle — no hardware writes');status.setWordWrap(True);layout.addWidget(status)
    buttons=QHBoxLayout();start=QPushButton('Start lighting');stop=QPushButton('Release control');stop.setEnabled(False);buttons.addWidget(start);buttons.addWidget(stop);layout.addLayout(buttons)
    state={'active':False,'profile':{},'status':'Idle — no hardware writes'};halt=threading.Event()
    screen=QDBusInterface('org.freedesktop.ScreenSaver','/ScreenSaver','org.freedesktop.ScreenSaver',QDBusConnection.sessionBus())
    screen.setTimeout(250)
    state['locked']=False
    def check_lock():
        reply=screen.call('GetActive')
        if reply.arguments() and isinstance(reply.arguments()[0],bool):state['locked']=reply.arguments()[0]
    locktimer=QTimer(win);locktimer.timeout.connect(check_lock);locktimer.start(750);check_lock()
    remote=CONFIG/'mobile-command.json'
    mobile_status=CONFIG/'mobile-status.json'
    offsets={k:cfg.get(k,{}).get('brightness',100) for k in rows}
    def snapshot():
        p={k:{'enabled':a.isChecked(),'color':b.text(),'brightness':offsets[k]} for k,(a,b) in rows.items()};p.update(mode=mode.currentText(),brightness=brightness.value(),dim_on_lock=dim.isChecked(),locked_brightness=dimlevel.value(),visor=visor.isChecked());state['profile']=p
        return p
    def begin():
        if not released(): QMessageBox.warning(win,'Release Game Sync','Set Dashboard lighting mode to Off and save first.');return
        try: import openrgb
        except ImportError: QMessageBox.warning(win,'Missing dependency','Install openrgb-python in the Python environment used to launch Sakura Lighting.');return
        save(CONFIG/'profile.json',snapshot());state['active']=True;start.setEnabled(False);stop.setEnabled(True)
    def end():
        state['active']=False;start.setEnabled(True);stop.setEnabled(False)
    start.clicked.connect(begin);stop.clicked.connect(end)
    def tick():
        if remote.exists():
            claimed=remote.with_suffix('.processing')
            try:
                remote.replace(claimed)
                cmd=read(claimed,{})
                keys=['ram1','ram2'] if cmd.get('device')=='ram' else [cmd.get('device')]
                if state['active'] and released():
                    for k in keys:
                        if k in rows:
                            paint(rows[k][1],QColor(cmd['color']))
                            offsets[k]=max(0,min(100,int(cmd['brightness'])))
            except (OSError,KeyError,TypeError,ValueError):pass
            finally:claimed.unlink(missing_ok=True)
        p=snapshot();status.setText(state['status'])
        if headless:
            if chroma_data() is None:app.quit();return
            state['active']=released()
            if time.monotonic()-state.get('visualiser_published',0)>=.5:
                save(CONFIG/'visualiser-status.json',dict(status=state['status'],heartbeat=time.time()));state['visualiser_published']=time.monotonic()
        if state['active'] and released():
            payload=dict(p,heartbeat=time.time())
            if time.monotonic()-state.get('published',0)>=1:
                save(mobile_status,payload);state['published']=time.monotonic()
        else:mobile_status.unlink(missing_ok=True)
        if not state['active'] and not start.isEnabled(): end()
    timer=QTimer(win);timer.timeout.connect(tick);timer.start(150)
    def worker():
        client=None; devices={}; last={};retry=0
        def disconnect():
            nonlocal client,devices
            if client:
                try: client.disconnect()
                except Exception: pass
            client=None;devices={};last.clear()
        multiplier=1.0; blended={};deadline=time.monotonic();fps=0.;previous_frame=0.;packet=None;rate=30;last_write={};bass_avg=0.;beat_at=-100.;gain_peak=.5; transitions={}; targets={}; consumed_commands={}
        while not halt.wait(max(0.,deadline-time.monotonic())):
            now=time.monotonic();deadline=now+(1/rate if headless else 1/30 if transitions else .12)
            if not state['active'] or not released():
                if state['active']:state['active']=False;state['status']='Released: Game Sync lighting is not off.'
                if client or last:disconnect()
                blended.clear();transitions.clear();targets.clear();consumed_commands.clear()
                continue
            p=state['profile'];errors=[]
            if previous_frame:fps=.85*fps+.15/max(.001,now-previous_frame) if fps else 1/max(.001,now-previous_frame)
            previous_frame=now
            target=p.get('locked_brightness',15)/100 if state['locked'] and p.get('dim_on_lock',True) else 1.0
            step=.035 if headless else .12
            multiplier += max(-step,min(step,target-multiplier))
            if client is None and now>=retry:
                retry=now+5
                try:
                    from openrgb import OpenRGBClient
                    client=OpenRGBClient('127.0.0.1',6743)
                    ks=[d for d in client.devices if int(d.type)==5 and 'k55' in d.name.lower()]
                    rs=sorted([d for d in client.devices if int(d.type)==1],key=lambda d:str(getattr(d,'serial','')))
                    if ks:devices['keyboard']=ks[0]
                    for i,d in enumerate(rs[:2]):devices['ram'+str(i+1)]=d
                except Exception as e:disconnect();errors.append(str(e))
            if receiver:
                for _ in range(16):
                    try:packet=json.loads(receiver.recv(16384))
                    except (BlockingIOError,OSError):break
                    except ValueError:continue
            chroma=chroma_data(data=packet) if packet is not None else None
            if chroma is None:chroma=chroma_data()
            effect_name='Spectrum';palette=[];bars=[];latency=0.
            if chroma:
                bars=chroma[1];meta=chroma[2];rate=meta['rate'];effect_name=meta['effect'];palette=meta['palette'];latency=max(0.,(time.time()-meta['heartbeat'])*1000)
                bass=sum(bars[:12])/12;energy=max(bars);gain_peak=max(.25,energy,gain_peak*.998)
                if bass>max(.16,bass_avg+.075) and now-beat_at>.18:beat_at=now
                bass_avg+=.04*(bass-bass_avg)
                if meta['adaptive']:bars=[min(1.,v/max(.45,gain_peak)) for v in bars]
                if effect_name=='Automatic':effect_name='Bass shockwave' if bass_avg>.42 else 'Ambient flow' if energy<.38 else 'Spectrum'
            for k in rows:
                if headless and k.startswith('ram') and now-last_write.get(k,-100)<1/30:continue
                if not p.get(k,{}).get('enabled'):continue
                h=p[k]['color'];manual=tuple(int(h[i:i+2],16) for i in (1,3,5));target_color=chroma[0] if chroma is not None else manual
                use_visor=(meta.get('visor',True) if chroma is not None else p.get('visor',True)) and p['mode'] not in ('Blackout','Rainbow')
                old_target=targets.get(k);targets[k]=target_color
                if use_visor and old_target is not None and old_target!=target_color and k in last:
                    direction=1
                    if chroma is not None and 0<=time.time()-meta['command_at']<10 and consumed_commands.get(k)!=meta['command_at']:
                        direction=meta['direction'];consumed_commands[k]=meta['command_at']
                    transitions[k]=(now,last[k],direction)
                elif not use_visor:transitions.pop(k,None)
                previous=blended.get(k,manual);base=target_color if use_visor else tuple(a+(b-a)*.35 for a,b in zip(previous,target_color));blended[k]=base
                effect='Static' if chroma is not None and p['mode']=='Rainbow' else p['mode']
                power=p['brightness']*multiplier*p[k].get('brightness',100)/100
                if chroma is not None:
                    count=1 if k=='mouse' else len(devices[k].leds) if k in devices else 0
                    if not count:continue
                    values=reactive_frame(base,bars,k,count,power,effect_name,palette,now-beat_at,now) if p['mode']!='Blackout' else [(0,0,0)]*count
                else:
                    rgb=frame(base,effect,power,now);values=[rgb]*(1 if k=='mouse' else len(devices[k].leds) if k in devices else 0)
                if not values:continue
                if k in transitions:
                    started,old_values,direction=transitions[k];progress=(now-started)/.6
                    if progress>=1 or len(old_values)!=len(values):transitions.pop(k,None)
                    else:values=visor_frame(old_values,values,progress,power,direction)
                signature=tuple(values)
                if last.get(k)==signature:continue
                try:
                    if k=='mouse':mouse_write(values[0])
                    elif k in devices:
                        from openrgb.utils import RGBColor
                        d=devices[k];d.set_colors([RGBColor(*rgb) for rgb in values],fast=True)
                    else:continue
                    last[k]=signature;last_write[k]=now
                except Exception as e:
                    errors.append(k+': '+str(e))
                    if k!='mouse':disconnect();transitions.clear();targets.clear();retry=now+5
            state['status']=(f'Chroma Sync active | {fps:.0f} FPS worker | {latency:.0f} ms packet age | {effect_name} | ' if chroma is not None else '')+'Detected: '+(', '.join(devices) or 'no SDK devices')+' | Mouse: '+('active' if 'mouse' in last else 'not active')+(' | '+'; '.join(errors) if errors else '')
        disconnect()
    thread=threading.Thread(target=worker,daemon=True);thread.start()
    def close():
        halt.set();state['active']=False;mobile_status.unlink(missing_ok=True)
        if headless:
            (CONFIG/'visualiser-status.json').unlink(missing_ok=True)
            if receiver:receiver.close();socket_path.unlink(missing_ok=True)
        else:save(CONFIG/'profile.json',snapshot())
    app.aboutToQuit.connect(close)
    if headless:snapshot();state['active']=released();app.setQuitOnLastWindowClosed(False)
    else:win.show()
    app.exec();thread.join(.5)
if __name__=='__main__':
    if '--install' in sys.argv:install()
    elif '--uninstall' in sys.argv:uninstall()
    else:main()
