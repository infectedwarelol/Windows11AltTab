import ctypes
import math
import random
import time

import cairo

import native
from celestial import Sky, mix

COLORS = {
    "background": "#1a0f24",
    "foreground": "#f3e8ff",
    "surface": "#2e1640",
    "primary": "#6b21a8",
    "secondary": "#8b3fc7",
    "accent": "#d06bf0",
}
ICON_PIXELS = 192
ICON_CACHE_LIMIT = 200
MAX_ICON_SIZE = 68
MIN_ICON_SIZE = 40
SELECTED_GROWTH = 0.3
APP_SPACING_DEGREES = 40.0
APP_LATITUDES = (14, -4, 28, 6, 22, -10, 16, 0, 32, 10, 24, -2)
GLOBE_PITCH = 14.0
MAX_GLOBE_SIZE = 480
LABEL_SPACE = 110
HALO_EXTENT = 1.16
DAWN_ORANGE = (1.0, 0.58, 0.3)
WHITE = (1.0, 1.0, 1.0)
BLACK = (0.0, 0.0, 0.0)
CITY_WARMTH = (1.0, 0.78, 0.5)
FONT = "Segoe UI"
YAW_FREQUENCY = 11.0
SCALE_FREQUENCY = 16.0
OPEN_FREQUENCY = 15.0
MAX_OVERSHOOT_DEGREES = 2.0
MAX_FRAME_SECONDS = 0.05
OPEN_SCALE = 0.92
OPEN_FADE_SECONDS = 0.18
CLOSE_SCALE = 1.04
CLOSE_SECONDS = 0.12
IDLE_DELAY_SECONDS = 1.5
IDLE_DEGREES_PER_SECOND = 2.0
CLOUD_SPEED_RATIO = 1.15
CLOUD_DRIFT_DEGREES_PER_SECOND = 0.8
REDRAW_PIXELS = 0.15
BACKDROP_ALPHA = 0.42
VIGNETTE_ALPHA = 0.35
STAR_LAYERS = (
    (512, 150, 0.35, 0.7, 0.45, 0.02, 0),
    (640, 70, 0.5, 1.0, 0.65, 0.05, 2),
    (768, 26, 0.8, 1.5, 0.9, 0.1, 4),
)
NEBULA_SEED = 11
NEBULA_DOWNSCALE = 8
STAR_SEED = 23
EXPOSURE = 1.0
BLOOM_THRESHOLD = 0.35
BLOOM_STRENGTH = 0.35
GRAIN_AMOUNT = 1.4
LIGHTING = {
    "day": ((1.0, 0.96, 0.9), 1.6, 0.35),
    "dawn": ((1.0, 0.76, 0.52), 1.5, 1.0),
    "dusk": ((1.0, 0.72, 0.48), 1.5, 1.0),
    "night": ((0.72, 0.8, 1.0), 1.0, 0.5),
}
SCROLL_STEP = 60

icon_sprite_cache = {}


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[index:index + 2], 16) / 255 for index in (0, 2, 4))


def linear(color):
    return tuple(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in color)


def scaled(color, amount):
    return tuple(value * amount for value in color)


