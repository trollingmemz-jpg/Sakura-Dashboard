"""Opt-in Windows LAN companion, compatible with Sakura Mobile v1 QR protocol."""
import datetime, hashlib, hmac, http.server, io, ipaddress, json, os, re, secrets, socket, ssl, threading, time, ctypes
from pathlib import Path
import psutil, qrcode
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QVBoxLayout, QLabel, QPushButton, QPlainTextEdit
from inline_panel import InlinePanel

PORT=8743
ROOT=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Sakura'/'mobile'
SYNC=ROOT.parent/'state'/'dashboard-rgb.json'
LIGHT=ROOT.parent/'lighting'
def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}

def atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.bridge-tmp')
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)

def lighting():
    p = read(LIGHT / 'mobile-status.json')
    if time.time() - p.get('heartbeat', 0) > 4 or read(SYNC).get('mode') != 'off':
        return {}
    return p

def dashboard_lighting():
    p=read(SYNC)
    if p.get('mode') not in ('manual','auto'):
        return {}
    live=read(SYNC.parent/'dashboard-status.json')
    if abs(time.time()-live.get('time',0))>5:
        return {}
    return p

def dashboard_devices(p):
    out={}
    overrides=p.get('mobile_overrides',{})
    live=read(SYNC.parent/'dashboard-status.json')
    key='manual' if p.get('mode')=='manual' else 'combat' if live.get('combat') else 'scanning' if live.get('scanning') else 'idle'
    defaults={'manual':[244,120,215],'combat':[240,24,134],'scanning':[179,108,255],'idle':[244,120,215]}
    color=p.get(key,defaults[key])
    if p.get('mode')=='auto' and key!='combat':
        game=read(SYNC.parent/'game-profiles.json').get(live.get('detected_game','Desktop'),{})
        if game.get('enabled') and game.get('rgb_enabled') and re.fullmatch(r'#[0-9a-fA-F]{6}',str(game.get('rgb',''))):
            color=[int(game['rgb'][i:i+2],16) for i in (1,3,5)]
    for device in ('keyboard','ram','mouse'):
        if not p.get(device,True):continue
        override=overrides.get(device,{})
        rgb=override.get('color',color)
        out[device]={'color':'#%02x%02x%02x'%tuple(rgb),'brightness':override.get('brightness',p.get('brightness',100))}
    return out


def network():
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.connect(('192.0.2.1',9))
        host=s.getsockname()[0]
    if not any(ipaddress.IPv4Address(host) in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise RuntimeError('Connect to a private Wi-Fi or Ethernet network first.')
    for addresses in psutil.net_if_addrs().values():
        if any(a.family==socket.AF_INET and a.address==host for a in addresses):
            for a in addresses:
                mac=a.address.replace('-',':')
                if a.family==psutil.AF_LINK and re.fullmatch(r'(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}',mac):
                    return host,mac
    raise RuntimeError('No LAN adapter MAC address found.')

def credentials():
    ROOT.mkdir(parents=True,exist_ok=True)
    cert,key,tokenfile=(ROOT/x for x in ('cert.pem','key.pem','token'))
    if not cert.exists() or not key.exists():
        private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Sakura-Mobile')])
        now=datetime.datetime.now(datetime.timezone.utc)
        signed=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=3650)).sign(private,hashes.SHA256())
        key.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        cert.write_bytes(signed.public_bytes(serialization.Encoding.PEM))
    if not tokenfile.exists():tokenfile.write_text(secrets.token_urlsafe(48))
    return cert,key,tokenfile.read_text().strip()

class Handler(http.server.BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(4)
    def log_message(self,*args):pass
    def reply(self,code,data=None):
        payload=json.dumps(data).encode() if data is not None else b''
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers()
        if payload:self.wfile.write(payload)
    def authorized(self):
        return hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+self.server.token).encode())
    def do_GET(self):
        if not self.authorized():return self.reply(401)
        if self.path!='/v1/status':return self.reply(404)
        try:
            self.reply(200,self.server.companion.status());(ROOT/'paired').touch()
        except Exception:return
    def do_POST(self):
        if not self.authorized():return self.reply(401)
        if self.path!='/v1/command':return self.reply(404)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=4096:return self.reply(400)
            data=json.loads(self.rfile.read(n))
            if not isinstance(data,dict):raise ValueError()
            self.server.companion.command(data);self.reply(204)
        except (ValueError,TypeError):self.reply(400)
        except Exception:self.reply(503)

