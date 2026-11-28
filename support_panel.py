"""Manual cloud support. No automatic telemetry."""
import json, os, uuid, platform, queue, threading, tempfile
import urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone
from PySide6.QtCore import Qt, QTimer, QObject
from PySide6.QtWidgets import (QApplication, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QWidget, QLineEdit, QPlainTextEdit, QCheckBox,
    QListWidget, QMessageBox)
from inline_panel import InlinePanel

ROOT = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'sakura'
FILE = ROOT/'support-preview.json'

def load():
    try:
        data = json.loads(FILE.read_text())
        uuid.UUID(data['uuid'], version=4)
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return {'uuid': str(uuid.uuid4()), 'auto': False, 'hardware': False,
                'performance': False, 'reports': []}

def save(data):
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='support-', dir=ROOT)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, FILE)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

API = 'https://sakura-support.codex-mailbox-c46153a.workers.dev'
def request(path, device, token=None, payload=None):
    headers = {'Accept': 'application/json', 'User-Agent': 'Sakura-Dashboard/1.0'}
    if token:
        headers.update({'Authorization': 'Bearer '+token, 'X-Device-UUID': device})
    if payload is not None: headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(API+path, headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None)
    # Never forward a device credential through a redirect.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=12) as response:
            return json.loads(response.read(1024*1024))
    except urllib.error.HTTPError as exc:
        reason = ''
        try:
            response = json.loads(exc.read(4096))
            reason = str(response.get('error', ''))[:240]
        except (ValueError, OSError, AttributeError):
            pass
        raise RuntimeError('Support API HTTP '+str(exc.code)+(' — '+reason if reason else '')) from None
    except (OSError, ValueError) as exc:
        raise RuntimeError('Support connection failed: '+type(exc).__name__+' — '+str(exc)[:240]) from None

