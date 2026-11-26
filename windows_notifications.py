"""Optional Windows notification mirror. Access requires Windows user consent."""
import asyncio, threading
from PySide6.QtCore import QObject, Signal

class WindowsNotifications(QObject):
    delivered=Signal(str,str,str)
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner
        self.delivered.connect(owner.receive)
        self.stop=threading.Event()
        self.status="Not started"
    def start(self):
        # Request permission only after the user explicitly enables the mirror.
        self.status="Enable notification access in Sakura"
    def enable(self):
        if getattr(self,'thread',None) and self.thread.is_alive():return
        self.stop.clear()
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()
    def run(self):
        try:asyncio.run(self.loop())
        except Exception as e:self.status="Notification access unavailable: "+str(e)
    async def loop(self):
        from winrt.windows.ui.notifications.management import UserNotificationListener,UserNotificationListenerAccessStatus
        from winrt.windows.ui.notifications import NotificationKinds,KnownNotificationBindings
        listener=UserNotificationListener.current
        access=await listener.request_access_async()
        if access!=UserNotificationListenerAccessStatus.ALLOWED:
            self.status="Windows notification access denied or unavailable";return
        self.status="Mirroring Windows notifications"
        seen=None
        while not self.stop.is_set():
            rows=await listener.get_notifications_async(NotificationKinds.TOAST)
            ids={row.id for row in rows}
            if seen is not None:
                for row in rows:
                    if row.id in seen:continue
                    try:
                        binding=row.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
                        if binding is None:continue
                        lines=[str(t.text) for t in binding.get_text_elements()]
                        self.delivered.emit(row.app_info.display_info.display_name,lines[0] if lines else "", " ".join(lines[1:]))
                    except Exception:continue
            seen=ids
            await asyncio.sleep(.5)
    def close(self):
        self.stop.set()
