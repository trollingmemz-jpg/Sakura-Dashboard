"""Sakura Mobile v1 LAN bridge. Run as the logged-in desktop user."""
import argparse
import hashlib
import hmac
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import time

ROOT = Path.home() / '.config/sakura-mobile'
LIGHT = Path.home() / '.config/sakura-lighting'
SYNC = Path.home() / '.config/sakura-game-sync/dashboard-rgb.json'

def run(*args):
    return subprocess.check_output(args, text=True, timeout=2).strip()

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

def optional(*args):
    try:
        return run(*args)
    except (OSError, subprocess.SubprocessError):
        return ''

def status():
    out = {'name': socket.gethostname(), 'stats': {}, 'media': {}, 'lighting': {}}
    try:
        m = dict((line.split(':')[0], int(line.split()[1])) for line in Path('/proc/meminfo').read_text().splitlines())
        out['stats']['memory'] = round(100 * (1 - m['MemAvailable']/m['MemTotal']))
    except (OSError, ValueError, KeyError, IndexError):
        pass
    try:
        a = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
        time.sleep(.15)
        b = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
        delta = [y-x for x,y in zip(a,b)]
        if sum(delta)>0:
            out['stats']['cpu'] = round(100*(1-(delta[3]+delta[4])/sum(delta)))
    except (OSError, ValueError, IndexError):
        pass
    gpu = optional('nvidia-smi','--query-gpu=utilization.gpu','--format=csv,noheader,nounits').splitlines()
    if gpu and gpu[0].isdigit():
        out['stats']['gpu'] = int(gpu[0])
    for key in ('title','artist'):
        value = optional('playerctl','metadata','xesam:'+key)
        if value:
            out['media'][key] = value
    vol = optional('wpctl','get-volume','@DEFAULT_AUDIO_SINK@')
    match = re.search(r'Volume: ([0-9.]+)',vol)
    if match:
        out['media']['volume'] = 0 if 'MUTED' in vol else min(100,round(float(match[1])*100))
    p=lighting()
    for key, local in [('keyboard','keyboard'),('ram','ram1'),('mouse','mouse')]:
        d=p.get(local,{})
        if d.get('enabled'):
            out['lighting'][key]={'color':d.get('color','#000000'),'brightness':d.get('brightness',100)}
    return out

def percent(value):
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError('Invalid percentage')
    return value

def command(data):
    action=data.get('action')
    media={'previous':'previous','next':'next','play_pause':'play-pause'}
    if action in media:
        run('playerctl',media[action])
    elif action=='volume':
        run('wpctl','set-volume','@DEFAULT_AUDIO_SINK@',str(percent(data.get('percent')))+'%')
    elif action=='lock':
        run('loginctl','lock-session')
    elif action=='sleep':
        subprocess.Popen(['systemctl','suspend'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    elif action=='lighting':
        device=data.get('device')
        color=data.get('color')
        if device not in ('keyboard','ram','mouse') or not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
            raise ValueError('Invalid lighting request')
        level=percent(data.get('brightness'))
        p=lighting()
        if not p.get('ram1' if device=='ram' else device,{}).get('enabled'):
            raise RuntimeError('Lighting unavailable')
        pending=LIGHT/'mobile-command.json'
        if pending.exists():
            raise RuntimeError('Lighting busy')
        atomic(pending,{'device':device,'color':color,'brightness':level})
    else:
        raise ValueError('Unknown action')

class Handler(http.server.BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(4)
    def log_message(self,*args):
        pass
    def reply(self,code,data=None):
        payload=json.dumps(data).encode() if data is not None else b''
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        if payload:
            self.wfile.write(payload)
    def authorized(self):
        return hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+self.server.token).encode())
    def do_GET(self):
        if not self.authorized():
            return self.reply(401)
        if self.path!='/v1/status':
            return self.reply(404)
        try:
            self.reply(200,status())
        except Exception:
            self.reply(503)
    def do_POST(self):
        if not self.authorized():
            return self.reply(401)
        if self.path!='/v1/command':
            return self.reply(404)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=4096:
                return self.reply(400)
            data=json.loads(self.rfile.read(n))
            if not isinstance(data,dict):
                raise ValueError('Expected object')
            command(data)
            self.reply(204)
        except (ValueError,TypeError):
            self.reply(400)
        except (RuntimeError,OSError,subprocess.SubprocessError):
            self.reply(503)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',required=True,help='PC LAN IPv4 address (not 0.0.0.0)')
    parser.add_argument('--mac',required=True,help='Wake-on-LAN adapter MAC address')
    parser.add_argument('--port',type=int,default=8743)
    parser.add_argument('--pair',action='store_true',help='Display pairing QR locally then exit')
    args=parser.parse_args()
    import ipaddress
    host=ipaddress.IPv4Address(args.host)
    if not host.is_private or host.is_unspecified or host.is_loopback or host.is_link_local:
        parser.error('Use the PC private LAN address')
    if not re.fullmatch(r'(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}',args.mac):
        parser.error('Invalid MAC')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    ROOT.chmod(0o700)
    cert,key,tokenfile=(ROOT/x for x in ('cert.pem','key.pem','token'))
    if not cert.exists() or not key.exists():
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','3650','-subj','/CN=Sakura-Mobile','-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if not tokenfile.exists():
        tokenfile.write_text(secrets.token_urlsafe(48))
    token=tokenfile.read_text().strip()
    fingerprint=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
    pairing=json.dumps({'version':1,'host':args.host,'port':args.port,'fingerprint':fingerprint,'token':token,'mac':args.mac})
    if args.pair:
        try:
            subprocess.run(['qrencode','-t','ANSIUTF8'],input=pairing,text=True,check=True)
        except FileNotFoundError:
            print(pairing)
        return
    server=http.server.HTTPServer((args.host,args.port),Handler)
    server.token=token
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert,key)
    server.socket=ctx.wrap_socket(server.socket,server_side=True)
    advertiser=None
    try:
        try:
            advertiser=subprocess.Popen(['avahi-publish-service','Sakura-'+fingerprint[:16],'_sakura-mobile._tcp',str(args.port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print('Avahi unavailable; QR pairing still works.')
        print('Sakura Mobile listening on '+args.host+':'+str(args.port),flush=True)
        server.serve_forever()
    finally:
        server.server_close()
        if advertiser:
            advertiser.terminate()

if __name__=='__main__':
    main()
