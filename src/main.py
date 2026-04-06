#!/usr/bin/env python3
"""Zenith — ADHD Focus Companion for Linux."""

import sys
import os
import gi
import time
import threading

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio, GObject, Gdk
from src.database import (
    add_session, add_capture, get_captures, delete_capture,
    add_energy, get_energy_entries, get_today_energy,
    add_worry, dismiss_worry, get_active_worries, get_stats,
    get_setting, set_setting,
)
from src.circular_timer import CircularTimer
from src.breathing import BreathingCircle


# ─── Resource paths ────────────────────────────────────────────
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
RESOURCES_DIR = os.path.join(PROJECT_DIR, 'resources')
CSS_FILE = os.path.join(RESOURCES_DIR, 'style.css')


def load_css():
    """Load custom CSS."""
    css_provider = Gtk.CssProvider()
    css_provider.load_from_path(CSS_FILE)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


# ─── Timer Page ────────────────────────────────────────────────
class TimerPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(24)
        self.set_margin_bottom(24)

        self.timer_duration = 25 * 60  # seconds
        self.time_remaining = self.timer_duration
        self.timer_running = False
        self.timer_thread = None
        self.timer_stop = False

        # Title
        title = Gtk.Label(label="focus")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.CENTER)
        self.append(title)

        subtitle = Gtk.Label(label="one thing at a time")
        subtitle.add_css_class("page-subtitle")
        subtitle.set_halign(Gtk.Align.CENTER)
        self.append(subtitle)

        # Circular timer
        self.timer_widget = CircularTimer(size=240)
        self.timer_widget.set_halign(Gtk.Align.CENTER)
        self.timer_widget.set_valign(Gtk.Align.CENTER)
        self.append(self.timer_widget)

        # Time display
        self.time_label = Gtk.Label(label="25:00")
        self.time_label.add_css_class("timer-display")
        self.time_label.set_halign(Gtk.Align.CENTER)
        self.append(self.time_label)

        self.status_label = Gtk.Label(label="ready")
        self.status_label.add_css_class("timer-label")
        self.status_label.set_halign(Gtk.Align.CENTER)
        self.append(self.status_label)

        # Controls
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.set_halign(Gtk.Align.CENTER)

        self.start_btn = Gtk.Button(label="start")
        self.start_btn.add_css_class("accent-btn")
        self.start_btn.connect("clicked", self.on_start)
        controls.append(self.start_btn)

        self.reset_btn = Gtk.Button(label="reset")
        self.reset_btn.add_css_class("secondary-btn")
        self.reset_btn.connect("clicked", self.on_reset)
        controls.append(self.reset_btn)

        self.append(controls)

        # Presets
        presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        presets.set_halign(Gtk.Align.CENTER)

        for mins in [5, 15, 25, 50]:
            btn = Gtk.Button(label=f"{mins}m")
            btn.add_css_class("preset-btn")
            if mins == 25:
                btn.add_css_class("active")
            btn._minutes = mins
            btn.connect("clicked", self.on_preset, mins)
            presets.append(btn)

        self.append(presets)

    def on_start(self, btn):
        if not self.timer_running:
            self.timer_running = True
            self.timer_stop = False
            self.start_btn.set_label("pause")
            self.status_label.set_text("focusing")
            self.timer_thread = threading.Thread(target=self._run_timer, daemon=True)
            self.timer_thread.start()
        else:
            self.timer_running = False
            self.timer_stop = True
            self.start_btn.set_label("resume")
            self.status_label.set_text("paused")

    def on_reset(self, btn):
        self.timer_running = False
        self.timer_stop = True
        self.time_remaining = self.timer_duration
        self.start_btn.set_label("start")
        self.status_label.set_text("ready")
        self._update_display()

    def on_preset(self, btn, mins):
        self.timer_duration = mins * 60
        self.time_remaining = self.timer_duration
        self.timer_running = False
        self.timer_stop = True
        self.start_btn.set_label("start")
        self.status_label.set_text("ready")
        self._update_display()

    def _run_timer(self):
        while self.time_remaining > 0 and not self.timer_stop:
            time.sleep(1)
            if not self.timer_stop:
                self.time_remaining -= 1
                GLib.idle_add(self._update_display)

        if self.time_remaining <= 0:
            GLib.idle_add(self._on_complete)

    def _update_display(self):
        mins = self.time_remaining // 60
        secs = self.time_remaining % 60
        self.time_label.set_text(f"{mins:02d}:{secs:02d}")
        progress = 1.0 - (self.time_remaining / self.timer_duration)
        self.timer_widget.set_progress(progress)

    def _on_complete(self):
        self.timer_running = False
        self.start_btn.set_label("start")
        self.status_label.set_text("done — nice work")
        self.time_label.set_text("00:00")
        self.timer_widget.set_progress(1.0)
        add_session("focus", self.timer_duration, completed=True)

        # Reset after a moment
        def do_reset():
            self.time_remaining = self.timer_duration
            self.timer_widget.set_progress(0)
            self.status_label.set_text("ready")
            mins = self.time_remaining // 60
            secs = self.time_remaining % 60
            self.time_label.set_text(f"{mins:02d}:{secs:02d}")
        GLib.timeout_add(3000, do_reset)


