"""Explicit Windows widget theme, independent of native light/dark settings."""
from PySide6.QtGui import QColor,QPalette
def apply_theme(app):
    app.setStyle('Fusion')
    palette=QPalette()
    colors={'Window':'#201329','WindowText':'#f5d9ef','Base':'#201329','AlternateBase':'#39253e','Text':'#f5d9ef','Button':'#39253e','ButtonText':'#f5d9ef','BrightText':'#ffffff','Highlight':'#805071','HighlightedText':'#ffffff','ToolTipBase':'#39253e','ToolTipText':'#f5d9ef','PlaceholderText':'#b89ab5','Link':'#f478d7'}
    for role,color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole,role),QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.Text,QColor('#927b90'))
    palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.ButtonText,QColor('#927b90'))
    app.setPalette(palette)
    app.setStyleSheet('QDialog {background-color:#201329;color:#f5d9ef;} QAbstractScrollArea {background-color:#201329;color:#f5d9ef;} QTabWidget::pane {background:#201329;border:1px solid #805071;} QTabBar::tab {background:#39253e;color:#f5d9ef;padding:7px;} QTabBar::tab:selected {background:#805071;} QComboBox QAbstractItemView {background:#201329;color:#f5d9ef;selection-background-color:#805071;} QLineEdit,QPlainTextEdit,QTextEdit,QSpinBox,QComboBox {background:#39253e;color:#f5d9ef;} QHeaderView::section {background:#39253e;color:#f5d9ef;}')
