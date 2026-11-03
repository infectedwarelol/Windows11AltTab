import math
import statistics
import sys
import time
import types
from pathlib import Path

import cairo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import planet_view
from planet_view import CLOSE_SCALE, HALO_EXTENT, MAX_GLOBE_SIZE, OPEN_FADE_SECONDS, PlanetSwitcher

SCREEN_WIDTH = 3840
SCREEN_HEIGHT = 2160
SCALES = (1.0, 1.25, 1.5, 2.0)
WINDOW_COUNT = 9
FRAME_SECONDS = 1 / 60
SETTLE_SECONDS = 1.2
TIMED_FRAMES = 12
FIRST_FRAME_BUDGET_SECONDS = 0.5
FULL_FRAME_BUDGET_SECONDS = 1 / 30
DIRTY_FRAME_BUDGET_SECONDS = 1 / 60


class FakeLibrary:
    def globe_bind(self, *arguments):
        pass

    def globe_grade(self, *arguments):
        pass

    def globe_prepare(self, *arguments):
        pass

    def globe_render(self, *arguments):
        pass


def sample_icon(index):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 256, 256)
    cr = cairo.Context(surface)
    cr.arc(128, 128, 100, 0, 2 * math.pi)
    cr.set_source_rgba((index * 0.37) % 1.0, 0.5, 1.0 - (index * 0.21) % 1.0, 0.8)
    cr.fill()
    surface.flush()
    return surface


def sample_windows():
    return [
        types.SimpleNamespace(
            hwnd=index, title=f"Document {index}", app_name=f"Application {index}", icon=sample_icon(index),
            icon_key=(f"application{index}.exe", f"Application {index}"), exe=f"application{index}.exe",
        )
        for index in range(WINDOW_COUNT)
    ]


class FakeOverlay:
    def __init__(self, scale):
        self.width, self.height = SCREEN_WIDTH, SCREEN_HEIGHT
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SCREEN_WIDTH, SCREEN_HEIGHT)
        self.surface.set_device_scale(scale, scale)
        self.presented_alpha = []


def render(switcher, overlay, scale, redraw):
    if redraw == "present":
        overlay.presented_alpha.append(switcher.fade())
        return
    cr = cairo.Context(overlay.surface)
    if redraw != "full" and switcher.layout is not None:
        left, top, dirty_width, dirty_height = redraw
        cr.rectangle(left, top, dirty_width, dirty_height)
        cr.clip()
    switcher.on_draw(cr, overlay.width / scale, overlay.height / scale, scale)
    del cr
    overlay.surface.flush()
    overlay.presented_alpha.append(switcher.fade())


def run_frame(switcher, overlay, scale, now):
    switcher.on_frame(now)
    redraw, switcher.redraw = switcher.redraw, None
    if redraw is None:
        return None, 0.0
    started = time.perf_counter()
    render(switcher, overlay, scale, redraw)
    return ("dirty" if isinstance(redraw, tuple) else redraw), time.perf_counter() - started


def make_switcher(windows, scale, reduce_motion):
    return PlanetSwitcher(
        windows, lambda: 1, lambda: False, None, FakeLibrary(), scale, reduce_motion, 1.0, lambda text: None, lambda: None,
    )