class MobileCompanion:
    def __init__(self,owner):
        self.owner=owner;self.server=None;self.payload='';self.message='Mobile pairing disabled'
        QApplication.instance().aboutToQuit.connect(self.stop)
        if (ROOT/'enabled').exists():QTimer.singleShot(0,self.restore)
    def restore(self):
        try:self.start()
        except Exception as e:self.message=str(e)
    def start(self):
        if self.server:return
        host,mac=network();cert,key,token=credentials()
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain(cert,key)
        server=http.server.HTTPServer((host,PORT),Handler)
        try:
            server.socket=ctx.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
            server.token=token;server.companion=self
            fingerprint=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
            self.payload=json.dumps(dict(version=1,host=host,port=PORT,fingerprint=fingerprint,token=token,mac=mac))
            self.server=server
            threading.Thread(target=server.serve_forever,daemon=True).start()
            (ROOT/'enabled').touch();self.message='Ready: '+host+':'+str(PORT)
        except Exception:
            server.server_close();self.server=None;raise
    def stop(self):
        if self.server:
            server=self.server;self.server=None
            threading.Thread(target=lambda:(server.shutdown(),server.server_close()),daemon=True).start()
        self.payload=''
    def disable(self):
        (ROOT/'enabled').unlink(missing_ok=True);self.stop();self.message='Mobile pairing disabled'
    def revoke(self):
        self.disable()
        for name in ('token','paired'):(ROOT/name).unlink(missing_ok=True)
        self.message='Pairing revoked. Enable again for a new code.'
    def status(self):
        local=self.owner.media.state.copy()
        stats={'cpu':round(psutil.cpu_percent()),'memory':round(psutil.virtual_memory().percent)}
        p=dashboard_lighting()
        return dict(name=socket.gethostname(),stats=stats,media={k:local[k] for k in ('title','artist') if k in local},lighting=dashboard_devices(p) if p else {})
    def command(self,data):
        action=data.get('action')
        if action in ('previous','next','play_pause'):
            if not self.owner.media.state:raise RuntimeError('No media session')
            self.owner.media.submit(('pause' if self.owner.media.state.get('playing') else 'play') if action=='play_pause' else action)
        elif action=='lock':
            if not ctypes.windll.user32.LockWorkStation():raise RuntimeError('Lock failed')
        elif action=='lighting':
            device=data.get('device');color=data.get('color');level=data.get('brightness')
            if device not in ('keyboard','ram','mouse') or not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color) or type(level) is not int or not 0<=level<=100:raise ValueError()
            profile=dashboard_lighting()
            if not profile or device not in dashboard_devices(profile):raise RuntimeError('Lighting unavailable')
            profile.setdefault('mobile_overrides',{})[device]={'color':[int(color[i:i+2],16) for i in (1,3,5)],'brightness':level}
            if read(SYNC).get('mode')!=profile['mode']:raise RuntimeError('Lighting ownership changed')
            atomic(SYNC,profile)
        elif action in ('sleep','volume'):raise RuntimeError('Not supported on Windows yet')
        else:raise ValueError('Unknown action')
    def show_pairing(self):
        dlg=InlinePanel(self.owner);dlg.setWindowTitle('Sakura Mobile • Pair phone');layout=QVBoxLayout(dlg)
        hint=QLabel('Connect your phone to the same private network. Enabling pairing grants remote PC control. Keep the QR private. Allow Sakura through Windows Firewall on private networks only if prompted.');hint.setWordWrap(True);layout.addWidget(hint)
        status=QLabel();status.setWordWrap(True);layout.addWidget(status)
        qr=QLabel();qr.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(qr)
        manual=QPlainTextEdit();manual.setReadOnly(True);manual.setMaximumHeight(100);manual.hide();layout.addWidget(manual)
        def refresh():
            status.setText(('Paired • ' if self.server and (ROOT/'paired').exists() else '')+self.message)
        def render():
            qr.clear();manual.clear();manual.hide()
            if self.payload:
                stream=io.BytesIO();qrcode.make(self.payload).save(stream,format='PNG')
                pix=QPixmap();pix.loadFromData(stream.getvalue());qr.setPixmap(pix.scaled(300,300,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation))
            refresh()
        def enable():
            try:self.start()
            except Exception as e:self.message=str(e)
            render()
        def disable():self.disable();render()
        def revoke():self.revoke();render()
        def reveal():
            if self.payload:manual.setPlainText(self.payload);manual.show()
        for label,fn in [('Enable pairing / show QR',enable),('Show manual pairing code',reveal),('Disable mobile control',disable),('Revoke pairing token',revoke)]:
            button=QPushButton(label);button.clicked.connect(fn);layout.addWidget(button)
        timer=QTimer(dlg);timer.timeout.connect(refresh);timer.start(500);render();dlg.exec();timer.stop()