def luminance(color):
    red, green, blue = linear(color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def squircle_path(cr, x, y, size):
    radius = size * 0.2237
    cr.new_sub_path()
    cr.arc(x + size - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + size - radius, y + size - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + size - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


def wrap_degrees(value):
    return (value + 180) % 360 - 180


def spring(error, velocity, frequency, elapsed):
    decay = math.exp(-frequency * elapsed)
    pull = velocity + frequency * error
    return (error + pull * elapsed) * decay, (velocity - frequency * pull * elapsed) * decay


def ease_out(progress):
    return 1 - (1 - progress) ** 3


def device_surface(width, height, scale, image_format=cairo.FORMAT_ARGB32):
    surface = cairo.ImageSurface(image_format, max(1, int(math.ceil(width * scale))), max(1, int(math.ceil(height * scale))))
    surface.set_device_scale(scale, scale)
    return surface


def paint_alpha(cr, alpha):
    if alpha >= 0.999:
        cr.paint()
    else:
        cr.paint_with_alpha(alpha)


class GlobeRenderer:
    def __init__(self, library):
        self.ready = False
        self.size = 0
        self.maps = []
        self.buffers = []
        self.library = library
        self.params = native.GlobeParams()
        if library is not None and native.layers_ready():
            self.load()

    def load(self):
        try:
            self.maps = native.map_layers()
        except (OSError, ValueError):
            return False
        self.buffers = [(ctypes.c_char * len(mapped)).from_buffer(mapped) for mapped in self.maps]
        self.library.globe_bind(
            ctypes.addressof(self.buffers[0]), ctypes.addressof(self.buffers[1]), native.RUNTIME_WIDTH, native.RUNTIME_HEIGHT,
        )
        self.ready = True
        return True

    def set_scene(self, rgb, sky):
        key, intensity, warmth = LIGHTING.get(sky.time_of_day, LIGHTING["day"])
        background, foreground = rgb["background"], rgb["foreground"]
        primary, accent = rgb["primary"], rgb["accent"]
        params = self.params
        params.light[:] = sky.light
        params.key_color[:] = scaled(key, intensity)
        params.rim_color[:] = scaled(linear(mix(accent, WHITE, 0.4)), 0.9)
        params.sky_ambient[:] = scaled(linear(mix(background, accent, 0.35)), 0.35)
        params.ground_ambient[:] = scaled(linear(background), 0.12)
        params.atmosphere_lit[:] = linear(mix(accent, WHITE, 0.15))
        params.atmosphere_dark[:] = scaled(linear(mix(background, primary, 0.5)), 0.6)
        params.emissive_color[:] = scaled(linear(mix(accent, CITY_WARMTH, 0.6)), 1.6)
        params.cloud_color[:] = scaled(linear(mix(foreground, WHITE, 0.5)), 0.85)
        params.warm_color[:] = linear(DAWN_ORANGE)
        params.warm_amount = warmth
        params.bump = 0.35 + 0.65 * min(1.0, abs(luminance(primary) - luminance(background)) * 3)
        params.pitch_degrees = GLOBE_PITCH
        params.exposure = EXPOSURE
        params.bloom_threshold = BLOOM_THRESHOLD
        params.bloom_strength = BLOOM_STRENGTH
        params.grain_amount = GRAIN_AMOUNT
        params.halo_extent = HALO_EXTENT
        params.grain_seed = random.getrandbits(32)
        average = sum(primary) / 3
        gamma = (ctypes.c_float * 3)(*(1 - 0.08 * (value - average) for value in primary))
        lift = (ctypes.c_float * 3)(*scaled(background, 0.03))
        self.library.globe_grade(gamma, lift)

    def prepare(self, size, radius):
        if not self.ready or size == self.size:
            return
        self.size = size
        self.radius = radius
        count = size * size
        quarter = (size + 3) // 4
        self.u = (ctypes.c_float * count)()
        self.v = (ctypes.c_float * count)()
        self.lod = (ctypes.c_float * count)()
        self.bloom_accumulator = (ctypes.c_float * (quarter * quarter * 3))()
        self.bloom_scratch = (ctypes.c_float * (quarter * quarter * 3))()
        self.bloom = (ctypes.c_float * (quarter * quarter * 3))()
        self.bright = (ctypes.c_uint32 * count)()
        self.library.globe_prepare(size, radius, GLOBE_PITCH, native.RUNTIME_WIDTH, native.RUNTIME_HEIGHT, self.u, self.v, self.lod)
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        self.output = self.surface.get_data()
        self.output_buffer = (ctypes.c_char * len(self.output)).from_buffer(self.output)
        self.output_pointer = ctypes.addressof(self.output_buffer)
        self.params_pointer = ctypes.byref(self.params)

    def render(self, yaw, cloud_yaw):
        self.params.shift = (yaw % 360) / 360 * native.RUNTIME_WIDTH
        self.params.cloud_shift = (cloud_yaw % 360) / 360 * native.RUNTIME_WIDTH
        self.surface.flush()
        self.library.globe_render(
            self.params_pointer, self.u, self.v, self.lod, self.size, self.radius, self.output_pointer,
            self.surface.get_stride(), self.bright, self.bloom_accumulator, self.bloom_scratch, self.bloom,
        )
        self.surface.mark_dirty()
        return self.surface

    def close(self):
        self.ready = False
        self.output_buffer = self.output = self.surface = None
        self.u = self.v = self.lod = self.bright = self.bloom_accumulator = self.bloom_scratch = self.bloom = None
        self.buffers = []
        for mapped in self.maps:
            mapped.close()
        self.maps = []


class PlanetSwitcher:
    def __init__(self, windows, tabs_pressed, alt_released, commit, library, scale, reduce_motion, text_scale, set_title,
                 release_keyboard, initial_offset=0):
        self.windows = windows
        self.count = len(windows)
        self.tabs_pressed = tabs_pressed
        self.alt_released = alt_released
        self.commit = commit
        self.set_title = set_title
        self.release_keyboard = release_keyboard
        self.offset = initial_offset
        self.tab_count = max(1, tabs_pressed())
        self.choice = None
        self.rgb = {key: hex_to_rgb(value) for key, value in COLORS.items()}
        self.sky = Sky()
        self.globe = GlobeRenderer(library)
        self.icon_pixels = max(ICON_PIXELS, math.ceil(2 * MAX_ICON_SIZE * (1 + SELECTED_GROWTH) * scale))
        self.app_positions = self.place_apps()
        self.icon_sprites = [self.icon_sprite(window) for window in windows]
        self.sprite_buckets = [{} for _ in windows]
        self.yaw = self.app_positions[self.selected_index()][0]
        self.yaw_velocity = 0.0
        self.yaw_travel = 0.0
        self.idle_offset = 0.0
        self.cloud_drift = 0.0
        self.reduce_motion = reduce_motion
        self.text_scale = text_scale
        self.scales = [1.0 if index == self.selected_index() else 0.0 for index in range(self.count)]
        self.scale_velocities = [0.0] * self.count
        self.open_error = 0.0 if self.reduce_motion else OPEN_SCALE - 1.0
        self.open_velocity = 0.0
        self.opened_at = None
        self.closing_at = None
        self.quit_requested = False
        self.frame_time = None
        self.drawn_yaw = None
        self.drawn_cloud = None
        self.last_change = None
        self.layout = None
        self.lighting = None
        self.backdrop = None
        self.parallax = None
        self.hit_boxes = []
        self.last_selected = None
        self.label_cache = {}
        self.scroll_remainder = 0
        self.redraw = None
        self.font_options = cairo.FontOptions()
        self.font_options.set_antialias(cairo.ANTIALIAS_GRAY)
        self.font_options.set_hint_style(cairo.HINT_STYLE_SLIGHT)
        self.font_options.set_hint_metrics(cairo.HINT_METRICS_ON)

    def place_apps(self):
        spacing = min(360.0 / self.count, APP_SPACING_DEGREES)
        return [(wrap_degrees(index * spacing), APP_LATITUDES[index % len(APP_LATITUDES)]) for index in range(self.count)]

    def icon_sprite(self, window):
        key = (window.icon_key, self.icon_pixels)
        cached = icon_sprite_cache.get(key)
        if cached:
            return cached
        source = window.icon
        size = self.icon_pixels
        padding = int(size * 0.12)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size + 2 * padding, size + 2 * padding)
        cr = cairo.Context(surface)
        squircle_path(cr, padding, padding, size)
        tile = cairo.LinearGradient(0, padding, 0, padding + size)
        tile.add_color_stop_rgb(0, 0.99, 0.99, 1.0)
        tile.add_color_stop_rgb(1, 0.89, 0.89, 0.92)
        cr.set_source(tile)
        cr.fill()
        if source is not None:
            inner = size * 0.7
            source_width, source_height = source.get_width(), source.get_height()
            scale = inner / max(source_width, source_height)
            cr.save()
            cr.translate(padding + (size - source_width * scale) / 2, padding + (size - source_height * scale) / 2)
            cr.scale(scale, scale)
            cr.set_source_surface(source, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_GOOD)
            cr.paint()
            cr.restore()
        surface.flush()
        cached = (surface, padding)
        if len(icon_sprite_cache) >= ICON_CACHE_LIMIT:
            icon_sprite_cache.pop(next(iter(icon_sprite_cache)))
        icon_sprite_cache[key] = cached
        return cached

    def bucket_sprite(self, index, device_size):
        bucket = max(8, int(round(device_size / 2)) * 2)
        cached = self.sprite_buckets[index].get(bucket)
        if cached:
            return cached
        source, padding = self.icon_sprites[index]
        ratio = bucket / self.icon_pixels
        side = int(math.ceil(source.get_width() * ratio))
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, side, side)
        cr = cairo.Context(surface)
        cr.scale(ratio, ratio)
        cr.set_source_surface(source, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint()
        surface.flush()
        cached = (surface, bucket, padding * ratio)
        self.sprite_buckets[index][bucket] = cached
        return cached

    def tab_index(self):
        return self.tab_count % self.count

    def selected_index(self):
        return (self.tab_index() + self.offset) % self.count

    def select(self, index):
        self.offset = index - self.tab_index()

    def now(self):
        return time.perf_counter()

    def finish(self, choice):
        if self.closing_at is not None:
            return
        self.choice = choice
        self.closing_at = self.now()
        self.release_keyboard()
        if choice is not None and self.commit:
            self.commit(choice)
        self.request_redraw()

    def quit(self):
        self.quit_requested = True
        return False

    def request_redraw(self, dirty=None):
        if dirty is None or self.redraw == "full":
            self.redraw = "full"
        else:
            self.redraw = dirty

    def request_present(self):
        if self.redraw is None:
            self.redraw = "present"

    def fade(self):
        return self.animation_state(self.frame_time if self.frame_time is not None else self.now())[1]

    def compute_layout(self, width, height, scale):
        radius = int(min(height * 0.24, MAX_GLOBE_SIZE / 2))
        cx, cy = width / 2, height / 2 + height * 0.11
        reach = max(radius * HALO_EXTENT, radius + MAX_ICON_SIZE * (1 + SELECTED_GROWTH)) * max(1.0, CLOSE_SCALE)
        dirty = (
            int(cx - reach) - 2, int(cy - reach) - 2,
            int(2 * reach) + 4, int(2 * reach + LABEL_SPACE) + 4,
        )
        globe_pixels = int(math.ceil(2 * radius * HALO_EXTENT * scale / 2)) * 2
        return {
            "width": width, "height": height, "scale": scale, "cx": cx, "cy": cy, "radius": radius,
            "dirty": dirty, "globe_pixels": globe_pixels, "ready": self.globe.ready,
        }

    def prepare_layout(self):
        layout = self.layout
        scale = layout["scale"]
        self.render_lighting(layout["radius"], scale)
        self.render_fallback_globe(layout["radius"], scale)
        self.build_backdrop(layout["width"], layout["height"], scale)
        self.build_icon_decorations(scale)
        self.sprite_buckets = [{} for _ in self.windows]
        if self.globe.ready:
            self.globe.set_scene(self.rgb, self.sky)
            self.globe.prepare(layout["globe_pixels"], layout["radius"] * scale)

    def build_backdrop(self, width, height, scale):
        rng = random.Random(NEBULA_SEED)
        nebula = cairo.ImageSurface(cairo.FORMAT_ARGB32, math.ceil(width / NEBULA_DOWNSCALE), math.ceil(height / NEBULA_DOWNSCALE))
        cr = cairo.Context(nebula)
        cr.scale(1 / NEBULA_DOWNSCALE, 1 / NEBULA_DOWNSCALE)
        cr.set_source_rgba(*mix(self.rgb["background"], BLACK, 0.5), BACKDROP_ALPHA)
        cr.paint()
        for color, alpha in ((self.rgb["primary"], 0.12), (self.rgb["accent"], 0.08), (self.rgb["secondary"], 0.1)):
            center_x, center_y = rng.uniform(0.15, 0.85) * width, rng.uniform(0.15, 0.85) * height
            for _ in range(5):
                x = center_x + rng.uniform(-0.12, 0.12) * width
                y = center_y + rng.uniform(-0.12, 0.12) * height
                reach = rng.uniform(0.12, 0.3) * width
                blob = cairo.RadialGradient(x, y, 0, x, y, reach)
                blob.add_color_stop_rgba(0, *color, alpha * rng.uniform(0.5, 1.0))
                blob.add_color_stop_rgba(0.5, *color, alpha * 0.35)
                blob.add_color_stop_rgba(1, *color, 0)
                cr.set_source(blob)
                cr.paint()
        diagonal = math.hypot(width, height) / 2
        vignette = cairo.RadialGradient(width / 2, height / 2, diagonal * 0.4, width / 2, height / 2, diagonal)
        vignette.add_color_stop_rgba(0, 0, 0, 0, 0)
        vignette.add_color_stop_rgba(1, 0, 0, 0, VIGNETTE_ALPHA)
        cr.set_source(vignette)
        cr.paint()
        nebula.flush()
        base = device_surface(width, height, scale)
        cr = cairo.Context(base)
        cr.scale(NEBULA_DOWNSCALE, NEBULA_DOWNSCALE)
        cr.set_source_surface(nebula, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.get_source().set_extend(cairo.EXTEND_PAD)
        cr.paint()
        base.flush()
        self.backdrop_base = base
        self.star_layers = [self.star_tile(index, layer, scale) for index, layer in enumerate(STAR_LAYERS)]
        self.backdrop = device_surface(width, height, scale)
        self.parallax = None
        self.compose_backdrop()

    def star_tile(self, index, layer, scale):
        tile, count, smallest, largest, brightness, factor, glints = layer
        rng = random.Random(STAR_SEED + index)
        surface = device_surface(tile, tile, scale)
        cr = cairo.Context(surface)
        foreground, accent = self.rgb["foreground"], self.rgb["accent"]
        for star in range(count):
            x, y = rng.uniform(0, tile), rng.uniform(0, tile)
            radius = rng.uniform(smallest, largest)
            color = mix(mix(foreground, WHITE, 0.4), accent, rng.uniform(0, 0.35))
            alpha = brightness * rng.uniform(0.45, 1.0)
            for shift_x in (-tile, 0, tile):
                for shift_y in (-tile, 0, tile):
                    if not (-8 < x + shift_x < tile + 8 and -8 < y + shift_y < tile + 8):
                        continue
                    glow = cairo.RadialGradient(x + shift_x, y + shift_y, 0, x + shift_x, y + shift_y, radius * 2.5)
                    glow.add_color_stop_rgba(0, *color, alpha)
                    glow.add_color_stop_rgba(0.35, *color, alpha * 0.45)
                    glow.add_color_stop_rgba(1, *color, 0)
                    cr.set_source(glow)
                    cr.arc(x + shift_x, y + shift_y, radius * 2.5, 0, 2 * math.pi)
                    cr.fill()
                    if star < glints:
                        for horizontal in (True, False):
                            length = radius * 9
                            start = (x + shift_x - length, y + shift_y) if horizontal else (x + shift_x, y + shift_y - length)
                            end = (x + shift_x + length, y + shift_y) if horizontal else (x + shift_x, y + shift_y + length)
                            ray = cairo.LinearGradient(*start, *end)
                            ray.add_color_stop_rgba(0, *color, 0)
                            ray.add_color_stop_rgba(0.5, *color, alpha * 0.7)
                            ray.add_color_stop_rgba(1, *color, 0)
                            cr.set_source(ray)
                            cr.set_line_width(0.6)
                            cr.move_to(*start)
                            cr.line_to(*end)
                            cr.stroke()
        surface.flush()
        pattern = cairo.SurfacePattern(surface)
        pattern.set_extend(cairo.EXTEND_REPEAT)
        pattern.set_filter(cairo.FILTER_NEAREST)
        return surface, pattern, factor

    def parallax_offsets(self):
        scale = self.layout["scale"]
        return [round(factor * self.yaw_travel * scale) for _, _, factor in self.star_layers]

    def compose_backdrop(self):
        offsets = self.parallax_offsets()
        cr = cairo.Context(self.backdrop)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_surface(self.backdrop_base, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        scale = self.layout["scale"]
        for (_, pattern, _), offset in zip(self.star_layers, offsets):
            matrix = cairo.Matrix()
            matrix.translate(-offset / scale, 0)
            pattern.set_matrix(matrix)
            cr.set_source(pattern)
            cr.paint()
        self.backdrop.flush()
        self.parallax = offsets

    def parallax_moved(self):
        if self.parallax is None:
            return False
        return self.parallax_offsets() != self.parallax

    def build_icon_decorations(self, scale):
        size = 64
        shadow = device_surface(size, size, scale)
        cr = cairo.Context(shadow)
        gradient = cairo.RadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
        gradient.add_color_stop_rgba(0, 0, 0, 0, 0.55)
        gradient.add_color_stop_rgba(0.5, 0, 0, 0, 0.22)
        gradient.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.set_source(gradient)
        cr.paint()
        shadow.flush()
        ring_size = 128
        ring = device_surface(ring_size, ring_size, scale)
        cr = cairo.Context(ring)
        accent = self.rgb["accent"]
        gradient = cairo.RadialGradient(ring_size / 2, ring_size / 2, 0, ring_size / 2, ring_size / 2, ring_size / 2)
        gradient.add_color_stop_rgba(0, *accent, 0.18)
        gradient.add_color_stop_rgba(0.55, *accent, 0.12)
        gradient.add_color_stop_rgba(0.72, *mix(accent, WHITE, 0.3), 0.5)
        gradient.add_color_stop_rgba(0.82, *accent, 0.16)
        gradient.add_color_stop_rgba(1, *accent, 0)
        cr.set_source(gradient)
        cr.paint()
        ring.flush()
        self.shadow_sprite = (shadow, size)
        self.ring_sprite = (ring, ring_size)

    def on_frame(self, now):
        elapsed = 0.0 if self.frame_time is None else min(MAX_FRAME_SECONDS, max(0.0, now - self.frame_time))
        self.frame_time = now
        return self.tick(now, elapsed)

    def animation_state(self, now):
        if self.closing_at is not None:
            progress = min(1.0, max(0.0, (now - self.closing_at) / CLOSE_SECONDS))
            eased = ease_out(progress)
            return (1.0 if self.reduce_motion else 1.0 + (CLOSE_SCALE - 1.0) * eased), 1.0 - eased
        opened = 0.0 if self.opened_at is None else now - self.opened_at
        return 1.0 + self.open_error, min(1.0, opened / OPEN_FADE_SECONDS)

    def tick(self, now, elapsed):
        if self.closing_at is not None:
            if now - self.closing_at >= CLOSE_SECONDS:
                self.quit()
                return False
            if self.layout is None:
                self.request_redraw()
            elif self.reduce_motion:
                self.request_present()
            else:
                self.request_redraw(self.layout["dirty"])
            return True
        if self.alt_released():
            self.tab_count = max(1, self.tabs_pressed())
            self.finish(self.selected_index())
            return True
        if self.opened_at is None:
            self.opened_at = now
            self.last_change = now
        full_redraw = False
        self.tab_count = max(1, self.tabs_pressed())
        selected = self.selected_index()
        changed = selected != self.last_selected
        if changed:
            self.last_change = now
            self.idle_offset = 0.0
            self.describe(selected)
        elif now - self.last_change > IDLE_DELAY_SECONDS and not self.reduce_motion:
            self.idle_offset += IDLE_DEGREES_PER_SECOND * elapsed
        target = self.app_positions[selected][0] + self.idle_offset
        error = wrap_degrees(self.yaw - target)
        if self.reduce_motion and abs(error) > 0.01:
            self.yaw_travel += wrap_degrees(target - self.yaw)
            self.yaw = wrap_degrees(target)
            self.yaw_velocity = 0.0
            changed = True
        elif abs(error) > 0.01 or abs(self.yaw_velocity) > 0.01:
            new_error, self.yaw_velocity = spring(error, self.yaw_velocity, YAW_FREQUENCY, elapsed)
            if new_error * error < 0 and abs(new_error) > MAX_OVERSHOOT_DEGREES:
                new_error = math.copysign(MAX_OVERSHOOT_DEGREES, new_error)
                self.yaw_velocity = 0.0
            new_yaw = wrap_degrees(target + new_error)
            self.yaw_travel += wrap_degrees(new_yaw - self.yaw)
            self.yaw = new_yaw
        if not self.reduce_motion:
            self.cloud_drift += CLOUD_DRIFT_DEGREES_PER_SECOND * elapsed
        if self.layout and self.drawn_yaw is not None:
            pixels_per_degree = math.radians(1) * self.layout["radius"] * self.layout["scale"]
            moved = abs(wrap_degrees(self.yaw - self.drawn_yaw))
            if self.globe.ready:
                moved = max(moved, abs(self.cloud_yaw() - self.drawn_cloud))
            changed = changed or moved * pixels_per_degree >= REDRAW_PIXELS
        for index in range(self.count):
            error = self.scales[index] - (1.0 if index == selected else 0.0)
            if self.reduce_motion and abs(error) > 0.002:
                self.scales[index] = 1.0 if index == selected else 0.0
                self.scale_velocities[index] = 0.0
                changed = True
            elif abs(error) > 0.002 or abs(self.scale_velocities[index]) > 0.002:
                error, self.scale_velocities[index] = spring(error, self.scale_velocities[index], SCALE_FREQUENCY, elapsed)
                self.scales[index] = (1.0 if index == selected else 0.0) + error
                changed = True
        if abs(self.open_error) > 0.0005 or abs(self.open_velocity) > 0.0005:
            self.open_error, self.open_velocity = spring(self.open_error, self.open_velocity, OPEN_FREQUENCY, elapsed)
            changed = True
        else:
            self.open_error = 0.0
        if self.layout and self.parallax_moved():
            self.compose_backdrop()
            full_redraw = True
        if full_redraw or not self.layout:
            self.request_redraw()
        elif changed:
            self.request_redraw(self.layout["dirty"])
        elif now - self.opened_at < OPEN_FADE_SECONDS + 0.02:
            self.request_present()
        self.last_selected = selected
        return True

    def describe(self, selected):
        window = self.windows[selected]
        app_name = window.app_name
        title = window.title or ""
        detail = f", {title}" if title.strip() and title.strip().lower() != app_name.lower() else ""
        self.set_title(f"Window switcher. {app_name}{detail}. {selected + 1} of {self.count}")

    def on_key(self, event):
        if self.closing_at is not None:
            return
        if event == "escape":
            self.finish(None)
        elif event == "confirm":
            self.finish(self.selected_index())
        elif event == "previous":
            self.offset -= 1
        elif event == "next":
            self.offset += 1

    def hit_test(self, x, y):
        for index, (left, top, size) in reversed(self.hit_boxes):
            if left <= x <= left + size and top <= y <= top + size:
                return index
        return None

    def on_click(self, x, y, right_button):
        if self.closing_at is not None:
            return
        index = self.hit_test(x, y)
        if index is not None:
            self.finish(index)
        elif right_button:
            self.finish(None)

    def on_motion(self, x, y):
        if self.closing_at is not None:
            return
        index = self.hit_test(x, y)
        if index is not None and index != self.selected_index():
            self.select(index)

    def on_scroll(self, delta):
        if self.closing_at is not None:
            return
        self.scroll_remainder += delta
        if abs(self.scroll_remainder) >= SCROLL_STEP:
            self.offset += -1 if self.scroll_remainder > 0 else 1
            self.scroll_remainder = 0

    def cloud_yaw(self):
        return self.yaw_travel * CLOUD_SPEED_RATIO + self.cloud_drift

    def draw_globe(self, cr, cx, cy, radius, scale):
        self.drawn_yaw = self.yaw
        self.drawn_cloud = self.cloud_yaw()
        if self.globe.ready:
            surface = self.globe.render(self.yaw, self.drawn_cloud)
            half = self.layout["globe_pixels"] / 2
            left = round((cx * scale - half)) / scale
            top = round((cy * scale - half)) / scale
            cr.save()
            cr.translate(left, top)
            cr.scale(1 / scale, 1 / scale)
            cr.set_source_surface(surface, 0, 0)
            cr.paint()
            cr.restore()
            return
        extent = radius * HALO_EXTENT
        cr.set_source_surface(self.fallback_globe, cx - extent, cy - extent)
        cr.paint()

    def render_fallback_globe(self, radius, scale):
        extent = radius * HALO_EXTENT
        surface = device_surface(2 * extent, 2 * extent, scale)
        cr = cairo.Context(surface)
        cx = cy = extent
        halo_radius = extent
        halo = cairo.RadialGradient(cx, cy, radius * 0.96, cx, cy, halo_radius)
        halo.add_color_stop_rgba(0, *self.rgb["accent"], 0.45)
        halo.add_color_stop_rgba(0.12, *self.rgb["accent"], 0.22)
        halo.add_color_stop_rgba(1, *self.rgb["accent"], 0)
        cr.arc(cx, cy, halo_radius, 0, 2 * math.pi)
        cr.set_source(halo)
        cr.fill()
        sphere = cairo.RadialGradient(cx - radius * 0.3, cy - radius * 0.3, 0, cx, cy, radius)
        sphere.add_color_stop_rgb(0, *mix(self.rgb["primary"], WHITE, 0.1))
        sphere.add_color_stop_rgb(1, *mix(self.rgb["background"], BLACK, 0.6))
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source(sphere)
        cr.fill()
        cr.set_source_surface(self.lighting, cx - radius, cy - radius)
        cr.paint()
        rim = cairo.RadialGradient(cx, cy, radius * 0.82, cx, cy, radius)
        rim.add_color_stop_rgba(0, *self.rgb["accent"], 0)
        rim.add_color_stop_rgba(1, *mix(self.rgb["accent"], WHITE, 0.2), 0.35)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source(rim)
        cr.fill()
        surface.flush()
        self.fallback_globe = surface

    def render_lighting(self, radius, scale):
        period = self.sky.time_of_day
        size = int(2 * radius)
        surface = device_surface(size, size, scale)
        cr = cairo.Context(surface)
        cx = cy = size / 2
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.clip()
        lx, ly, lz = self.sky.light
        if period == "night":
            cr.set_source_rgba(0.02, 0.04, 0.12, 0.28)
            cr.paint()
            shade = cairo.RadialGradient(cx, cy, radius * 0.45, cx, cy, radius)
            shade.add_color_stop_rgba(0, 0, 0, 0, 0.35)
            shade.add_color_stop_rgba(1, 0.0, 0.02, 0.08, 0.7)
        else:
            lit_x, lit_y = cx + lx * radius * 0.8, cy - ly * radius * 0.8
            warmth = DAWN_ORANGE if period in ("dawn", "dusk") else (1.0, 0.96, 0.9)
            darkness = 0.82 if period in ("dawn", "dusk") else 0.6
            shade = cairo.RadialGradient(lit_x, lit_y, 0, lit_x, lit_y, radius * 2.1)
            shade.add_color_stop_rgba(0, *warmth, 0.3 if period == "day" else 0.35)
            shade.add_color_stop_rgba(0.3, *warmth, 0.05)
            shade.add_color_stop_rgba(0.6, 0, 0, 0, darkness * 0.45)
            shade.add_color_stop_rgba(1, 0, 0, 0, darkness)
        cr.set_source(shade)
        cr.paint()
        surface.flush()
        self.lighting = surface

    def paint_sprite(self, cr, sprite, x, y, width, height, alpha):
        surface, size = sprite
        cr.save()
        cr.translate(x - width / 2, y - height / 2)
        cr.scale(width / size, height / size)
        cr.set_source_surface(surface, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        paint_alpha(cr, alpha)
        cr.restore()

    def draw_icons(self, cr, cx, cy, radius, scale):
        base = max(MIN_ICON_SIZE, min(MAX_ICON_SIZE, radius * 1.2 / math.sqrt(self.count)))
        pitch = math.radians(GLOBE_PITCH)
        placed = []
        for index, (lon, lat) in enumerate(self.app_positions):
            dlon = math.radians(lon - self.yaw)
            latitude = math.radians(lat)
            x = math.cos(latitude) * math.sin(dlon)
            world_y = math.sin(latitude)
            world_z = math.cos(latitude) * math.cos(dlon)
            y = world_y * math.cos(pitch) - world_z * math.sin(pitch)
            z = world_y * math.sin(pitch) + world_z * math.cos(pitch)
            if z > 0.08:
                placed.append((z, index, x, y))
        placed.sort()
        light_x, light_y, _ = self.sky.light
        self.hit_boxes = []
        for z, index, x, y in placed:
            highlight = self.scales[index]
            size = base * (0.55 + 0.45 * z) * (1 + SELECTED_GROWTH * highlight)
            center_x, center_y = cx + x * radius, cy - y * radius
            alpha = min(1.0, (z - 0.08) / 0.3)
            self.paint_sprite(
                cr, self.shadow_sprite, center_x - light_x * size * 0.12, center_y + size * 0.42 + light_y * size * 0.06,
                size * 1.05, size * 0.38 * (0.5 + 0.5 * z), alpha * 0.8,
            )
            if highlight > 0.01:
                ring = size * 1.75
                self.paint_sprite(cr, self.ring_sprite, center_x, center_y, ring, ring, alpha * min(1.0, highlight))
            surface, bucket, padding = self.bucket_sprite(index, size * scale)
            left, top = center_x - size / 2, center_y - size / 2
            ratio = size * scale / bucket
            cr.save()
            cr.translate(left, top)
            cr.scale(ratio / scale, ratio / scale)
            cr.translate(-padding, -padding)
            cr.set_source_surface(surface, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_BILINEAR)
            paint_alpha(cr, alpha)
            cr.restore()
            self.hit_boxes.append((index, (left, top, size)))

    def set_label_font(self, cr, size, bold):
        cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(size * self.text_scale)
        cr.set_font_options(self.font_options)

    def label_surface(self, cr, text, size, bold, max_width, scale):
        key = (text, size, bold, max_width, scale)
        cached = self.label_cache.get(key)
        if cached:
            return cached
        text = "".join(character for character in text if ord(character) <= 0xFFFF and not 0x2600 <= ord(character) <= 0x27BF).strip()
        cr.save()
        self.set_label_font(cr, size, bold)
        if max_width:
            while len(text) > 4 and cr.text_extents(text).width > max_width:
                text = text[:-2].rstrip() + "…"
        extents = cr.text_extents(text)
        ascent, descent = cr.font_extents()[:2]
        cr.restore()
        padding = 3
        surface = device_surface(extents.width + 2 * padding, ascent + descent + 2 * padding, scale)
        label = cairo.Context(surface)
        self.set_label_font(label, size, bold)
        origin_x, origin_y = padding - extents.x_bearing, padding + ascent
        for dx, dy, shadow in ((0, 2, 0.55), (1, 1, 0.35), (-1, 1, 0.35)):
            label.move_to(origin_x + dx, origin_y + dy)
            label.set_source_rgba(0, 0, 0, shadow)
            label.show_text(text)
        label.move_to(origin_x, origin_y)
        label.set_source_rgb(*self.rgb["foreground"])
        label.show_text(text)
        surface.flush()
        cached = (surface, extents.width / 2 + padding, origin_y)
        self.label_cache[key] = cached
        return cached

    def draw_text(self, cr, text, cx, y, size, alpha, scale, bold=False, max_width=None):
        surface, half_width, baseline = self.label_surface(cr, text, size, bold, max_width, scale)
        cr.set_source_surface(surface, round((cx - half_width) * scale) / scale, round((y - baseline) * scale) / scale)
        paint_alpha(cr, alpha)

    def on_draw(self, cr, width, height, scale):
        layout = self.layout
        if not layout or (layout["width"], layout["height"], layout["scale"], layout["ready"]) != (width, height, scale, self.globe.ready):
            self.layout = self.compute_layout(width, height, scale)
            self.prepare_layout()
            layout = self.layout
        now = self.frame_time if self.frame_time is not None else self.now()
        zoom = self.animation_state(now)[0]
        cx, cy, radius = layout["cx"], layout["cy"], layout["radius"]
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_surface(self.backdrop, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        animating = abs(zoom - 1.0) > 0.0005
        if animating:
            cr.push_group()
            cr.translate(cx, cy)
            cr.scale(zoom, zoom)
            cr.translate(-cx, -cy)
        self.draw_globe(cr, cx, cy, radius, scale)
        self.draw_icons(cr, cx, cy, radius, scale)
        if animating:
            cr.pop_group_to_source()
            cr.paint()
        selected = self.windows[self.selected_index()]
        app_name = selected.app_name
        title = selected.title or ""
        label_top = cy + radius + 52
        self.draw_text(cr, app_name, cx, label_top, 22, 1.0, scale, True, width * 0.4)
        if title.strip().lower() != app_name.lower():
            self.draw_text(cr, title, cx, label_top + 24 * self.text_scale, 13, 0.8, scale, False, width * 0.4)
        return False

    def release(self):
        self.globe.close()
        self.backdrop = self.backdrop_base = self.star_layers = self.lighting = self.fallback_globe = None
        self.icon_sprites = []
        self.sprite_buckets = []
        self.label_cache = {}
