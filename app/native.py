import ctypes
import mmap
import os
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
GLOBE_DIR = ROOT / "assets" / "globe"
RUNTIME_WIDTH = 2048
RUNTIME_HEIGHT = 1024
LAYER_NAMES = ("color.mip", "surface.mip")
PF_AVX2_INSTRUCTIONS_AVAILABLE = 40

_library = None


class Color(ctypes.c_float * 3):
    pass


class GlobeParams(ctypes.Structure):
    _fields_ = [
        ("light", Color), ("key_color", Color), ("rim_color", Color), ("sky_ambient", Color),
        ("ground_ambient", Color), ("atmosphere_lit", Color), ("atmosphere_dark", Color),
        ("emissive_color", Color), ("cloud_color", Color), ("warm_color", Color),
        ("warm_amount", ctypes.c_float), ("bump", ctypes.c_float), ("pitch_degrees", ctypes.c_float),
        ("shift", ctypes.c_float), ("cloud_shift", ctypes.c_float), ("exposure", ctypes.c_float),
        ("bloom_threshold", ctypes.c_float), ("bloom_strength", ctypes.c_float), ("grain_amount", ctypes.c_float),
        ("halo_extent", ctypes.c_float), ("grain_seed", ctypes.c_uint32),
    ]


def mip_bytes(width=RUNTIME_WIDTH, height=RUNTIME_HEIGHT):
    total = 0
    while True:
        total += width * height * 4
        if width <= 1 or height <= 1:
            return total
        width, height = width // 2, height // 2


def select_library():
    generic = ctypes.CDLL(str(BIN_DIR / "planet_native.dll"))
    avx2 = BIN_DIR / "planet_native_avx2.dll"
    if not avx2.is_file():
        return generic
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.IsProcessorFeaturePresent.argtypes = [wintypes.DWORD]
    kernel32.IsProcessorFeaturePresent.restype = wintypes.BOOL
    generic.cpu_supports_avx2_fma.argtypes = []
    generic.cpu_supports_avx2_fma.restype = ctypes.c_int
    if kernel32.IsProcessorFeaturePresent(PF_AVX2_INSTRUCTIONS_AVAILABLE) and generic.cpu_supports_avx2_fma():
        return ctypes.CDLL(str(avx2))
    return generic


def load():
    global _library
    if _library is not None:
        return _library
    os.environ.setdefault("OMP_NUM_THREADS", str(os.cpu_count() or 1))
    os.environ.setdefault("OMP_DYNAMIC", "true")
    library = select_library()
    float_pointer = ctypes.POINTER(ctypes.c_float)
    signatures = {
        "globe_bind": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int], None),
        "globe_grade": ([float_pointer, float_pointer], None),
        "globe_prepare": (
            [ctypes.c_int, ctypes.c_float, ctypes.c_double, ctypes.c_int, ctypes.c_int, float_pointer, float_pointer, float_pointer],
            None,
        ),
        "globe_render": (
            [ctypes.POINTER(GlobeParams), float_pointer, float_pointer, float_pointer, ctypes.c_int, ctypes.c_float,
             ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, float_pointer, float_pointer, float_pointer],
            None,
        ),
        "hook_start": ([wintypes.HWND], ctypes.c_int),
        "hook_stop": ([], None),
        "hook_heartbeat": ([], None),
        "hook_set_capture": ([ctypes.c_int], None),
        "hook_alt_held": ([], ctypes.c_int),
        "unlock_foreground": ([], None),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(library, name)
        function.argtypes = arguments
        function.restype = result
    _library = library
    return library


def layers_ready():
    try:
        return all((GLOBE_DIR / name).stat().st_size == mip_bytes() for name in LAYER_NAMES)
    except OSError:
        return False


def map_layers():
    maps = []
    try:
        for name in LAYER_NAMES:
            with open(GLOBE_DIR / name, "rb") as layer:
                mapped = mmap.mmap(layer.fileno(), 0, access=mmap.ACCESS_COPY)
            maps.append(mapped)
            if len(mapped) != mip_bytes():
                raise ValueError(f"{name} has the wrong size")
    except (OSError, ValueError):
        for mapped in maps:
            mapped.close()
        raise
    return maps
