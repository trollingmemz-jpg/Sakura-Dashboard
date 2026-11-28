"""Local-only Sakura Support preview. No network requests or telemetry."""
import json, os, uuid, platform
from pathlib import Path
from datetime import datetime, timezone
from PySide6.QtCore import Qt
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
    tmp = FILE.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FILE)

def support_panel(host):
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
    label('Local design preview — nothing is sent to GitHub or Discord.', root)
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
    perf = QCheckBox('Include performance statistics (not collected in preview)'); report.addWidget(perf)
    preview = QPlainTextEdit(); preview.setReadOnly(True); report.addWidget(preview)
    submit = QPushButton('Save local test report'); report.addWidget(submit)
    messages = page('Messages')
    label('Local test reports — developer messaging is not connected.', messages)
    items = QListWidget(); messages.addWidget(items)
    detail = QPlainTextEdit(); detail.setReadOnly(True); messages.addWidget(detail)
    reply = QPlainTextEdit(); reply.setPlaceholderText('Write a local test reply'); messages.addWidget(reply)
    send = QPushButton('Save local reply'); messages.addWidget(send)
    privacy = page('Privacy')
    label('Your preferences are saved locally. Automatic reporting is not implemented.', privacy)
    auto = QCheckBox('Allow automatic crash reporting in a future connected version')
    auto.setChecked(data.get('auto', False)); privacy.addWidget(auto)
    for box, key in [(hardware,'hardware'),(perf,'performance')]:
        box.setChecked(data.get(key,False))
    def persist():
        try: save(data); return True
        except OSError as exc:
            QMessageBox.warning(panel,'Sakura Support',str(exc)); return False
    def payload():
        result = {'device_uuid': data['uuid'], 'title': subject.text().strip(),
                  'description': body.toPlainText().strip(), 'preview_only': True}
        if hardware.isChecked(): result['platform'] = platform.system()+' '+platform.release()
        return result
    def refresh_preview(*args):
        preview.setPlainText(json.dumps(payload(), indent=2))
        submit.setEnabled(bool(subject.text().strip() and body.toPlainText().strip()))
    def refresh():
        summary.setText(f"Local reports: {len(data['reports'])} | Network: disconnected")
        items.clear()
        for entry in data['reports']: items.addItem(entry['title'])
        detail.clear()
    def preference(key, value):
        data[key] = value; persist(); refresh_preview()
    auto.toggled.connect(lambda v: preference('auto',v))
    hardware.toggled.connect(lambda v: preference('hardware',v))
    perf.toggled.connect(lambda v: preference('performance',v))
    subject.textChanged.connect(refresh_preview); body.textChanged.connect(refresh_preview)
    def submit_report():
        entry = payload()
        entry.update(id=str(uuid.uuid4()), created=datetime.now(timezone.utc).isoformat(), replies=[])
        data['reports'].append(entry)
        if not persist(): data['reports'].pop(); return
        subject.clear(); body.clear(); refresh(); tabs.setCurrentIndex(2); items.setCurrentRow(len(data['reports'])-1)
    def show_report(row):
        detail.setPlainText(json.dumps(data['reports'][row],indent=2) if 0<=row<len(data['reports']) else '')
    def save_reply():
        row=items.currentRow(); value=reply.toPlainText().strip()
        if not value or not 0<=row<len(data['reports']): return
        entry=data['reports'][row]; entry['replies'].append(value)
        if not persist(): entry['replies'].pop(); return
        reply.clear(); show_report(row)
    submit.clicked.connect(submit_report); items.currentRowChanged.connect(show_report); send.clicked.connect(save_reply)
    delete = QPushButton('Delete local test reports and reset identity'); privacy.addWidget(delete)
    def reset():
        if QMessageBox.question(panel,'Reset support data','Delete local reports and reset the device UUID?') != QMessageBox.StandardButton.Yes: return
        data.clear(); data.update(uuid=str(uuid.uuid4()),auto=False,hardware=False,performance=False,reports=[])
        persist(); identity.setText(data['uuid']); auto.setChecked(False); hardware.setChecked(False); perf.setChecked(False); refresh(); refresh_preview()
    delete.clicked.connect(reset); privacy.addStretch()
    refresh(); refresh_preview(); panel.exec()
