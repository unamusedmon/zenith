"""Breathing exercise overlay with animated circle."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk, Graphene
import math


class BreathingCircle(Gtk.DrawingArea):
    """Animated breathing circle for 4-4-4 box breathing."""

    def __init__(self, size: int = 200):
        super().__init__()
        self.size = size
        self.scale = 0.8  # 0.6 (exhale) to 1.3 (inhale)
        self.target_scale = 0.8
        self.set_size_request(size, size)
        self.set_draw_func(self.draw_func, None)

        self.animating = False
        self.anim_tick = None

    def draw_func(self, area, ctx, width, height, data):
        cx = width / 2
        cy = height / 2
        base_radius = min(cx, cy) * 0.7
        radius = base_radius * self.scale

        # Outer glow
        ctx.set_line_width(3)
        ctx.set_source_rgba(0.29, 0.62, 0.56, 0.08)
        ctx.arc(cx, cy, radius + 15, 0, 2 * math.pi)
        ctx.stroke()

        # Main circle
        ctx.set_line_width(2)
        ctx.set_source_rgba(0.29, 0.62, 0.56, 0.5)
        ctx.arc(cx, cy, radius, 0, 2 * math.pi)
        ctx.stroke()

        # Inner fill
        ctx.set_source_rgba(0.29, 0.62, 0.56, 0.04)
        ctx.arc(cx, cy, radius, 0, 2 * math.pi)
        ctx.fill()

    def _animate(self):
        """Smooth interpolation toward target scale."""
        diff = self.target_scale - self.scale
        if abs(diff) < 0.005:
            self.scale = self.target_scale
            self.animating = False
            self.queue_draw()
            return False  # stop animation

        self.scale += diff * 0.06
        self.queue_draw()
        return True  # continue

    def set_phase(self, phase: str):
        """Set breathing phase: 'inhale', 'hold', 'exhale'."""
        if phase == 'inhale':
            self.target_scale = 1.3
        elif phase == 'hold':
            self.target_scale = 1.3
        elif phase == 'exhale':
            self.target_scale = 0.7
        else:
            self.target_scale = 0.8

        if not self.animating:
            self.animating = True
            GLib.timeout_add(16, self._animate)
