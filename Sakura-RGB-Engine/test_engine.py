import tempfile, unittest, json
from pathlib import Path
from engine import Engine, Device
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.p=self.root/'test:rgb';self.p.mkdir()
        for name,val in {'multi_index':'blue red green','multi_intensity':'0 0 0','max_brightness':'100','brightness':'0'}.items():(self.p/name).write_text(val)
        self.e=Engine(self.root);self.e.scan_leds()
    def test_colour_order(self):
        self.e.set_color(self.e.devices[0],(255,128,0));self.assertEqual((self.p/'multi_intensity').read_text().strip(),'0 100 50')
    def test_off(self):
        self.e.set_color(self.e.devices[0],(0,0,0));self.assertEqual((self.p/'brightness').read_text().strip(),'0')
    def test_unknown(self):
        d=Device('MP810','USB HID','09DA:FAEF','unverified');self.e.devices.append(d)
        with self.assertRaises(ValueError):self.e.set_color(d,(255,0,0))
    def test_bad_rgb(self):
        with self.assertRaises(ValueError):self.e.set_color(self.e.devices[0],(256,0,0))
    def test_report(self):
        self.assertNotIn('path',json.loads(self.e.report())['devices'][0])
    def test_channel_change(self):
        (self.p/'multi_index').write_text('red green white')
        with self.assertRaises(ValueError):self.e.set_color(self.e.devices[0],(255,0,0))
if __name__=='__main__':unittest.main()