# ─── Capture Page ──────────────────────────────────────────────
class CapturePage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(24)
        self.set_margin_bottom(24)

        # Title
        title = Gtk.Label(label="brain dump")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        subtitle = Gtk.Label(label="throw everything here. sort it later.")
        subtitle.add_css_class("page-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        self.append(subtitle)

        # Input
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.entry = Gtk.Entry()
        self.entry.add_css_class("capture-entry")
        self.entry.set_hexpand(True)
        self.entry.set_placeholder_text("what's in your head...")
        self.entry.connect("activate", self.on_add)
        input_box.append(self.entry)

        add_btn = Gtk.Button(label="dump it")
        add_btn.add_css_class("accent-btn")
        add_btn.connect("clicked", self.on_add)
        input_box.append(add_btn)

        self.append(input_box)

        # List
        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("glass-card")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_show_separators(False)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.list_box)
        self.append(scroll)

        self._load_captures()

    def on_add(self, widget):
        text = self.entry.get_text().strip()
        if not text:
            return
        add_capture(text)
        self.entry.set_text("")
        self._load_captures()

    def _load_captures(self):
        # Clear existing
        while self.list_box.get_first_child():
            self.list_box.remove(self.list_box.get_first_child())

        captures = get_captures(50)
        if not captures:
            empty = Gtk.Label(label="empty. that's fine.")
            empty.add_css_class("empty-state")
            empty.set_margin_top(40)
            empty.set_margin_bottom(40)
            self.list_box.append(empty)
            return

        for c in captures:
            row = self._make_row(c)
            self.list_box.append(row)

    def _make_row(self, capture):
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row_box.set_margin_start(12)
        row_box.set_margin_end(12)
        row_box.set_margin_top(6)
        row_box.set_margin_bottom(6)

        text_label = Gtk.Label(label=capture["text"])
        text_label.set_halign(Gtk.Align.START)
        text_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        text_label.set_hexpand(True)
        text_label.set_xalign(0)
        row_box.append(text_label)

        time_label = Gtk.Label(label=capture["created_at"][11:16])
        time_label.add_css_class("empty-state")
        row_box.append(time_label)

        del_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        del_btn.add_css_class("close-btn")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.connect("clicked", self.on_delete, capture["id"])
        row_box.append(del_btn)

        return row_box

    def on_delete(self, btn, capture_id):
        delete_capture(capture_id)
        self._load_captures()


# ─── Worries Page ──────────────────────────────────────────────
class WorriesPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(24)
        self.set_margin_bottom(24)

        title = Gtk.Label(label="worry parking lot")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        subtitle = Gtk.Label(label="park it here so it stops bugging you.")
        subtitle.add_css_class("page-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        self.append(subtitle)

        # Input
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.entry = Gtk.Entry()
        self.entry.add_css_class("capture-entry")
        self.entry.set_hexpand(True)
        self.entry.set_placeholder_text("what's bothering you...")
        self.entry.connect("activate", self.on_add)
        input_box.append(self.entry)

        add_btn = Gtk.Button(label="park it")
        add_btn.add_css_class("teal-btn")
        add_btn.connect("clicked", self.on_add)
        input_box.append(add_btn)
        self.append(input_box)

        # List
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.list_box)
        self.append(scroll)

        self._load_worries()

    def on_add(self, widget):
        text = self.entry.get_text().strip()
        if not text:
            return
        add_worry(text)
        self.entry.set_text("")
        self._load_worries()

    def _load_worries(self):
        while self.list_box.get_first_child():
            self.list_box.remove(self.list_box.get_first_child())

        worries = get_active_worries()
        if not worries:
            empty = Gtk.Label(label="clear mind. nice.")
            empty.add_css_class("empty-state")
            empty.set_margin_top(40)
            empty.set_margin_bottom(40)
            self.list_box.append(empty)
            return

        for w in worries:
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row_box.set_margin_start(12)
            row_box.set_margin_end(12)
            row_box.set_margin_top(6)
            row_box.set_margin_bottom(6)

            cloud = Gtk.Label(label="☁")
            cloud.set_halign(Gtk.Align.CENTER)
            row_box.append(cloud)

            text_label = Gtk.Label(label=w["text"])
            text_label.set_halign(Gtk.Align.START)
            text_label.set_ellipsize(3)
            text_label.set_hexpand(True)
            text_label.set_xalign(0)
            row_box.append(text_label)

            dismiss_btn = Gtk.Button(label="let go")
            dismiss_btn.add_css_class("close-btn")
            dismiss_btn.set_valign(Gtk.Align.CENTER)
            dismiss_btn.connect("clicked", self.on_dismiss, w["id"])
            row_box.append(dismiss_btn)

            self.list_box.append(row_box)

    def on_dismiss(self, btn, worry_id):
        dismiss_worry(worry_id)
        self._load_worries()


