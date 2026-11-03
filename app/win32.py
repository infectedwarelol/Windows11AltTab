import ctypes
import itertools
import os
import winreg
from ctypes import wintypes

import cairo

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
shcore = ctypes.WinDLL("shcore")
shell32 = ctypes.WinDLL("shell32")
ole32 = ctypes.WinDLL("ole32")
version = ctypes.WinDLL("version")
winmm = ctypes.WinDLL("winmm")

LRESULT = ctypes.c_ssize_t
HRESULT = ctypes.c_long
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD
)

WS_POPUP = 0x80000000
WS_MAXIMIZEBOX = 0x00010000
WS_THICKFRAME = 0x00040000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
OVERLAY_SHOWN_STYLE = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
OVERLAY_HIDDEN_STYLE = OVERLAY_SHOWN_STYLE | WS_EX_TRANSPARENT
GWL_STYLE = -16
GWL_EXSTYLE = -20
GA_ROOTOWNER = 3
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SW_MAXIMIZE = 3
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
HWND_TOPMOST = wintypes.HWND(-1)
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0
DWMWA_CLOAKED = 14
MONITOR_DEFAULTTOPRIMARY = 1
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
PM_REMOVE = 0x0001
QS_ALLINPUT = 0x04FF
WM_QUIT = 0x0012
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SPI_GETCLIENTAREAANIMATION = 0x1042
COINIT_APARTMENTTHREADED = 0x2
GIL_FORSHELL = 0x0002
S_FALSE = 1
DI_MASK = 0x0001
DI_NORMAL = 0x0003
WM_GETICON = 0x007F
ICON_BIG = 1
GCLP_HICON = -14
SMTO_BLOCK = 0x0001
SMTO_ABORTIFHUNG = 0x0002
ICON_MESSAGE_TIMEOUT_MS = 100
SIGDN_NORMALDISPLAY = 0
VT_LPWSTR = 31
IDC_ARROW = 32512
ERROR_ALREADY_EXISTS = 183
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
FRAME_HOST_EXE = "applicationframehost.exe"
CORE_WINDOW_CLASS = "Windows.UI.Core.CoreWindow"
WINDOWED_APPS = {"brave.exe", "firefox.exe", "chromium.exe", "chrome.exe"}
ICON_REQUEST_PIXELS = 256
ICON_EXTRACT_SIZE = (16 << 16) | ICON_REQUEST_PIXELS
INVERTED_BYTES = bytes(255 - value for value in range(256))
ALT_TAB_FILTER_WINDOWS_ONLY = 3
IDENTITY_CACHE_LIMIT = 200


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        ole32.CLSIDFromString(text, ctypes.byref(self))


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort), ("reserved1", ctypes.c_ushort), ("reserved2", ctypes.c_ushort),
        ("reserved3", ctypes.c_ushort), ("value", ctypes.c_void_p), ("padding", ctypes.c_void_p),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class UPDATELAYEREDWINDOWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hdcDst", wintypes.HDC), ("pptDst", ctypes.POINTER(wintypes.POINT)),
        ("psize", ctypes.POINTER(wintypes.SIZE)), ("hdcSrc", wintypes.HDC), ("pptSrc", ctypes.POINTER(wintypes.POINT)),
        ("crKey", wintypes.DWORD), ("pblend", ctypes.POINTER(BLENDFUNCTION)), ("dwFlags", wintypes.DWORD),
        ("prcDirty", ctypes.POINTER(wintypes.RECT)),
    ]


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


