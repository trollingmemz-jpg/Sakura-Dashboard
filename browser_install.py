"""Package the entire Firefox extension for KDE/Flatpak document portals."""
import shutil,subprocess,zipfile,os
from pathlib import Path
from PySide6.QtWidgets import QMessageBox,QApplication
def install_firefox(parent):
 root=Path(__file__).resolve().parent/'browser-connector'
 signed=root/'sakura-media-signed.xpi'
 firefox=shutil.which('firefox')
 cmd=[firefox] if firefox else ['flatpak','run','org.mozilla.firefox'] if shutil.which('flatpak') else None
 if not cmd:
  QMessageBox.warning(parent,'Firefox connector','Firefox was not found.');return
 try:
  if signed.is_file():
   subprocess.Popen(cmd+[str(signed)],start_new_session=True);return
  downloads=Path.home()/'Downloads';downloads.mkdir(parents=True,exist_ok=True)
  archive=downloads/'Sakura-Media-Connector.zip'
  temp=archive.with_suffix('.tmp')
  required=('manifest.json','background.js','content.js','popup.html','popup.js','popup.css')
  with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
   for name in required:z.write(root/name,name)
  with zipfile.ZipFile(temp) as z:
   if z.testzip() or set(z.namelist())!=set(required):raise ValueError('Invalid connector archive')
  os.replace(temp,archive)
  QApplication.clipboard().setText(str(archive))
  subprocess.Popen(cmd+['about:debugging#/runtime/this-firefox'],start_new_session=True)
  QMessageBox.information(parent,'Firefox test connector','Remove the old temporary extension, then choose Load Temporary Add-on and select Sakura-Media-Connector.zip from Downloads. The ZIP path has been copied. Do not select manifest.json.')
 except (OSError,ValueError,zipfile.BadZipFile) as e:QMessageBox.warning(parent,'Firefox connector',str(e))