# ─── Energy Page ───────────────────────────────────────────────
class EnergyPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(24)
        self.set_margin_bottom(24)

        title = Gtk.Label(label="energy")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        subtitle = Gtk.Label(label="how are you right now?")
        subtitle.add_css_class("page-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        self.append(subtitle)

        self.energies = [
            ("😫", "exhausted"),
            ("😕", "low"),
            ("😐", "meh"),
            ("🙂", "okay"),
            ("⚡", "wired"),
        ]

        energy_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        energy_box.set_halign(Gtk.Align.CENTER)

        for i, (emoji, label) in enumerate(self.energies, 1):
            btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            btn_box.set_halign(Gtk.Align.CENTER)

            btn = Gtk.Button(label=emoji)
            btn.add_css_class("energy-btn")
            btn.set_size_request(64, 64)
            btn.connect("clicked", self.on_energy, i)
            btn_box.append(btn)

            lbl = Gtk.Label(label=label)
            lbl.add_css_class("empty-state")
            lbl.style = "font-size: 10px"
            btn_box.append(lbl)

            energy_box.append(btn_box)

        self.append(energy_box)

        # Today's entry
        today = get_today_energy()
        if today:
            emoji, label = self.energies[today["value"] - 1]
            today_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            today_box.set_halign(Gtk.Align.CENTER)
            today_label = Gtk.Label(label=f"earlier: {emoji} {label}")
            today_label.add_css_class("page-subtitle")
            today_box.append(today_label)
            self.append(today_label)

        # History
        section = Gtk.Label(label="recent")
        section.add_css_class("section-header")
        section.set_halign(Gtk.Align.START)
        self.append(section)

        self.history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.history_box)
        self.append(scroll)

        self._load_history()

    def on_energy(self, btn, value):
        add_energy(value)
        # Visual feedback
        for child in self.get_children():
            for sub in self._get_all_buttons(child):
                sub.remove_css_class("selected")
        btn.add_css_class("selected")
        self._load_history()

    def _get_all_buttons(self, widget):
        buttons = []
        if isinstance(widget, Gtk.Button):
            buttons.append(widget)
        if hasattr(widget, 'get_first_child'):
            child = widget.get_first_child()
            while child:
                buttons.extend(self._get_all_buttons(child))
                child = child.get_next_sibling()
        return buttons

    def _load_history(self):
        while self.history_box.get_first_child():
            self.history_box.remove(self.history_box.get_first_child())

        entries = get_energy_entries(20)
        if not entries:
            empty = Gtk.Label(label="no entries yet")
            empty.add_css_class("empty-state")
            self.history_box.append(empty)
            return

        for e in entries:
            emoji, label = self.energies[e["value"] - 1]
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            emoji_label = Gtk.Label(label=emoji)
            row.append(emoji_label)

            val_label = Gtk.Label(label=f"{label} ({e['value']}/5)")
            val_label.set_halign(Gtk.Align.START)
            val_label.set_xalign(0)
            val_label.set_hexpand(True)
            row.append(val_label)

            time_label = Gtk.Label(label=e["created_at"][11:16])
            time_label.add_css_class("empty-state")
            row.append(time_label)

            self.history_box.append(row)


# ─── Stats Page ────────────────────────────────────────────────
class StatsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(24)
        self.set_margin_bottom(24)

        title = Gtk.Label(label="how you're doing")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        subtitle = Gtk.Label(label="no judgment. just numbers.")
        subtitle.add_css_class("page-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        self.append(subtitle)

        stats = get_stats()

        # Grid
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)

        self._add_stat(grid, 0, 0, str(stats["week_sessions"]), "this week")
        self._add_stat(grid, 1, 0, str(stats["total_sessions"]), "all time")
        self._add_stat(grid, 0, 1, str(stats["total_minutes"]), "minutes focused")
        self._add_stat(grid, 1, 1, str(stats["total_captures"]), "ideas captured")

        if stats["avg_energy"]:
            self._add_stat(grid, 0, 2, f"{'😫😕😐🙂⚡'[round(stats['avg_energy'])-1]} {stats['avg_energy']}/5", "avg energy")

        self.append(grid)

        # Reassurance
        count = stats["total_sessions"]
        if count == 0:
            msg = "you're here. that counts for something."
        elif count < 5:
            msg = "small numbers. still progress."
        elif count < 20:
            msg = "you're getting things done. more than you think."
        else:
            msg = "look at that. you've been busy."

        reassurance = Gtk.Label(label=msg)
        reassurance.add_css_class("reassurance")
        reassurance.set_halign(Gtk.Align.CENTER)
        reassurance.set_margin_top(24)
        self.append(reassurance)

    def _add_stat(self, grid, col, row, value, label):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("stat-card")
        card.set_size_request(160, 90)

        val = Gtk.Label(label=value)
        val.add_css_class("stat-value")
        val.set_halign(Gtk.Align.CENTER)
        card.append(val)

        lbl = Gtk.Label(label=label)
        lbl.add_css_class("stat-label")
        lbl.set_halign(Gtk.Align.CENTER)
        card.append(lbl)

        grid.attach(card, col, row, 1, 1)


