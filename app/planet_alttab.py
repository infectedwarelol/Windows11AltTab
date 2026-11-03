import ctypes
import math
import sys
import time
import traceback
from pathlib import Path

import cairo

import native
import win32
from planet_view import PlanetSwitcher

MUTEX_NAME = "Local\\PlanetAltTabSwitcher"
LOG_FILE = Path(__file__).resolve().parent.parent / "planet-alttab.log"
HOOK_MESSAGE = 0x8000 + 1
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_ENDSESSION = 0x0016
WM_DISPLAYCHANGE = 0x007E
WM_DPICHANGED = 0x02E0
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MOUSEWHEEL = 0x020A
WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3
IDLE_WAIT_MS = 500
FRAME_FLOOR_SECONDS = 0.004
FALLBACK_FRAME_MS = 8
HOOK_EVENTS = {
    1: "tab_forward",
    2: "tab_backward",
    3: "alt_released",
    4: "escape",
    5: "confirm",
    6: "previous",
    7: "next",
    8: "wheel",
}


def signed_word(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def log_text(text):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{text}\n")
    except OSError:
        pass


def log_error():
    log_text(traceback.format_exc())


class Session:
    def __init__(self, daemon, windows, backward):
        self.daemon = daemon
        self.windows = windows
        self.tab_presses = 1
        self.alt_up = False
        rect, scale = win32.target_monitor()
        self.scale = scale
        daemon.overlay.place(rect, scale)
        self.switcher = PlanetSwitcher(
            windows, lambda: self.tab_presses, lambda: self.alt_up, self.commit, daemon.library, scale,
            win32.reduce_motion(), win32.text_scale(), daemon.overlay.set_title,
            lambda: daemon.library.hook_set_capture(0), -2 if backward else 0,
        )
        daemon.library.hook_set_capture(1)
        win32.timeBeginPeriod(1)
        self.shown = False

    def commit(self, choice):
        win32.switch_to_window(self.windows[choice], self.daemon.library)

    def refresh_monitor(self):
        overlay = self.daemon.overlay
        rect, scale = win32.window_monitor(overlay.hwnd)
        if rect == (*overlay.origin, overlay.width, overlay.height) and scale == self.scale:
            return
        self.scale = scale
        overlay.place(rect, scale)
        self.switcher.request_redraw()

    def logical(self, lparam):
        return signed_word(lparam) / self.scale, signed_word(lparam >> 16) / self.scale

    def on_event(self, event):
        if event == "tab_forward":
            if self.switcher.closing_at is None:
                self.tab_presses += 1
        elif event == "tab_backward":
            self.switcher.on_key("previous")
        elif event == "alt_released":
            self.alt_up = True
        else:
            self.switcher.on_key(event)

    def frame(self):
        overlay = self.daemon.overlay
        started = time.perf_counter()
        self.switcher.on_frame(started)
        if self.switcher.quit_requested:
            return False
        redraw = self.switcher.redraw
        self.switcher.redraw = None
        if redraw == "present":
            overlay.present(None, self.switcher.fade())
            win32.DwmFlush()
        elif redraw is not None:
            self.render(redraw)
            if not self.shown:
                overlay.show()
                self.shown = True
            win32.DwmFlush()
        if time.perf_counter() - started < FRAME_FLOOR_SECONDS:
            win32.wait_for_messages(FALLBACK_FRAME_MS)
        return True

    def render(self, redraw):
        overlay = self.daemon.overlay
        scale = self.scale
        width, height = overlay.width / scale, overlay.height / scale
        cr = cairo.Context(overlay.surface)
        device_dirty = None
        if redraw != "full" and self.switcher.layout is not None:
            left, top, dirty_width, dirty_height = redraw
            cr.rectangle(left, top, dirty_width, dirty_height)
            cr.clip()
            device_left = max(0, math.floor(left * scale))
            device_top = max(0, math.floor(top * scale))
            device_right = min(overlay.width, math.ceil((left + dirty_width) * scale))
            device_bottom = min(overlay.height, math.ceil((top + dirty_height) * scale))
            if device_right > device_left and device_bottom > device_top:
                device_dirty = (device_left, device_top, device_right, device_bottom)
        self.switcher.on_draw(cr, width, height, scale)
        del cr
        overlay.present(device_dirty, self.switcher.fade())

    def close(self):
        self.daemon.library.hook_set_capture(0)
        win32.timeEndPeriod(1)
        self.daemon.overlay.hide()
        self.daemon.overlay.set_title("Window switcher")
        self.switcher.release()


class Daemon:
    def __init__(self):
        self.library = native.load()
        self.session = None
        self.failed = False
        self.overlay = win32.Overlay(self.window_procedure)
        self.history = win32.FocusHistory()
        self.identities = win32.Identities()
        if self.library.hook_start(self.overlay.hwnd) != 0:
            raise RuntimeError("installing the keyboard hook failed")
        if win32.alt_tab_shows_browser_tabs():
            log_text("MultiTaskingAltTabFilter asks for browser tabs. Windows has no public API for Edge tabs, so only windows are shown.")

    def window_procedure(self, hwnd, message, wparam, lparam):
        try:
            if message == HOOK_MESSAGE:
                self.on_hook(HOOK_EVENTS.get(wparam), lparam)
                return 0
            if message == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            session = self.session
            if message in (WM_DPICHANGED, WM_DISPLAYCHANGE):
                if session is not None:
                    session.refresh_monitor()
                return 0
            if session is not None and session.shown:
                if message == WM_MOUSEMOVE:
                    session.switcher.on_motion(*session.logical(lparam))
                    return 0
                if message in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                    session.switcher.on_click(*session.logical(lparam), message == WM_RBUTTONDOWN)
                    return 0
                if message == WM_MOUSEWHEEL:
                    session.switcher.on_scroll(signed_word(wparam >> 16))
                    return 0
            if message in (WM_CLOSE, WM_DESTROY) or (message == WM_ENDSESSION and wparam):
                win32.PostQuitMessage(0)
                return 0
        except Exception:
            log_error()
            self.failed = True
            win32.PostQuitMessage(1)
            return 0
        return win32.DefWindowProcW(hwnd, message, wparam, lparam)

    def on_hook(self, event, lparam):
        if event is None:
            return
        if event == "wheel":
            if self.session is not None and self.session.shown:
                self.session.switcher.on_scroll(signed_word(lparam))
            return
        if self.session is not None:
            self.session.on_event(event)
            return
        if event in ("tab_forward", "tab_backward"):
            self.start(event == "tab_backward")

    def start(self, backward):
        windows = win32.list_windows(self.overlay.hwnd, self.history, self.identities)
        if len(windows) < 2:
            return
        if not self.library.hook_alt_held():
            win32.switch_to_window(windows[-1 if backward else 1], self.library)
            return
        self.session = Session(self, windows, backward)

    def end_session(self):
        session, self.session = self.session, None
        session.close()

    def run(self):
        try:
            self.loop()
        finally:
            if self.session is not None:
                self.end_session()
            self.library.hook_stop()
            self.history.close()
            self.overlay.destroy()
        if self.failed:
            raise RuntimeError(f"switcher stopped after an error, see {LOG_FILE}")

    def loop(self):
        while True:
            self.library.hook_heartbeat()
            if self.session is None:
                win32.wait_for_messages(IDLE_WAIT_MS)
                if not win32.pump_messages():
                    return
                continue
            if not win32.pump_messages():
                return
            if self.session is not None and not self.session.frame():
                self.end_session()


def main():
    win32.initialize_process()
    mutex = win32.acquire_single_instance(MUTEX_NAME)
    if mutex is None:
        return 0
    try:
        Daemon().run()
    except Exception:
        log_error()
        return 1
    finally:
        win32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