RegisterClassExW = bind(user32, "RegisterClassExW", wintypes.ATOM, ctypes.POINTER(WNDCLASSEXW))
CreateWindowExW = bind(
    user32, "CreateWindowExW", wintypes.HWND, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
)
DestroyWindow = bind(user32, "DestroyWindow", wintypes.BOOL, wintypes.HWND)
DefWindowProcW = bind(user32, "DefWindowProcW", LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
LoadCursorW = bind(user32, "LoadCursorW", wintypes.HANDLE, wintypes.HINSTANCE, ctypes.c_void_p)
GetModuleHandleW = bind(kernel32, "GetModuleHandleW", wintypes.HMODULE, wintypes.LPCWSTR)
ShowWindow = bind(user32, "ShowWindow", wintypes.BOOL, wintypes.HWND, ctypes.c_int)
ShowWindowAsync = bind(user32, "ShowWindowAsync", wintypes.BOOL, wintypes.HWND, ctypes.c_int)
SetWindowPos = bind(
    user32, "SetWindowPos", wintypes.BOOL, wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.UINT,
)
GetWindowLongPtrW = bind(user32, "GetWindowLongPtrW", ctypes.c_ssize_t, wintypes.HWND, ctypes.c_int)
SetWindowLongPtrW = bind(user32, "SetWindowLongPtrW", ctypes.c_ssize_t, wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
SetWindowTextW = bind(user32, "SetWindowTextW", wintypes.BOOL, wintypes.HWND, wintypes.LPCWSTR)
EnumWindows = bind(user32, "EnumWindows", wintypes.BOOL, ENUMPROC, wintypes.LPARAM)
EnumChildWindows = bind(user32, "EnumChildWindows", wintypes.BOOL, wintypes.HWND, ENUMPROC, wintypes.LPARAM)
IsWindow = bind(user32, "IsWindow", wintypes.BOOL, wintypes.HWND)
IsWindowVisible = bind(user32, "IsWindowVisible", wintypes.BOOL, wintypes.HWND)
IsIconic = bind(user32, "IsIconic", wintypes.BOOL, wintypes.HWND)
IsZoomed = bind(user32, "IsZoomed", wintypes.BOOL, wintypes.HWND)
GetAncestor = bind(user32, "GetAncestor", wintypes.HWND, wintypes.HWND, wintypes.UINT)
GetLastActivePopup = bind(user32, "GetLastActivePopup", wintypes.HWND, wintypes.HWND)
GetClassNameW = bind(user32, "GetClassNameW", ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
GetWindowTextLengthW = bind(user32, "GetWindowTextLengthW", ctypes.c_int, wintypes.HWND)
GetWindowTextW = bind(user32, "GetWindowTextW", ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
GetWindowThreadProcessId = bind(user32, "GetWindowThreadProcessId", wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
GetForegroundWindow = bind(user32, "GetForegroundWindow", wintypes.HWND)
SetForegroundWindow = bind(user32, "SetForegroundWindow", wintypes.BOOL, wintypes.HWND)
SwitchToThisWindow = bind(user32, "SwitchToThisWindow", None, wintypes.HWND, wintypes.BOOL)
BringWindowToTop = bind(user32, "BringWindowToTop", wintypes.BOOL, wintypes.HWND)
AttachThreadInput = bind(user32, "AttachThreadInput", wintypes.BOOL, wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
GetCurrentThreadId = bind(kernel32, "GetCurrentThreadId", wintypes.DWORD)
MonitorFromWindow = bind(user32, "MonitorFromWindow", wintypes.HMONITOR, wintypes.HWND, wintypes.DWORD)
GetMonitorInfoW = bind(user32, "GetMonitorInfoW", wintypes.BOOL, wintypes.HMONITOR, ctypes.POINTER(MONITORINFO))
GetDpiForMonitor = bind(
    shcore, "GetDpiForMonitor", HRESULT, wintypes.HMONITOR, ctypes.c_int, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)
)
SetProcessDpiAwarenessContext = bind(user32, "SetProcessDpiAwarenessContext", wintypes.BOOL, ctypes.c_ssize_t)
SystemParametersInfoW = bind(user32, "SystemParametersInfoW", wintypes.BOOL, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT)
DwmGetWindowAttribute = bind(dwmapi, "DwmGetWindowAttribute", HRESULT, wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
DwmFlush = bind(dwmapi, "DwmFlush", HRESULT)
GetDC = bind(user32, "GetDC", wintypes.HDC, wintypes.HWND)
ReleaseDC = bind(user32, "ReleaseDC", ctypes.c_int, wintypes.HWND, wintypes.HDC)
CreateCompatibleDC = bind(gdi32, "CreateCompatibleDC", wintypes.HDC, wintypes.HDC)
DeleteDC = bind(gdi32, "DeleteDC", wintypes.BOOL, wintypes.HDC)
CreateDIBSection = bind(
    gdi32, "CreateDIBSection", wintypes.HBITMAP, wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
)
SelectObject = bind(gdi32, "SelectObject", wintypes.HGDIOBJ, wintypes.HDC, wintypes.HGDIOBJ)
DeleteObject = bind(gdi32, "DeleteObject", wintypes.BOOL, wintypes.HGDIOBJ)
DrawIconEx = bind(
    user32, "DrawIconEx", wintypes.BOOL, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON, ctypes.c_int, ctypes.c_int,
    wintypes.UINT, wintypes.HBRUSH, wintypes.UINT,
)
DestroyIcon = bind(user32, "DestroyIcon", wintypes.BOOL, wintypes.HICON)
SendMessageTimeoutW = bind(
    user32, "SendMessageTimeoutW", LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT,
    wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
)
GetClassLongPtrW = bind(user32, "GetClassLongPtrW", ctypes.c_size_t, wintypes.HWND, ctypes.c_int)
GdiFlush = bind(gdi32, "GdiFlush", wintypes.BOOL)
UpdateLayeredWindowIndirect = bind(
    user32, "UpdateLayeredWindowIndirect", wintypes.BOOL, wintypes.HWND, ctypes.POINTER(UPDATELAYEREDWINDOWINFO)
)
PeekMessageW = bind(
    user32, "PeekMessageW", wintypes.BOOL, ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT
)
TranslateMessage = bind(user32, "TranslateMessage", wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
DispatchMessageW = bind(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(wintypes.MSG))
PostQuitMessage = bind(user32, "PostQuitMessage", None, ctypes.c_int)
MsgWaitForMultipleObjects = bind(
    user32, "MsgWaitForMultipleObjects", wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
    wintypes.DWORD,
)
SetWinEventHook = bind(
    user32, "SetWinEventHook", wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENTPROC,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
)
UnhookWinEvent = bind(user32, "UnhookWinEvent", wintypes.BOOL, wintypes.HANDLE)
OpenProcess = bind(kernel32, "OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
CloseHandle = bind(kernel32, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)
QueryFullProcessImageNameW = bind(
    kernel32, "QueryFullProcessImageNameW", wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
GetApplicationUserModelId = bind(
    kernel32, "GetApplicationUserModelId", ctypes.c_long, wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR
)
CreateMutexW = bind(kernel32, "CreateMutexW", wintypes.HANDLE, ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
CoInitializeEx = bind(ole32, "CoInitializeEx", HRESULT, ctypes.c_void_p, wintypes.DWORD)
CoTaskMemFree = bind(ole32, "CoTaskMemFree", None, ctypes.c_void_p)
PropVariantClear = bind(ole32, "PropVariantClear", HRESULT, ctypes.POINTER(PROPVARIANT))
SHCreateItemFromParsingName = bind(
    shell32, "SHCreateItemFromParsingName", HRESULT, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID),
    ctypes.POINTER(ctypes.c_void_p),
)
SHDefExtractIconW = bind(
    shell32, "SHDefExtractIconW", HRESULT, wintypes.LPCWSTR, ctypes.c_int, wintypes.UINT, ctypes.POINTER(wintypes.HICON),
    ctypes.POINTER(wintypes.HICON), wintypes.UINT,
)
SHGetPropertyStoreForWindow = bind(
    shell32, "SHGetPropertyStoreForWindow", HRESULT, wintypes.HWND, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)
)
GetFileVersionInfoSizeW = bind(version, "GetFileVersionInfoSizeW", wintypes.DWORD, wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
GetFileVersionInfoW = bind(version, "GetFileVersionInfoW", wintypes.BOOL, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
VerQueryValueW = bind(
    version, "VerQueryValueW", wintypes.BOOL, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(wintypes.UINT),
)
timeBeginPeriod = bind(winmm, "timeBeginPeriod", wintypes.UINT, wintypes.UINT)
timeEndPeriod = bind(winmm, "timeEndPeriod", wintypes.UINT, wintypes.UINT)

IID_IShellItem = GUID("{43826d1e-e718-42ee-bc55-a1e261c37bfe}")
IID_IExtractIconW = GUID("{000214FA-0000-0000-C000-000000000046}")
BHID_SFUIObject = GUID("{3981e225-f559-11d3-8e3a-00c04f6837d5}")
IID_IPropertyStore = GUID("{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}")
PKEY_AppUserModel_ID = PROPERTYKEY(GUID("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"), 5)


def com_call(pointer, index, result, arguments, *values):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    method = ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *arguments)(vtable[index])
    return method(pointer, *values)


def com_release(pointer):
    if pointer:
        com_call(pointer, 2, wintypes.ULONG, ())


def initialize_process():
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    CoInitializeEx(None, COINIT_APARTMENTTHREADED)


def acquire_single_instance(name):
    handle = CreateMutexW(None, True, name)
    if not handle or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def reduce_motion():
    enabled = wintypes.BOOL(True)
    if not SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0):
        return False
    return not enabled.value


def text_scale():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Accessibility") as key:
            value, _ = winreg.QueryValueEx(key, "TextScaleFactor")
        return max(1.0, min(2.25, int(value) / 100))
    except (OSError, ValueError, TypeError):
        return 1.0


def alt_tab_shows_browser_tabs():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced") as key:
            value, _ = winreg.QueryValueEx(key, "MultiTaskingAltTabFilter")
        return int(value) != ALT_TAB_FILTER_WINDOWS_ONLY
    except (OSError, ValueError, TypeError):
        return False


def target_monitor():
    return monitor_geometry(MonitorFromWindow(GetForegroundWindow(), MONITOR_DEFAULTTOPRIMARY))


def window_monitor(hwnd):
    return monitor_geometry(MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST))


def monitor_geometry(monitor):
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    GetMonitorInfoW(monitor, ctypes.byref(info))
    dpi_x, dpi_y = wintypes.UINT(96), wintypes.UINT(96)
    if GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) != 0:
        dpi_x.value = 96
    rect = info.rcMonitor
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top), max(1.0, dpi_x.value / 96)


def pump_messages():
    message = wintypes.MSG()
    while PeekMessageW(ctypes.byref(message), None, 0, 0, PM_REMOVE):
        if message.message == WM_QUIT:
            return False
        TranslateMessage(ctypes.byref(message))
        DispatchMessageW(ctypes.byref(message))
    return True


def wait_for_messages(milliseconds):
    MsgWaitForMultipleObjects(0, None, False, max(0, int(milliseconds)), QS_ALLINPUT)


class Overlay:
    CLASS_NAME = "PlanetAltTabOverlay"

    def __init__(self, window_procedure):
        self.procedure = WNDPROC(window_procedure)
        instance = GetModuleHandleW(None)
        window_class = WNDCLASSEXW(
            cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=self.procedure, hInstance=instance,
            hCursor=LoadCursorW(None, ctypes.c_void_p(IDC_ARROW)), lpszClassName=self.CLASS_NAME,
        )
        if not RegisterClassExW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = CreateWindowExW(
            OVERLAY_HIDDEN_STYLE, self.CLASS_NAME, "Window switcher", WS_POPUP, 0, 0, 1, 1, None, None, instance, None
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.origin = (0, 0)
        self.width = self.height = 0
        self.memory_dc = None
        self.bitmap = None
        self.previous_bitmap = None
        self.pixels = None
        self.surface = None
        self.visible = False
        self.presented_alpha = None

    def place(self, rect, scale):
        left, top, width, height = rect
        self.origin = (left, top)
        if (width, height) != (self.width, self.height) or self.surface is None:
            self.release_buffer()
            self.allocate_buffer(width, height)
        self.surface.set_device_scale(scale, scale)
        SetWindowPos(self.hwnd, HWND_TOPMOST, left, top, width, height, SWP_NOACTIVATE)

    def allocate_buffer(self, width, height):
        screen = GetDC(None)
        self.memory_dc = CreateCompatibleDC(screen)
        ReleaseDC(None, screen)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        bits = ctypes.c_void_p()
        self.bitmap = CreateDIBSection(self.memory_dc, ctypes.byref(info), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        if not self.bitmap or not bits.value:
            DeleteDC(self.memory_dc)
            self.memory_dc = None
            raise ctypes.WinError(ctypes.get_last_error())
        self.previous_bitmap = SelectObject(self.memory_dc, self.bitmap)
        self.pixels = (ctypes.c_char * (width * height * 4)).from_address(bits.value)
        self.surface = cairo.ImageSurface.create_for_data(self.pixels, cairo.FORMAT_ARGB32, width, height, width * 4)
        self.width, self.height = width, height

    def release_buffer(self):
        if self.surface is not None:
            self.surface.finish()
            self.surface = None
        self.pixels = None
        if self.memory_dc:
            SelectObject(self.memory_dc, self.previous_bitmap)
            DeleteDC(self.memory_dc)
            self.memory_dc = None
        if self.bitmap:
            DeleteObject(self.bitmap)
            self.bitmap = None
        self.width = self.height = 0

    def present(self, dirty=None, alpha=1.0):
        self.surface.flush()
        GdiFlush()
        destination = wintypes.POINT(*self.origin)
        size = wintypes.SIZE(self.width, self.height)
        source = wintypes.POINT(0, 0)
        constant_alpha = max(0, min(255, round(alpha * 255)))
        if constant_alpha != self.presented_alpha:
            dirty = None
        self.presented_alpha = constant_alpha
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, constant_alpha, AC_SRC_ALPHA)
        info = UPDATELAYEREDWINDOWINFO(
            cbSize=ctypes.sizeof(UPDATELAYEREDWINDOWINFO), pptDst=ctypes.pointer(destination), psize=ctypes.pointer(size),
            hdcSrc=self.memory_dc, pptSrc=ctypes.pointer(source), pblend=ctypes.pointer(blend), dwFlags=ULW_ALPHA,
        )
        if dirty is not None:
            info.prcDirty = ctypes.pointer(wintypes.RECT(*dirty))
            if UpdateLayeredWindowIndirect(self.hwnd, ctypes.byref(info)):
                return
            info.prcDirty = None
        UpdateLayeredWindowIndirect(self.hwnd, ctypes.byref(info))

    def set_title(self, text):
        SetWindowTextW(self.hwnd, text)

    def show(self):
        SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, OVERLAY_SHOWN_STYLE)
        SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self.visible = True

    def hide(self):
        ShowWindow(self.hwnd, SW_HIDE)
        self.presented_alpha = None
        SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, OVERLAY_HIDDEN_STYLE)
        self.visible = False

    def destroy(self):
        self.hide()
        self.release_buffer()
        DestroyWindow(self.hwnd)


class FocusHistory:
    def __init__(self):
        self.counter = itertools.count(1)
        self.stamps = {}
        self.callback = WINEVENTPROC(self.on_foreground)
        self.hook = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, self.callback, 0, 0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        self.touch(GetForegroundWindow())

    def on_foreground(self, _hook, _event, hwnd, object_id, _child, _thread, _time):
        if object_id == 0:
            self.touch(hwnd)

    def touch(self, hwnd):
        if hwnd:
            self.stamps[hwnd] = next(self.counter)

    def prune(self, alive):
        self.stamps = {hwnd: stamp for hwnd, stamp in self.stamps.items() if hwnd in alive}

    def close(self):
        if self.hook:
            UnhookWinEvent(self.hook)
            self.hook = None


class Window:
    __slots__ = ("hwnd", "title", "app_name", "icon", "icon_key", "exe")

    def __init__(self, hwnd, title, app_name, icon, icon_key, exe):
        self.hwnd = hwnd
        self.title = title
        self.app_name = app_name
        self.icon = icon
        self.icon_key = icon_key
        self.exe = exe


def window_text(hwnd):
    length = GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def class_name(hwnd):
    buffer = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def is_cloaked(hwnd):
    cloaked = wintypes.DWORD(0)
    if DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0:
        return False
    return cloaked.value != 0


def is_switchable(hwnd, own_hwnd):
    if hwnd == own_hwnd or not IsWindowVisible(hwnd) or is_cloaked(hwnd):
        return False
    if class_name(hwnd) in SHELL_CLASSES or GetWindowTextLengthW(hwnd) == 0:
        return False
    extended = GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    if extended & WS_EX_APPWINDOW:
        return True
    if extended & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE):
        return False
    walk = GetAncestor(hwnd, GA_ROOTOWNER)
    while walk:
        candidate = GetLastActivePopup(walk)
        if candidate == walk or IsWindowVisible(candidate):
            break
        walk = candidate
    return walk == hwnd


def top_level_windows():
    handles = []

    def collect(hwnd, _parameter):
        handles.append(hwnd)
        return True

    EnumWindows(ENUMPROC(collect), 0)
    return handles


def window_process_id(hwnd):
    process_id = wintypes.DWORD(0)
    GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return process_id.value


def frame_host_child_process(hwnd, frame_process):
    found = []

    def inspect(child, _parameter):
        if class_name(child) == CORE_WINDOW_CLASS:
            process_id = window_process_id(child)
            if process_id and process_id != frame_process:
                found.append(process_id)
                return False
        return True

    EnumChildWindows(hwnd, ENUMPROC(inspect), 0)
    return found[0] if found else None


def process_details(process_id):
    handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return "", None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        exe = buffer.value if QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else ""
        length = wintypes.UINT(0)
        GetApplicationUserModelId(handle, ctypes.byref(length), None)
        model_id = None
        if 0 < length.value < 1024:
            model_buffer = ctypes.create_unicode_buffer(length.value)
            if GetApplicationUserModelId(handle, ctypes.byref(length), model_buffer) == 0:
                model_id = model_buffer.value or None
        return exe, model_id
    finally:
        CloseHandle(handle)


def window_model_id(hwnd):
    store = ctypes.c_void_p()
    if SHGetPropertyStoreForWindow(hwnd, ctypes.byref(IID_IPropertyStore), ctypes.byref(store)) != 0 or not store:
        return None
    value = PROPVARIANT()
    try:
        result = com_call(
            store, 5, HRESULT, (ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT)),
            ctypes.byref(PKEY_AppUserModel_ID), ctypes.byref(value),
        )
        if result != 0 or value.vt != VT_LPWSTR or not value.value:
            return None
        return ctypes.wstring_at(value.value) or None
    finally:
        PropVariantClear(ctypes.byref(value))
        com_release(store)


def file_description(exe):
    if not exe:
        return None
    handle = wintypes.DWORD(0)
    size = GetFileVersionInfoSizeW(exe, ctypes.byref(handle))
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not GetFileVersionInfoW(exe, 0, size, data):
        return None
    pointer, length = ctypes.c_void_p(), wintypes.UINT(0)
    if not VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)) or length.value < 4:
        return None
    language, codepage = ctypes.cast(pointer, ctypes.POINTER(wintypes.WORD * 2)).contents
    query = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\FileDescription"
    if not VerQueryValueW(data, query, ctypes.byref(pointer), ctypes.byref(length)) or length.value <= 1:
        return None
    return ctypes.wstring_at(pointer, length.value).rstrip("\0").strip() or None