# ─── Breathing Page ────────────────────────────────────────────
class BreathingPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(24)
        self.set_margin_bottom(24)

        title = Gtk.Label(label="breathe")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.CENTER)
        self.append(title)

        subtitle = Gtk.Label(label="4 seconds each. nothing else matters.")
        subtitle.add_css_class("page-subtitle")
        subtitle.set_halign(Gtk.Align.CENTER)
        self.append(subtitle)

        self.breath_circle = BreathingCircle(size=200)
        self.breath_circle.set_halign(Gtk.Align.CENTER)
        self.append(self.breath_circle)

        self.phase_label = Gtk.Label(label="ready")
        self.phase_label.add_css_class("breath-label")
        self.phase_label.set_halign(Gtk.Align.CENTER)
        self.append(self.phase_label)

        self.cycle_label = Gtk.Label(label="")
        self.cycle_label.add_css_class("page-subtitle")
        self.cycle_label.set_halign(Gtk.Align.CENTER)
        self.append(self.cycle_label)

        # Controls
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.set_halign(Gtk.Align.CENTER)

        self.start_btn = Gtk.Button(label="begin")
        self.start_btn.add_css_class("teal-btn")
        self.start_btn.connect("clicked", self.on_toggle)
        controls.append(self.start_btn)
        self.append(controls)

        self.running = False
        self.cycle_count = 0
        self.breath_timer = None

    def on_toggle(self, btn):
        if not self.running:
            self.running = True
            self.cycle_count = 0
            self.start_btn.set_label("stop")
            self._breath_cycle()
        else:
            self.running = False
            self.start_btn.set_label("begin")
            self.phase_label.set_text("ready")
            self.cycle_label.set_text("")
            if self.breath_timer:
                GLib.source_remove(self.breath_timer)
                self.breath_timer = None

    def _breath_cycle(self):
        if not self.running:
            return

        phases = [
            ("inhale", 4000),
            ("hold", 4000),
            ("exhale", 4000),
        ]

        self._run_phase(phases, 0)

    def _run_phase(self, phases, index):
        if not self.running:
            return

        if index >= len(phases):
            self.cycle_count += 1
            self.cycle_label.set_text(f"cycle {self.cycle_count}")
            self._run_phase(phases, 0)
            return

        phase_name, duration = phases[index]
        self.breath_circle.set_phase(phase_name)
        self.phase_label.set_text(f"breathe {phase_name}")

        def next_phase():
            self._run_phase(phases, index + 1)
            return False

        self.breath_timer = GLib.timeout_add(duration, next_phase)


# ─── Main Window ───────────────────────────────────────────────
class ZenithWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(420, 720)
        self.set_title("Zenith")

        # Tab bar
        self.tab_bar = Adw.ViewSwitcherBar()
        self.view_stack = Adw.ViewStack()

        # Add pages
        self.view_stack.add_titled(TimerPage(), "timer", "◎ Focus")
        self.view_stack.add_titled(CapturePage(), "capture", "⚡ Dump")
        self.view_stack.add_titled(WorriesPage(), "worries", "☁ Worries")
        self.view_stack.add_titled(EnergyPage(), "energy", "◈ Energy")
        self.view_stack.add_titled(StatsPage(), "stats", "◇ Stats")
        self.view_stack.add_titled(BreathingPage(), "breathing", "◇ Breathe")

        # View switcher at bottom
        self.tab_bar.set_stack(self.view_stack)

        # Layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(self.view_stack)
        main_box.append(self.tab_bar)

        self.set_content(main_box)


# ─── Application ───────────────────────────────────────────────
class ZenithApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.zenith.app",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        win = ZenithWindow(application=self)
        win.present()


def main():
    app = ZenithApplication()

    def on_startup(app):
        load_css()

    app.connect('startup', on_startup)
    app.run(sys.argv)


if __name__ == "__main__":
    main()
