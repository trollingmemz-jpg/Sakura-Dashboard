#!/usr/bin/env python3
"""Install Sakura external-frame support into an existing Lightctl checkout."""
from pathlib import Path
import sys, shutil, time
root=Path(sys.argv[1]).expanduser() if len(sys.argv)>1 else Path.home()/"projects/lightctl"
p=root/"lightctl/visualizer.py"
d=root/"lightctl/daemon.py"
v=p.read_text(); a=d.read_text()
if "def sakura_frame(" in v and 'action == "sakura_frame"' in a:
    print("Already patched"); sys.exit(0)
def change(s, old, new):
    if s.count(old)!=1: raise SystemExit("Unexpected Lightctl source: "+old[:80])
    return s.replace(old,new,1)
v=change(v,'        self.active = False\n        self._lock', '        self.external = False\n        self.external_at = 0.0\n        self.active = False\n        self._lock')
v=change(v,'    def start(self, colour=None):','''    def sakura_frame(self, colour, level, devices):
        names = tuple(devices)
        available = {ch.name: ch for ch in self.channels}
        if not names or any(n not in available for n in names):
            return {"error": "Unknown or excluded visualizer device"}
        if self.active and not self.external:
            return {"error": "Stop the standalone visualizer first"}
        if self.active and tuple(ch.name for ch in self.channels if ch.enabled) != names:
            self.stop()
        self._base = tuple(max(0,min(255,int(c))) for c in colour)
        self._level = max(0.,min(1.,float(level)))
        self.external_at = time.monotonic()
        if self.active:
            return {"ok": True}
        for ch in self.channels:
            ch.enabled = ch.name in names
        return self.start(self._base, external=True)

    def sakura_stop(self):
        return self.stop() if self.external and self.active else {"ok": True}

    def _external_watch(self):
        while not self._stop_evt.wait(.25):
            if time.monotonic()-self.external_at > 5:
                self.stop()
                break

    def start(self, colour=None, external=False):''')
v=change(v,'            if np is None:', '            self.external = external\n            if not external:\n                for ch in self.channels: ch.enabled = True\n            if np is None and not external:')
start=v.index('            try:\n                self._proc = subprocess.Popen(')
end=v.index('            # Remember what each light',start)
v=v[:start]+'            if not external:\n'+'\n'.join('    '+x if x else x for x in v[start:end].split('\n'))+v[end:]
').map(x=>x?'    '+x:x).join('
')+v.slice(end);
v=change(v,'            for ch in self.channels:\n                try:\n                    ch.saved', '            for ch in self.channels:\n                if not ch.enabled: continue\n                try:\n                    ch.saved')
v=change(v,'            self._level = 0.0\n            self.active = True','            if not external: self._level = 0.0\n            self.active = True')
v=change(v,'threading.Thread(target=self._reader, daemon=True)','threading.Thread(target=self._external_watch if external else self._reader, daemon=True)')
v=change(v,'                for ch in self.channels\n            ]','                for ch in self.channels if ch.enabled\n            ]')
v=change(v,'        self.saved = None      # state to restore on stop','        self.enabled = True\n        self.saved = None      # state to restore on stop')
v=change(v,'return any(ch.light is light for ch in self.channels)','return any(ch.enabled and ch.light is light for ch in self.channels)')
v=change(v,'                if only is not None and ch.light not in only:','                if not ch.enabled: continue\n                if only is not None and ch.light not in only:')
v=change(v,'            if proc is None or proc.poll() is not None:','            if not self.external and (proc is None or proc.poll() is not None):')
v=change(v,'            pct = self.min_brightness + self._level * span','''            br, bg, bb = self._base
            h, s, _ = colorsys.rgb_to_hsv(br/255., bg/255., bb/255.)
            ch.h = int(round(h*360)) % 360
            ch.s = int(round(s*1000))
            pct = self.min_brightness + self._level * span''')
v=change(v,'        last_v, frames = None, 0','        last_v, frames = None, 0\n        last_colour = None')
v=change(v,'if last_v is None or abs(v - last_v) >= 8:', 'if last_v is None or abs(v - last_v) >= 8 or last_colour != (br,bg,bb):')
v=change(v,'                    last_v = v','                    last_v = v\n                    last_colour = (br,bg,bb)')
a=change(a,'    if action == "visualizer_start":','''    if action == "sakura_frame":
        return viz.sakura_frame(cmd["colour"], cmd["level"], cmd["devices"])
    if action == "sakura_stop":
        return viz.sakura_stop()
    if action == "visualizer_start":''')
for path, source in [(p,v),(d,a)]: compile(source,str(path),"exec")
stamp=str(int(time.time()))
for path, source in [(p,v),(d,a)]:
    shutil.copy2(path,path.with_name(path.name+".bak-sakura-"+stamp))
    path.write_text(source)
print("Patched Lightctl; backups suffix .bak-sakura-"+stamp)
