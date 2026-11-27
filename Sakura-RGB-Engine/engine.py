"""Native discovery and Linux multicolour LED control; no OpenRGB dependency."""
from dataclasses import dataclass, asdict
from pathlib import Path
import platform
import json
import subprocess
import re

TARGETS = {(0x09DA,0xFAEF): 'A4Tech controller / possible Monoprice MP810',
           (0x258A,0x0027): 'Sino Wealth controller',
           (0x1B1C,0x1B3C): 'Corsair Harpoon RGB'}
@dataclass
class Device:
    name: str
    kind: str
    identifier: str
    status: str
    channels: str = ''
    interface: int = -1
    usage_page: int = 0
    usage: int = 0
    path: str = ''

class Engine:
    def __init__(self, led_root='/sys/class/leds'):
        self.led_root = Path(led_root)
        self.devices = []
        self.notes = []
    def scan(self):
        self.devices, self.notes = [], []
        if platform.system() == 'Linux':
            self.scan_linux_hid()
            self.scan_leds()
            return self.devices
        try:
            import hid
            for item in hid.enumerate():
                v,p = item['vendor_id'],item['product_id']
                name=TARGETS.get((v,p)) or item.get('product_string') or 'USB HID device'
                self.devices.append(Device(name,'USB HID',f'{v:04X}:{p:04X}', 'Protocol unverified — read-only',interface=item.get('interface_number',-1),usage_page=item.get('usage_page',0),usage=item.get('usage',0)))
        except Exception as e:
            self.notes.append('HID discovery unavailable: '+type(e).__name__)
        if platform.system() == 'Windows':
            self.scan_memory()
        return self.devices
    def scan_linux_hid(self, root='/sys/bus/hid/devices'):
        for entry in sorted(Path(root).glob('*')):
            try:
                fields=dict(line.split('=',1) for line in (entry/'uevent').read_text().splitlines() if '=' in line)
                bus, vendor, product=fields['HID_ID'].split(':')
                v,p=int(vendor,16),int(product,16)
                name=TARGETS.get((v,p)) or fields.get('HID_NAME') or 'HID device'
                interface=-1
                for parent in entry.resolve().parents:
                    if (parent/'bInterfaceNumber').is_file():
                        interface=int((parent/'bInterfaceNumber').read_text().strip(),16)
                        break
                self.devices.append(Device(name,'USB HID' if int(bus,16)==3 else 'HID',f'{v:04X}:{p:04X}','Protocol unverified — read-only',interface=interface))
            except (OSError,ValueError,KeyError):
                continue
    def scan_memory(self):
        command = 'Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer,PartNumber | ConvertTo-Json -Compress'
        try:
            p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
            rows=json.loads(p.stdout or '[]')
            if isinstance(rows,dict): rows=[rows]
            for row in rows or []:
                manufacturer=str(row.get('Manufacturer') or '').strip()
                part=str(row.get('PartNumber') or '').strip()
                self.devices.append(Device((manufacturer+' '+part).strip() or 'Memory module','RAM','DIMM','Inventory only — SMBus lighting driver pending'))
        except Exception as e:
            self.notes.append('RAM inventory unavailable: '+type(e).__name__)
    def scan_leds(self):
        for entry in sorted(self.led_root.glob('*')):
            try:
                channels=(entry/'multi_index').read_text().split()
                if sorted(channels)!=['blue','green','red']: continue
                if not (entry/'multi_intensity').is_file(): continue
                self.devices.append(Device(entry.name,'Linux LED',entry.name,'Native RGB control available',' '.join(channels),path=str(entry)))
            except OSError: continue
    def set_color(self, device, rgb):
        if not any(d is device for d in self.devices) or device.kind!='Linux LED':
            raise ValueError('No verified writable driver for this device')
        if len(rgb)!=3 or any(type(v) is not int or not 0<=v<=255 for v in rgb):
            raise ValueError('Expected RGB bytes')
        p=Path(device.path)
        if p.parent != self.led_root or p.name!=device.identifier: raise ValueError('Invalid LED path')
        channels=(p/'multi_index').read_text().split()
        if sorted(channels)!=['blue','green','red']: raise ValueError('Unexpected LED channels')
        maximum=int((p/'max_brightness').read_text())
        if not 1<=maximum<=65535: raise ValueError('Unexpected brightness range')
        values=dict(zip(('red','green','blue'),rgb))
        (p/'multi_intensity').write_text(' '.join(str(round(values[c]*maximum/255)) for c in channels)+'\n')
        (p/'brightness').write_text(str(maximum if any(rgb) else 0)+'\n')
    def report(self):
        rows=[]
        for d in self.devices:
            row=asdict(d); row.pop('path'); rows.append(row)
        return json.dumps({'engine':'Sakura RGB Engine 0.2','os':platform.system(),'devices':rows,'notes':self.notes},indent=2)