def shell_item(parsing_name):
    item = ctypes.c_void_p()
    if SHCreateItemFromParsingName(parsing_name, None, ctypes.byref(IID_IShellItem), ctypes.byref(item)) != 0 or not item:
        return None
    return item


def shell_item_name(item):
    name = ctypes.c_void_p()
    if com_call(item, 5, HRESULT, (ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)), SIGDN_NORMALDISPLAY, ctypes.byref(name)) != 0:
        return None
    try:
        return ctypes.wstring_at(name.value) if name.value else None
    finally:
        CoTaskMemFree(name)


def draw_icon_pixels(icon, flags, fill):
    size = ICON_REQUEST_PIXELS
    screen = GetDC(None)
    memory_dc = CreateCompatibleDC(screen)
    ReleaseDC(None, screen)
    if not memory_dc:
        return None
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = size
    info.bmiHeader.biHeight = -size
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    bitmap = CreateDIBSection(memory_dc, ctypes.byref(info), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
    if not bitmap or not bits.value:
        DeleteDC(memory_dc)
        return None
    previous = SelectObject(memory_dc, bitmap)
    try:
        ctypes.memset(bits.value, fill, size * size * 4)
        if not DrawIconEx(memory_dc, 0, 0, icon, size, size, 0, None, flags):
            return None
        GdiFlush()
        return bytearray(ctypes.string_at(bits.value, size * size * 4))
    finally:
        SelectObject(memory_dc, previous)
        DeleteObject(bitmap)
        DeleteDC(memory_dc)


def icon_surface(icon):
    size = ICON_REQUEST_PIXELS
    color = draw_icon_pixels(icon, DI_NORMAL, 0)
    if color is None:
        return None
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    if any(color[3::4]):
        stride = surface.get_stride()
        data = surface.get_data()
        for row in range(size):
            data[row * stride:row * stride + size * 4] = color[row * size * 4:(row + 1) * size * 4]
        del data
        surface.mark_dirty()
        return surface
    mask = draw_icon_pixels(icon, DI_MASK, 0xFF)
    if mask is None:
        return None
    alpha_stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_A8, size)
    alpha = bytearray(alpha_stride * size)
    opacity = mask[0::4].translate(INVERTED_BYTES)
    for row in range(size):
        alpha[row * alpha_stride:row * alpha_stride + size] = opacity[row * size:(row + 1) * size]
    color_surface = cairo.ImageSurface.create_for_data(color, cairo.FORMAT_RGB24, size, size, size * 4)
    alpha_surface = cairo.ImageSurface.create_for_data(alpha, cairo.FORMAT_A8, size, size, alpha_stride)
    cr = cairo.Context(surface)
    cr.set_source_surface(color_surface, 0, 0)
    cr.mask_surface(alpha_surface, 0, 0)
    del cr
    surface.flush()
    color_surface.finish()
    alpha_surface.finish()
    return surface


