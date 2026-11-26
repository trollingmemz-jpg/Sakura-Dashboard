"""Dashboard-owned mobile companion lifecycle and pairing UI."""
import json
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import sys
from PySide6.QtCore import QObject,QProcess,QTimer,Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QLabel,QPushButton,QPlainTextEdit

ROOT=Path.home()/'.config/sakura-mobile'
BRIDGE=Path(__file__).resolve().with_name('mobile_bridge.py')

def network():
    routes=json.loads(subprocess.check_output(['ip','-j','-4','route','show','default'],text=True,timeout=2))
    for route in sorted(routes,key=lambda r:r.get('metric',0)):
        dev=route.get('dev')
        if not dev:continue
        links=json.loads(subprocess.check_output(['ip','-j','-4','addr','show','dev',dev],text=True,timeout=2))
        for link in links:
            mac=link.get('address','')
            for addr in link.get('addr_info',[]):
                host=addr.get('local','')
                if addr.get('scope')=='global' and ipaddress.IPv4Address(host).is_private and len(mac)==17:
                    return host,mac
    raise RuntimeError('No private LAN address found. Connect Ethernet or Wi-Fi.')

class MobileCompanion(QObject):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner
        self.process=QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed)
        self.message='Starting mobile companion…'
        self.buffer=''
        self.args=[]
        self.closing=False
        self.started=False
        self.timer=QTimer(self);self.timer.timeout.connect(self.ensure);self.timer.start(10000)
        QApplication.instance().aboutToQuit.connect(self.stop)
        QTimer.singleShot(0,self.ensure)
        if not (ROOT/'paired').exists():
            QTimer.singleShot(1200,self.show_pairing)
    def ensure(self):
        if self.closing:return
        try:
            host,mac=network()
            args=['--host',host,'--mac',mac]
            if self.process.state()!=QProcess.ProcessState.NotRunning:
                if args==self.args:return
                self.process.terminate()
                return
            self.args=args
            self.buffer=''
            self.message='Starting mobile companion…'
            self.process.start(sys.executable,[str(BRIDGE),*args])
        except Exception as e:self.message=str(e)
    def output(self):
        self.buffer=(self.buffer+bytes(self.process.readAllStandardOutput()).decode(errors='replace'))[-4000:]
        if 'listening on' in self.buffer:
            self.message='Ready: '+self.args[1]+':8743'
        elif self.buffer.strip():self.message=self.buffer.strip()[-500:]
    def failed(self,*_):
        self.message=self.process.errorString()
    def finished(self,*_):
        if not self.closing:self.message='Bridge stopped. '+self.buffer.strip()[-350:]
    def stop(self):
        self.closing=True
        self.timer.stop()
        if self.process.state()!=QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1200):
                self.process.kill();self.process.waitForFinished(500)
    def show_pairing(self):
        dlg=QDialog(self.owner);dlg.setWindowTitle('Sakura Mobile • Pair your phone')
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet('QDialog{background:#201329;color:#f5d9ef} QLabel{color:#f5d9ef} QPushButton{background:#39253e;color:#f5d9ef;padding:9px;border-radius:6px}')
        layout=QVBoxLayout(dlg)
        title=QLabel('SAKURA  /  MOBILE');title.setStyleSheet('font-size:24px;font-weight:bold;color:#f478d7');layout.addWidget(title)
        hint=QLabel('Open Sakura Mobile on your phone, connect to the same network and scan the pairing QR. This grants remote PC control. Keep the QR private.');hint.setWordWrap(True);layout.addWidget(hint)
        status=QLabel();status.setWordWrap(True);layout.addWidget(status)
        qr=QLabel();qr.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(qr)
        manual=QPlainTextEdit();manual.setReadOnly(True);manual.setMaximumHeight(100);manual.hide();layout.addWidget(manual)
        payload=''
        def generate():
            nonlocal payload
            qr.clear();manual.clear();manual.hide();payload=''
            try:
                if not self.args:self.ensure()
                if not self.args:raise RuntimeError(self.message)
                payload=subprocess.check_output([sys.executable,str(BRIDGE),*self.args,'--pair-json'],text=True,timeout=8).strip()
                json.loads(payload)
                if shutil.which('qrencode'):
                    raw=subprocess.check_output(['qrencode','-t','PNG','-s','5','-o','-'],input=payload.encode(),timeout=4)
                else:
                    import io,qrcode
                    stream=io.BytesIO();qrcode.make(payload).save(stream,format='PNG');raw=stream.getvalue()
                image=QPixmap()
                if not image.loadFromData(raw):raise RuntimeError('QR rendering failed')
                qr.setPixmap(image)
            except Exception as e:
                qr.setText('QR unavailable: '+str(e))
                if payload:manual.setPlainText(payload);manual.show()
        reveal=QPushButton('Show manual pairing code');reveal.clicked.connect(lambda:(manual.setPlainText(payload),manual.show()));layout.addWidget(reveal)
        retry=QPushButton('Refresh pairing');retry.clicked.connect(generate);layout.addWidget(retry)
        close=QPushButton('Close / pair later');close.clicked.connect(dlg.accept);layout.addWidget(close)
        def refresh():
            status.setText('Paired • '+self.message if (ROOT/'paired').exists() else self.message)
        timer=QTimer(dlg);timer.timeout.connect(refresh);timer.start(500)
        generate();refresh();dlg.exec()
