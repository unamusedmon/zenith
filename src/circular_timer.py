"""Custom GTK drawing widget for animated circular timer."""
import math
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk


class CircularTimer(Gtk.DrawingArea):
    """Animated circular progress timer with smooth rendering."""

    def __init__(self, size: int = 240):
        super().__init__()
        self.size = size
        self.progress = 0.0  # 0.0 to 1.0
        self.line_width = 4
        self.track_color = (0.12, 0.12, 0.12, 1.0)
        # Amber accent
        self.progress_color = (0.83, 0.53, 0.24, 1.0)
        self.glow_color = (0.83, 0.53, 0.24, 0.15)

        self.set_size_request(size, size)
        self.set_draw_func(self.draw_func, None)

    def draw_func(self, area, ctx, width, height, data):
        cx = width / 2
        cy = height / 2
        radius = min(cx, cy) - self.line_width * 3

        # Draw glow
        ctx.set_line_width(self.line_width + 12)
        ctx.set_source_rgba(*self.glow_color)
        ctx.arc(cx, cy, radius, 0, 2 * math.pi)
        ctx.stroke()

        # Draw track
        ctx.set_line_width(self.line_width)
        ctx.set_source_rgba(*self.track_color)
        ctx.arc(cx, cy, radius, 0, 2 * math.pi)
        ctx.stroke()

        # Draw progress
        if self.progress > 0:
            ctx.set_line_width(self.line_width)
            ctx.set_source_rgba(*self.progress_color)
            ctx.set_line_cap(1)  # rounded

            start_angle = -math.pi / 2
            end_angle = start_angle + (2 * math.pi * self.progress)

            ctx.arc(cx, cy, radius, start_angle, end_angle)
            ctx.stroke()

    def set_progress(self, progress: float):
        """Set progress (0.0 to 1.0) and trigger redraw."""
        self.progress = max(0.0, min(1.0, progress))
        self.queue_draw()

    def reset(self):
        self.progress = 0.0
        self.queue_draw()