def owned_icon_surface(icon):
    try:
        return icon_surface(icon)
    finally:
        DestroyIcon(icon)


def extract_file_icon(path, index):
    large = wintypes.HICON()
    if SHDefExtractIconW(path, index, 0, ctypes.byref(large), None, ICON_REQUEST_PIXELS) != 0 or not large:
        return None
    return owned_icon_surface(large)


def shell_item_icon(item):
    extractor = ctypes.c_void_p()
    if com_call(
        item, 3, HRESULT, (ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)),
        None, ctypes.byref(BHID_SFUIObject), ctypes.byref(IID_IExtractIconW), ctypes.byref(extractor),
    ) != 0 or not extractor:
        return None
    try:
        location = ctypes.create_unicode_buffer(32768)
        index, flags = ctypes.c_int(0), wintypes.UINT(0)
        if com_call(
            extractor, 3, HRESULT,
            (wintypes.UINT, wintypes.LPWSTR, wintypes.UINT, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(wintypes.UINT)),
            GIL_FORSHELL, location, len(location), ctypes.byref(index), ctypes.byref(flags),
        ) != 0:
            return None
        large, small = wintypes.HICON(), wintypes.HICON()
        result = com_call(
            extractor, 4, HRESULT,
            (wintypes.LPCWSTR, wintypes.UINT, ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT),
            location.value, index.value & 0xFFFFFFFF, ctypes.byref(large), ctypes.byref(small), ICON_EXTRACT_SIZE,
        )
        if small:
            DestroyIcon(small)
        if result == 0 and large:
            return owned_icon_surface(large)
        if large:
            DestroyIcon(large)
        if result == S_FALSE and location.value:
            return extract_file_icon(location.value, index.value)
        return None
    finally:
        com_release(extractor)


