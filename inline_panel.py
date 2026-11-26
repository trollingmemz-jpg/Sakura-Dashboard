from PySide6.QtCore import Qt,QEventLoop,QEvent,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QHBoxLayout,QScrollArea

class InlinePanel(QWidget):
 def __init__(self,parent):
  super().__init__(parent);self.host=parent;self.result_code=0;self.loop=None;self.title='Settings'
  self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
  self.setStyleSheet('InlinePanel{background:#201329;border:1px solid #805071;border-radius:12px} QLabel,QCheckBox{color:#f5d9ef} QPushButton,QComboBox,QLineEdit,QSpinBox,QTableWidget{background:#39253e;color:#f5d9ef;padding:6px;border-radius:5px}')
  self.hide()
 def setMinimumWidth(self,width):pass
 def setWindowTitle(self,title):self.title=title
 def accept(self):self.done(1)
 def reject(self):self.done(0)
 def done(self,result):
  self.result_code=result;self.hide()
  if self.loop:self.loop.quit()
 def eventFilter(self,obj,event):
  if obj is self.host and event.type()==QEvent.Type.Resize:self.fit()
  if obj is self.host and event.type()==QEvent.Type.Close:self.reject()
  return False
 def fit(self):
  w=min(self.host.width()-24,max(480,int(self.host.width()*.72)))
  h=min(self.host.height()-24,max(320,int(self.host.height()*.94)))
  self.setGeometry((self.host.width()-w)//2,(self.host.height()-h)//2,w,h)
 def exec(self):
  old=self.layout()
  if old:
   body=QWidget();body.setLayout(old)
   outer=QVBoxLayout(self);header=QHBoxLayout();label=QLabel(self.title);label.setStyleSheet('font-size:18px;color:#f478d7');header.addWidget(label);header.addStretch();back=QPushButton('Close');back.clicked.connect(self.reject);header.addWidget(back);outer.addLayout(header)
   scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame);scroll.setWidget(body);outer.addWidget(scroll)
  self.host.installEventFilter(self);self.fit();self.show();self.raise_();self.setFocus()
  self.loop=QEventLoop();self.loop.exec();self.loop=None;self.host.removeEventFilter(self);self.hide();self.deleteLater();return self.result_code
