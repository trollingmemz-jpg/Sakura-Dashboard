"""Firefox installation entry point; no browser security settings modified."""
import shutil,subprocess
from pathlib import Path
from PySide6.QtWidgets import QMessageBox,QApplication
def install_firefox(parent):
 root=Path(__file__).resolve().parent
 signed=root/'browser-connector'/'sakura-media-signed.xpi'
 manifest=root/'browser-connector'/'manifest.json'
 firefox=shutil.which('firefox')
 cmd=[firefox] if firefox else ['flatpak','run','org.mozilla.firefox'] if shutil.which('flatpak') else None
 if not cmd:
  QMessageBox.warning(parent,'Firefox connector','Firefox was not found. Install Firefox first.');return
 try:
  if signed.is_file():
   subprocess.Popen(cmd+[str(signed)],start_new_session=True)
  else:
   QApplication.clipboard().setText(str(manifest))
   subprocess.Popen(cmd+['about:debugging#/runtime/this-firefox'],start_new_session=True)
   QMessageBox.information(parent,'Firefox test connector','The manifest path is copied. In Firefox choose Load Temporary Add-on and paste the path. Permanent one-click installation requires a Mozilla-signed package.')
 except OSError as e:QMessageBox.warning(parent,'Firefox connector',str(e))