def window_icon(hwnd):
    icon = ctypes.c_size_t(0)
    if not SendMessageTimeoutW(
        hwnd, WM_GETICON, ICON_BIG, 0, SMTO_ABORTIFHUNG | SMTO_BLOCK, ICON_MESSAGE_TIMEOUT_MS, ctypes.byref(icon),
    ) or not icon.value:
        icon.value = GetClassLongPtrW(hwnd, GCLP_HICON)
    return icon_surface(wintypes.HICON(icon.value)) if icon.value else None


class Identities:
    def __init__(self):
        self.cache = {}

    def resolve(self, hwnd):
        process_id = window_process_id(hwnd)
        exe, process_model_id = process_details(process_id)
        if os.path.basename(exe).lower() == FRAME_HOST_EXE:
            child = frame_host_child_process(hwnd, process_id)
            if child:
                exe, process_model_id = process_details(child)
        model_ids = [model_id for model_id in (window_model_id(hwnd), process_model_id) if model_id]
        key = (exe.lower(), tuple(model_ids))
        cached = self.cache.get(key)
        if cached is None:
            cached = self.load(exe, model_ids, hwnd)
            if len(self.cache) >= IDENTITY_CACHE_LIMIT:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = cached
        return exe, cached

    def load(self, exe, model_ids, hwnd):
        for model_id in model_ids:
            item = shell_item(f"shell:AppsFolder\\{model_id}")
            if item:
                try:
                    name = shell_item_name(item)
                    icon = shell_item_icon(item)
                finally:
                    com_release(item)
                return name, icon or window_icon(hwnd)
        icon = None
        item = shell_item(exe) if exe else None
        if item:
            try:
                icon = shell_item_icon(item)
            finally:
                com_release(item)
        if icon is None and exe:
            icon = extract_file_icon(exe, 0)
        return file_description(exe), icon or window_icon(hwnd)


