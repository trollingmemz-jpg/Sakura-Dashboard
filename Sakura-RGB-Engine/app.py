import sys
import threading
import queue
from pathlib import Path
from engine import Engine

def main():
    if '--scan' in sys.argv:
        engine=Engine()
        engine.scan()
        print(engine.report())
        return
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QColorDialog, QFileDialog, QMessageBox)

    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.engine=Engine()
            self.results=queue.Queue()
            self.busy=False
            self.color=QColor('#f478d7')
            self.setWindowTitle('Sakura RGB Engine 0.2')
            self.resize(1000,600)
            self.setMinimumSize(660,420)
            self.setStyleSheet("""
                QWidget { background: #1b1225; color: #f5d9ef; font-size: 14px; }
                QPushButton { background: #47304e; padding: 10px; border-radius: 6px; }
                QPushButton:hover { background: #684469; }
                QPushButton:disabled { color: #88798e; background: #30253a; }
                QTableWidget { background: #24192f; gridline-color: #392842; selection-background-color: #85507e; }
                QHeaderView::section { background: #392842; color: #f5d9ef; padding: 7px; border: 0; }
            """)
            layout=QVBoxLayout(self)
            layout.setContentsMargins(22,18,22,18)
            title=QLabel('桜  /  SAKURA RGB ENGINE')
            title.setStyleSheet('font-size: 24px; font-weight: bold; color: #f478d7;')
            layout.addWidget(title)
            subtitle=QLabel('Native hardware discovery and lighting')
            layout.addWidget(subtitle)
            self.table=QTableWidget(0,4)
            self.table.setHorizontalHeaderLabels(['Device','Connection','Hardware ID','Driver status'])
            self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table.verticalHeader().hide()
            layout.addWidget(self.table)
            row=QHBoxLayout()
            self.scan_button=QPushButton('Scan hardware')
            self.apply_button=QPushButton('Set colour')
            self.export_button=QPushButton('Save support report')
            self.apply_button.setEnabled(False)
            self.export_button.setEnabled(False)
            row.addWidget(self.scan_button)
            row.addWidget(self.apply_button)
            row.addStretch()
            row.addWidget(self.export_button)
            layout.addLayout(row)
            self.status=QLabel('Ready')
            self.status.setTextFormat(Qt.TextFormat.PlainText)
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.scan_button.clicked.connect(self.refresh)
            self.apply_button.clicked.connect(self.choose)
            self.export_button.clicked.connect(self.save)
            self.table.itemSelectionChanged.connect(self.selection)
            self.timer=QTimer(self)
            self.timer.timeout.connect(self.poll)
            self.timer.start(100)
            self.refresh()

        def refresh(self):
            if self.busy:return
            self.busy=True
            self.scan_button.setEnabled(False)
            self.apply_button.setEnabled(False)
            self.export_button.setEnabled(False)
            self.table.clearSelection()
            self.status.setText('Scanning hardware without sending device commands…')
            def work():
                try:self.engine.scan();self.results.put(None)
                except Exception as e:self.results.put(type(e).__name__)
            threading.Thread(target=work,daemon=True).start()

        def poll(self):
            try:error=self.results.get_nowait()
            except queue.Empty:return
            self.table.setRowCount(0)
            for i,d in enumerate(self.engine.devices):
                self.table.insertRow(i)
                for j,value in enumerate((d.name,d.kind,d.identifier,d.status)):
                    self.table.setItem(i,j,QTableWidgetItem(str(value)))
            self.busy=False
            self.scan_button.setEnabled(True)
            self.export_button.setEnabled(True)
            self.selection()
            self.status.setText('Scan failed: '+error if error else f'{len(self.engine.devices)} interfaces / modules found. '+ ' '.join(self.engine.notes))

        def selected(self):
            row=self.table.currentRow()
            if self.busy or not self.table.selectedItems() or not 0<=row<len(self.engine.devices):
                return None
            return self.engine.devices[row]

        def selection(self):
            d=self.selected()
            self.apply_button.setEnabled(d is not None and d.kind=='Linux LED')

        def choose(self):
            d=self.selected()
            if d is None or d.kind!='Linux LED':return
            color=QColorDialog.getColor(self.color,self,'Choose lighting colour')
            if not color.isValid():return
            try:
                self.engine.set_color(d,(color.red(),color.green(),color.blue()))
                self.color=color
                self.status.setText('Colour applied.')
            except (OSError,ValueError) as e:QMessageBox.warning(self,'Lighting',str(e))

        def save(self):
            if self.busy:return
            path,_=QFileDialog.getSaveFileName(self,'Save support report','Sakura-RGB-report.json','JSON report (*.json)')
            if path:
                try:
                    Path(path).write_text(self.engine.report(),encoding='utf-8')
                    self.status.setText('Report saved. Review it before sharing.')
                except OSError as e:QMessageBox.warning(self,'Report',str(e))

    app=QApplication(sys.argv)
    window=Window()
    window.show()
    sys.exit(app.exec())

if __name__=='__main__':
    main()
