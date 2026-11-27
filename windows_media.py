"""Local Windows media sessions: no Spotify API account required."""
import asyncio
import datetime
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import threading
import time


class LocalMedia:
    def __init__(self):
        self.state = {}
        self.status = 'Starting Windows media detection'
        self.session_count = 0
        self.spotify_sessions = 0
        self.error_type = ''
        self.commands = queue.Queue(maxsize=32)
        self.closed = False
        self.log = logging.getLogger('sakura.windows_media')
        if not self.log.handlers:
            try:
                root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Sakura' / 'state'
                root.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(root / 'media.log', maxBytes=262144, backupCount=2, encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
                self.log.addHandler(handler)
                self.log.setLevel(logging.INFO)
                self.log.propagate = False
            except OSError:
                self.log.addHandler(logging.NullHandler())
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def submit(self, action):
        try:
            self.commands.put_nowait((action, time.monotonic(), self.state.get('key')))
        except queue.Full:
            self.log.warning('Media command queue full')

    def run(self):
        # WinRT async work lives on a dedicated multithreaded COM apartment.
        hr = ctypes.windll.combase.RoInitialize(1)
        if hr not in (0, 1):
            self.log.warning('RoInitialize returned %s', hr)
        try:
            self.run_worker()
        finally:
            if hr in (0, 1):ctypes.windll.combase.RoUninitialize()

    def run_worker(self):
        while not self.closed:
            try:
                asyncio.run(self.loop())
            except Exception as exc:
                self.state = {}
                self.session_count = 0
                self.spotify_sessions = 0
                self.error_type = type(exc).__name__
                self.status = 'Windows media unavailable: ' + type(exc).__name__
                self.log.exception('Media worker failed; reconnecting')
                for _ in range(20):
                    if self.closed:
                        return
                    time.sleep(.25)

    @staticmethod
    async def bounded(operation, seconds=3):
        return await asyncio.wait_for(operation, timeout=seconds)

    async def choose(self, manager):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
        sessions = list(manager.get_sessions() or [])
        self.session_count = len(sessions)
        self.spotify_sessions = 0
        for candidate in sessions:
            try:
                self.spotify_sessions += int('spotify' in (candidate.source_app_user_model_id or '').lower())
            except Exception:
                pass
        try:
            current = manager.get_current_session()
        except Exception:
            current = None
        # Include the current session even if enumeration momentarily omits it.
        if current is not None:
            sessions.insert(0, current)
        ranked = []
        for index, session in enumerate(sessions):
            try:
                app = session.source_app_user_model_id or ''
                try:
                    info = session.get_playback_info()
                    playing = info is not None and info.playback_status == PlaybackStatus.PLAYING
                except Exception:
                    playing = False
                    self.log.debug('Playback status unavailable', exc_info=True)
                ranked.append(((playing, 'spotify' in app.lower(), -index), session, app, playing))
            except Exception:
                self.log.debug('Session inspection failed', exc_info=True)
        ranked.sort(key=lambda row: row[0], reverse=True)
        for _, session, app, playing in ranked:
            try:
                props = await self.bounded(session.try_get_media_properties_async())
                if props and props.title:
                    return session, props, app, playing
            except Exception:
                self.log.warning('Session metadata unavailable', exc_info=True)
        return None

    async def loop(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        from winrt.windows.storage.streams import DataReader
        import winrt.windows.foundation, winrt.windows.foundation.collections
        manager = await self.bounded(Manager.request_async(), 10)
        self.error_type = ''
        self.log.info('Windows media manager connected')
        old = None
        art = b''
        art_attempt = 0.0
        while not self.closed:
            selected = await self.choose(manager)
            if selected is None:
                self.state = {}
                self.status = 'No Windows media session with track information'
                old = None
                art = b''
            else:
                session, props, app, playing = selected
                key = (app, props.title, props.artist)
                changed = key != old
                if changed:
                    old, art, art_attempt = key, b'', 0.0
                # Missing/broken timeline data must never hide otherwise valid metadata.
                position = duration = 0.0
                try:
                    timeline = session.get_timeline_properties()
                    if timeline is not None:
                        position = timeline.position.total_seconds()
                        duration = timeline.end_time.total_seconds()
                        if playing:
                            try:
                                position += max(0, (datetime.datetime.now(datetime.timezone.utc) - timeline.last_updated_time).total_seconds())
                            except (TypeError, AttributeError, OverflowError):
                                pass
                        position = max(0, min(duration, position)) if duration > 0 else max(0, position)
                except Exception:
                    self.log.debug('Timeline unavailable', exc_info=True)
                self.state = dict(title=props.title, artist=props.artist or '', album=props.album_title or '', app=app, playing=playing, art=art, key=key, position=position, duration=duration, sampled=time.monotonic())
                self.status = 'Windows media connected: ' + app
                if not art and props.thumbnail and (changed or time.monotonic() - art_attempt >= 10):
                    art_attempt = time.monotonic()
                    try:
                        stream = await self.bounded(props.thumbnail.open_read_async())
                        try:
                            size = int(stream.size)
                            if 0 < size <= 4000000:
                                reader = DataReader(stream)
                                try:
                                    loaded = await self.bounded(reader.load_async(size))
                                    if loaded == size:
                                        buf = bytearray(size)
                                        reader.read_bytes(buf)
                                        art = bytes(buf)
                                finally:
                                    reader.close()
                        finally:
                            stream.close()
                    except Exception:
                        self.log.debug('Artwork unavailable', exc_info=True)
                    self.state = dict(self.state, art=art)
            for _ in range(8):
                try:
                    action, queued, target = self.commands.get_nowait()
                except queue.Empty:
                    break
                if selected is None or time.monotonic() - queued > 5 or target != self.state.get('key'):
                    continue
                method = {'play': 'try_play_async', 'pause': 'try_pause_async', 'next': 'try_skip_next_async', 'previous': 'try_skip_previous_async'}.get(action)
                if method:
                    try:
                        await self.bounded(getattr(session, method)())
                    except Exception:
                        self.log.warning('Media command failed: %s', action, exc_info=True)
            await asyncio.sleep(.5)