def check_layout(layout, scale):
    width, height = SCREEN_WIDTH / scale, SCREEN_HEIGHT / scale
    assert math.ceil(width * scale) == SCREEN_WIDTH and math.ceil(height * scale) == SCREEN_HEIGHT
    assert (layout["width"], layout["height"], layout["scale"]) == (width, height, scale)
    radius, cx, cy = layout["radius"], layout["cx"], layout["cy"]
    assert 0 < radius <= MAX_GLOBE_SIZE / 2 and radius <= height * 0.24
    assert cx == width / 2
    extent = radius * HALO_EXTENT
    assert cx - extent >= 0 and cx + extent <= width and cy - extent >= 0 and cy + extent <= height
    assert cy + radius + 52 + 24 <= height
    assert layout["globe_pixels"] % 2 == 0 and layout["globe_pixels"] >= 2 * extent * scale
    left, top, dirty_width, dirty_height = layout["dirty"]
    reach = max(extent, radius + planet_view.MAX_ICON_SIZE * (1 + planet_view.SELECTED_GROWTH)) * CLOSE_SCALE
    assert left <= cx - reach and left + dirty_width >= cx + reach
    assert top <= cy - reach and top + dirty_height >= cy + reach + planet_view.LABEL_SPACE
    device_left, device_top = max(0, math.floor(left * scale)), max(0, math.floor(top * scale))
    device_right = min(SCREEN_WIDTH, math.ceil((left + dirty_width) * scale))
    device_bottom = min(SCREEN_HEIGHT, math.ceil((top + dirty_height) * scale))
    assert device_right > device_left and device_bottom > device_top


def check_fade_not_baked(windows, scale):
    switcher = make_switcher(windows, scale, True)
    overlay = FakeOverlay(scale)
    run_frame(switcher, overlay, scale, 0.0)
    middle_fade = switcher.fade()
    assert 0.0 <= middle_fade < 1.0
    during_fade = bytes(overlay.surface.get_data())
    kinds = []
    now = 0.0
    while now < OPEN_FADE_SECONDS + 0.1:
        now += FRAME_SECONDS
        kinds.append(run_frame(switcher, overlay, scale, now)[0])
    assert "present" in kinds and "full" not in kinds and "dirty" not in kinds
    alphas = overlay.presented_alpha
    assert all(first <= second for first, second in zip(alphas, alphas[1:])) and alphas[-1] == 1.0
    switcher.request_redraw()
    run_frame(switcher, overlay, scale, now)
    assert bytes(overlay.surface.get_data()) == during_fade
    switcher.release()


def measure(windows, scale):
    switcher = make_switcher(windows, scale, False)
    overlay = FakeOverlay(scale)
    timings = {"full": [], "dirty": [], "present": []}
    first_kind, first_seconds = run_frame(switcher, overlay, scale, 0.0)
    assert first_kind == "full"
    check_layout(switcher.layout, scale)
    now = 0.0
    while now < SETTLE_SECONDS:
        now += FRAME_SECONDS
        kind, seconds = run_frame(switcher, overlay, scale, now)
        if kind is not None:
            timings[kind].append(seconds)
    for _ in range(TIMED_FRAMES):
        now += FRAME_SECONDS
        switcher.request_redraw()
        timings["full"].append(run_frame(switcher, overlay, scale, now)[1])
        now += FRAME_SECONDS
        switcher.offset += 1
        kind, seconds = run_frame(switcher, overlay, scale, now)
        if kind == "dirty":
            timings[kind].append(seconds)
    assert timings["dirty"], "selection changes must produce dirty-rect redraws"
    switcher.release()
    return first_seconds, timings


def milliseconds(values):
    return f"{statistics.median(values) * 1000:7.2f}" if values else "    n/a"


def main():
    windows = sample_windows()
    print(f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}, {WINDOW_COUNT} windows, median milliseconds per frame")
    print("scale  first     full    dirty")
    for scale in SCALES:
        check_fade_not_baked(windows, scale)
        first_seconds, timings = measure(windows, scale)
        print(f"{scale:5.2f} {first_seconds * 1000:7.2f}  {milliseconds(timings['full'])}  "
              f"{milliseconds(timings['dirty'])}")
        assert first_seconds <= FIRST_FRAME_BUDGET_SECONDS, f"first frame over budget at {scale}"
        assert statistics.median(timings["full"]) <= FULL_FRAME_BUDGET_SECONDS, f"full frame over budget at {scale}"
        assert statistics.median(timings["dirty"]) <= DIRTY_FRAME_BUDGET_SECONDS, f"dirty frame over budget at {scale}"
    print("selfcheck passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