def pretty_exe_name(exe):
    stem = os.path.splitext(os.path.basename(exe or ""))[0].replace("-", " ").replace("_", " ").strip()
    return (stem.title() if stem.islower() else stem) or "App"


def list_windows(own_hwnd, history, identities):
    handles = [hwnd for hwnd in top_level_windows() if is_switchable(hwnd, own_hwnd)]
    history.prune(set(handles))
    order = {hwnd: index for index, hwnd in enumerate(handles)}
    handles.sort(key=lambda hwnd: (0, -history.stamps[hwnd]) if hwnd in history.stamps else (1, order[hwnd]))
    windows = []
    for hwnd in handles:
        exe, (name, icon) = identities.resolve(hwnd)
        icon_key = (exe.lower(), name)
        windows.append(Window(hwnd, window_text(hwnd), name or pretty_exe_name(exe), icon, icon_key, exe))
    return windows


def attach_input(current_thread, threads):
    attached = []
    for thread in dict.fromkeys(threads):
        if thread and thread != current_thread and AttachThreadInput(current_thread, thread, True):
            attached.append(thread)
    return attached


def detach_input(current_thread, attached):
    for thread in attached:
        AttachThreadInput(current_thread, thread, False)


def raise_window(hwnd, threads):
    current_thread = GetCurrentThreadId()
    attached = attach_input(current_thread, threads)
    try:
        BringWindowToTop(hwnd)
        SetForegroundWindow(hwnd)
    finally:
        detach_input(current_thread, attached)
    return GetForegroundWindow() == hwnd


def switch_to_window(window, native):
    hwnd = window.hwnd
    if not IsWindow(hwnd):
        return
    if IsIconic(hwnd):
        ShowWindowAsync(hwnd, SW_RESTORE)
    native.unlock_foreground()
    if not raise_window(hwnd, (GetWindowThreadProcessId(GetForegroundWindow(), None),)):
        threads = (GetWindowThreadProcessId(GetForegroundWindow(), None), GetWindowThreadProcessId(hwnd, None))
        if not raise_window(hwnd, threads):
            SwitchToThisWindow(hwnd, True)
    if GetForegroundWindow() != hwnd:
        return
    style = GetWindowLongPtrW(hwnd, GWL_STYLE)
    resizable = style & WS_MAXIMIZEBOX and style & WS_THICKFRAME
    if resizable and not IsZoomed(hwnd) and os.path.basename(window.exe).lower() not in WINDOWED_APPS:
        ShowWindowAsync(hwnd, SW_MAXIMIZE)