def support_panel(host):
    if getattr(host, '_support_busy', False):
        QMessageBox.information(host, 'Sakura Support', 'A previous support operation is still running.')
        return
    data = load()
    try:
        save(data)
    except OSError as exc:
        QMessageBox.warning(host, 'Sakura Support', 'Cannot save local support state: '+str(exc))
        return
    panel = InlinePanel(host)
    panel.setWindowTitle('Sakura / Support')
    root = QVBoxLayout(panel)
    panel.setStyleSheet(panel.styleSheet()+'''
    QTabWidget::pane { border: 1px solid #53394f; border-radius: 8px; }
    QTabBar::tab { background: #29202e; color: #e4c8db; padding: 8px; }
    QTabBar::tab:selected { background: #54334e; color: #ffd1e7; }
    QPlainTextEdit, QListWidget { background: #211b28; color: #f5d9ef;
      border: 1px solid #53394f; border-radius: 6px; padding: 6px; }
    ''')
    def label(text, layout):
        w = QLabel(text); w.setTextFormat(Qt.TextFormat.PlainText)
        w.setWordWrap(True); layout.addWidget(w); return w
    label('Sakura Support • Open beta', root).setStyleSheet('font-size: 22px; color: #edb3ce')
    status = label('Manual reporting only. Reports are sent to a private GitHub repository.', root)
    tabs = QTabWidget(); root.addWidget(tabs)
    def page(name):
        widget = QWidget(); layout = QVBoxLayout(widget); tabs.addTab(widget, name)
        return layout
    overview = page('Overview')
    label('Your installation identity', overview)
    identity = label(data['uuid'], overview)
    identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    copy = QPushButton('Copy device UUID'); overview.addWidget(copy)
    copy.clicked.connect(lambda: QApplication.clipboard().setText(data['uuid']))
    summary = label('', overview)
    start = QPushButton('Report a new issue'); overview.addWidget(start)
    start.clicked.connect(lambda: tabs.setCurrentIndex(1))
    overview.addStretch()
    report = page('Report an issue')
    label('Tell us what went wrong', report)
    subject = QLineEdit(); subject.setPlaceholderText('Issue title'); subject.setMaxLength(160); report.addWidget(subject)
    body = QPlainTextEdit(); body.setPlaceholderText('Describe the problem and how to reproduce it. Avoid personal details.'); report.addWidget(body)
    hardware = QCheckBox('Include platform information'); report.addWidget(hardware)
    perf = QCheckBox('Performance statistics unavailable'); perf.setEnabled(False); report.addWidget(perf)
    consent = QCheckBox('I agree to send this report and my installation UUID to Sakura Support.'); report.addWidget(consent)
    preview = QPlainTextEdit(); preview.setReadOnly(True); report.addWidget(preview)
    submit = QPushButton('Submit report'); report.addWidget(submit)
    messages = page('Messages')
    label('Select a submitted report to retrieve developer replies. Old preview reports remain local.', messages)
    items = QListWidget(); items.setMinimumHeight(90); items.setMaximumHeight(140); messages.addWidget(items)
    detail = QPlainTextEdit(); detail.setReadOnly(True); detail.setMinimumHeight(100); messages.addWidget(detail)
    send = QPushButton('Refresh developer replies'); messages.addWidget(send)
    privacy = page('Privacy')
    label('Manual submissions go to the Sakura team through Cloudflare and private GitHub Issues. Do not include secrets or personal information. Server-side deletion is not available yet.', privacy)
    auto = QCheckBox('Allow automatic crash reporting in a future connected version')
    auto.setChecked(False); auto.setEnabled(False); privacy.addWidget(auto)
    for box, key in [(hardware,'hardware'),(perf,'performance')]:
        box.setChecked(False)
    def persist():
        try: save(data); return True
        except OSError as exc:
            QMessageBox.warning(panel,'Sakura Support',str(exc)); return False
    def payload():
        result = {'device_uuid': data['uuid'], 'title': subject.text().strip(),
                  'description': body.toPlainText().strip(), 'consent': True}
        if hardware.isChecked(): result['platform'] = platform.system()+' '+platform.release()
        return result
    def refresh_preview(*args):
        preview.setPlainText(json.dumps(payload(), indent=2))
        submit.setEnabled(not getattr(host, '_support_busy', False) and consent.isChecked() and bool(subject.text().strip() and body.toPlainText().strip()) and len(body.toPlainText())<=8000)
    def refresh():
        summary.setText(f"Reports on this device: {len(data['reports'])} | Manual cloud reporting")
        items.clear()
        for entry in data['reports']: items.addItem(('#'+str(entry['issue_number'])+' ' if entry.get('issue_number') else '[Local / unconfirmed] ')+entry['title'])
        detail.clear()
    def preference(key, value):
        if getattr(host, '_support_busy', False): return
        data[key] = value; persist(); refresh_preview()
    auto.toggled.connect(lambda v: preference('auto',v))
    hardware.toggled.connect(lambda v: preference('hardware',v))
    perf.toggled.connect(lambda v: preference('performance',v))
    subject.textChanged.connect(refresh_preview); body.textChanged.connect(refresh_preview); consent.toggled.connect(refresh_preview)
    results = queue.Queue()
    timer = QTimer(panel)
    def launch(work, done):
        if getattr(host, '_support_busy', False): return
        host._support_busy = True
        status.setText('Contacting Sakura Support…')
        submit.setEnabled(False); send.setEnabled(False); hardware.setEnabled(False); delete.setEnabled(False)
        def run():
            try: results.put((done, work(), None))
            except Exception as exc: results.put((done, None, str(exc)))
            finally: host._support_busy = False
        threading.Thread(target=run, daemon=True).start()
    def drain():
        try: done, value, error = results.get_nowait()
        except queue.Empty: return
        if error: status.setText(error)
        else: status.setText('Sakura Support connected')
        done(value, error)
        send.setEnabled(True); hardware.setEnabled(True); delete.setEnabled(not data.get('token')); refresh_preview()
    timer.timeout.connect(drain); timer.start(100)
    def submit_report():
        if not consent.isChecked() or not submit.isEnabled(): return
        entry = payload()
        entry.update(id=str(uuid.uuid4()), created=datetime.now(timezone.utc).isoformat(),
                     status='pending', replies=[])
        data['reports'].append(entry)
        if not persist(): data['reports'].pop(); return
        subject.clear(); body.clear(); consent.setChecked(False)
        refresh(); tabs.setCurrentIndex(2); items.setCurrentRow(len(data['reports'])-1)
        def work():
            token = data.get('token')
            if not token:
                registered = request('/register', data['uuid'], payload={'uuid':data['uuid'],'consent':True})
                token = registered['token']
                data['token'] = token
                save(data)
            answer = request('/report', data['uuid'], token, entry)
            entry.update(status=answer.get('status','unconfirmed'), issue_number=answer.get('issue_number'))
            save(data)
            return answer
        def done(value, error):
            if error:
                entry['status']='unconfirmed'; entry['delivery_error']=error; persist()
                status.setText(error+' — check GitHub before submitting again.')
            refresh(); items.setCurrentRow(len(data['reports'])-1)
        launch(work, done)
    def show_report(row):
        if not 0<=row<len(data['reports']):
            detail.clear(); return
        entry=data['reports'][row]
        lines=[entry['title'], 'Status: '+str(entry.get('status','local preview')),
               'GitHub issue: '+str(entry.get('issue_number') or 'Not confirmed'),
               'Error: '+str(entry.get('delivery_error','None recorded')), '', entry.get('description','')]
        for msg in entry.get('developer_messages',[]):
            lines.extend(['',msg.get('author','Sakura Development Team')+' · '+msg.get('created_at',''),msg.get('message','')])
        detail.setPlainText('\n'.join(lines))
    def refresh_messages():
        row=items.currentRow()
        if not 0<=row<len(data['reports']): return
        entry=data['reports'][row]
        if not entry.get('issue_number') or not data.get('token'):
            status.setText('This report has no confirmed cloud issue.'); return
        def work():
            answer=request('/messages/'+entry['id'],data['uuid'],data['token'])
            entry['developer_messages']=answer.get('messages',[])
            entry['status']=answer.get('status','submitted')
            save(data)
            return answer
        def done(value,error):
            if items.currentRow()==row: show_report(row)
        launch(work,done)
    submit.clicked.connect(submit_report); items.currentRowChanged.connect(show_report); send.clicked.connect(refresh_messages)
    delete = QPushButton('Reset local preview data'); privacy.addWidget(delete)
    delete.setEnabled(not data.get('token'))
    def reset():
        if getattr(host, '_support_busy', False) or data.get('token'): return
        if QMessageBox.question(panel,'Reset support data','Delete local reports and reset the device UUID?') != QMessageBox.StandardButton.Yes: return
        data.clear(); data.update(uuid=str(uuid.uuid4()),auto=False,hardware=False,performance=False,reports=[])
        persist(); identity.setText(data['uuid']); auto.setChecked(False); hardware.setChecked(False); perf.setChecked(False); refresh(); refresh_preview()
    delete.clicked.connect(reset); privacy.addStretch()
    refresh(); refresh_preview(); panel.exec(); timer.stop()


class SupportReplyMonitor(QObject):
    """Poll one confirmed report at a time, without uploading diagnostics.

    A separate notification ledger avoids overwriting the Support panel's
    state while a manual submission or reply refresh is running.
    """
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.results = queue.Queue()
        self.busy = False
        self.cursor = 0
        self.ledger_path = ROOT/'support-notified.json'
        self.timer = QTimer(self)
        self.timer.setInterval(90000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.drain_timer = QTimer(self)
        self.drain_timer.setInterval(500)
        self.drain_timer.timeout.connect(self.drain)
        self.drain_timer.start()
        QTimer.singleShot(5000, self.poll)

    def poll(self):
        if self.busy or getattr(self.host, '_support_busy', False):
            return
        if not self.host.notifications.enabled or not FILE.exists():
            return
        data = load()
        token = data.get('token')
        reports = [r for r in data.get('reports', [])
                   if r.get('issue_number') and r.get('id')]
        if not token or not reports:
            return
        # 40 requests/hour at most, leaving room for manual refreshes.
        entry = reports[self.cursor % len(reports)]
        self.cursor += 1
        device = data['uuid']
        report_id = entry['id']
        self.busy = True
        def work():
            try:
                response = request('/messages/'+report_id, device, token)
                self.results.put((device, report_id, response))
            except Exception:
                self.results.put(None)
        threading.Thread(target=work, daemon=True).start()

    def drain(self):
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            return
        self.busy = False
        if result is None or not self.host.notifications.enabled:
            return
        device, report_id, response = result
        data = load()
        if device != data.get('uuid') or not data.get('token'):
            return
        entry = next((r for r in data.get('reports', [])
                      if r.get('id') == report_id), None)
        if entry is None:
            return
        try:
            ledger = json.loads(self.ledger_path.read_text())
            if not isinstance(ledger, dict):
                ledger = {}
        except (OSError, ValueError):
            ledger = {}
        key = device+':'+report_id
        seen = set(str(i) for i in ledger.get(key, []))
        # Replies already fetched manually are not new notifications.
        seen.update(str(m['id']) for m in entry.get('developer_messages', [])
                    if m.get('id') is not None)
        fresh = []
        for msg in response.get('messages', []):
            if msg.get('id') is None:
                continue
            mid = str(msg['id'])
            if mid not in seen:
                seen.add(mid)
                fresh.append(msg)
        ledger[key] = sorted(seen)
        try:
            ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix='support-notified-', dir=ROOT)
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(ledger, f)
                os.replace(tmp, self.ledger_path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        except OSError:
            return  # Avoid repeating pop-ups if the ledger cannot persist.
        if fresh:
            import time
            count = len(fresh)
            title = 'New developer reply' if count == 1 else str(count)+' new developer replies'
            issue = str(entry.get('issue_number'))
            body = 'Issue #'+issue+' — '+str(entry.get('title',''))[:100]
            body += ' · Open Sakura Support / Messages'
            item = ('Sakura Support', title, body, time.time())
            self.host.notifications.history.appendleft(item)
            self.host.notifications.pending.append(item)
            self.host.update()

    def close(self):
        self.timer.stop()
        self.drain_timer.stop()
