#!/usr/bin/env python3
"""Zenith — ADHD Focus Companion for Linux."""

import sys
import os
import gi
import time
import threading

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GObject
from src.database import (
    add_session, add_capture, get_captures, delete_capture,
    add_energy, get_energy_entries, get_today_energy,
    add_worry, dismiss_worry, get_active_worries, get_stats,
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
    display = Gdk.Display.get_default()
    Gtk.StyleContext.add_provider_for_display(
        display,
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


# ─── Sidebar ───────────────────────────────────────────────────
class Sidebar(Gtk.Box):
    def __init__(self, callback):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.callback = callback
        self.active = "todo"
        self.set_size_request(180, -1)
        self.add_css_class("sidebar")

        # Logo
        logo = Gtk.Label(label="◎ zenith")
        logo.add_css_class("sidebar-logo")
        logo.set_margin_top(20)
        logo.set_margin_bottom(16)
        self.append(logo)

        # Nav items
        items = [
            ("todo", "☐", "todo"),
            ("timer", "◷", "timer"),
            ("dump", "⚡", "brain dump"),
            ("worries", "☁", "worries"),
            ("energy", "◈", "energy"),
            ("stats", "◇", "stats"),
            ("breathe", "◇", "breathe"),
        ]

        for page_id, icon, label in items:
            btn = self._make_nav_btn(page_id, icon, label)
            self.append(btn)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        self.append(spacer)

        # Quit button
        quit_btn = Gtk.Button(label="✕ quit")
        quit_btn.add_css_class("quit-btn")
        quit_btn.set_margin_bottom(16)
        quit_btn.set_margin_start(8)
        quit_btn.set_margin_end(8)
        quit_btn.connect("clicked", lambda b: Gtk.Application.get_default().quit())
        self.append(quit_btn)

    def _make_nav_btn(self, page_id, icon, label):
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_margin_start(8)
        btn_box.set_margin_end(8)
        btn_box.set_margin_top(2)
        btn_box.set_margin_bottom(2)

        icon_label = Gtk.Label(label=icon)
        icon_label.set_width_chars(2)
        btn_box.append(icon_label)

        text_label = Gtk.Label(label=label)
        text_label.set_halign(Gtk.Align.START)
        text_label.set_hexpand(True)
        text_label.set_xalign(0)
        btn_box.append(text_label)

        btn = Gtk.Button()
        btn.set_child(btn_box)
        btn.add_css_class("nav-btn")
        if page_id == self.active:
            btn.add_css_class("nav-btn-active")
        btn.connect("clicked", self._on_nav, page_id)
        return btn

    def _on_nav(self, btn, page_id):
        self.active = page_id
        # Update visual state
        child = self.get_first_child()
        while child:
            if hasattr(child, 'get_css_classes'):
                classes = child.get_css_classes()
                if 'nav-btn' in classes:
                    child.remove_css_class('nav-btn-active')
            child = child.get_next_sibling()
        btn.add_css_class('nav-btn-active')
        self.callback(page_id)


# ─── Todo Page ─────────────────────────────────────────────────
class TodoPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        # Title
        title = Gtk.Label(label="todo")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        # Input row
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_row.set_margin_bottom(8)

        self.task_entry = Gtk.Entry()
        self.task_entry.add_css_class("capture-entry")
        self.task_entry.set_hexpand(True)
        self.task_entry.set_placeholder_text("add a task...")
        self.task_entry.connect("activate", self._on_add)
        input_row.append(self.task_entry)

        self.priority_model = Gtk.StringList()
        for p in ["low", "medium", "high"]:
            self.priority_model.append(p)
        self.priority_combo = Gtk.DropDown(model=self.priority_model)
        self.priority_combo.set_selected(1)  # default medium
        self.priority_combo.add_css_class("priority-combo")
        input_row.append(self.priority_combo)

        add_btn = Gtk.Button(label="+")
        add_btn.add_css_class("accent-btn")
        add_btn.connect("clicked", self._on_add)
        input_row.append(add_btn)

        self.append(input_row)

        # Task list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.list_box)
        self.append(scroll)

        # Load from brain dumps as todo items
        self.tasks = []
        self._load_tasks()

    def _on_add(self, widget):
        text = self.task_entry.get_text().strip()
        if not text:
            return
        priority = self.priority_model.get_string(self.priority_combo.get_selected())
        self.tasks.append({
            "text": text,
            "priority": priority,
            "done": False,
        })
        add_capture(text)  # also save to db
        self.task_entry.set_text("")
        self._render()

    def _load_tasks(self):
        captures = get_captures(100)
        self.tasks = []
        for c in captures:
            self.tasks.append({
                "text": c["text"],
                "priority": "medium",
                "done": False,
            })
        self._render()

    def _render(self):
        while self.list_box.get_first_child():
            self.list_box.remove(self.list_box.get_first_child())

        if not self.tasks:
            empty = Gtk.Label(label="nothing here. add something or enjoy the void.")
            empty.add_css_class("empty-state")
            empty.set_margin_top(60)
            self.list_box.append(empty)
            return

        # Sort: undone first, then by priority
        order = {"high": 0, "medium": 1, "low": 2}
        sorted_tasks = sorted(self.tasks, key=lambda t: (t["done"], order.get(t["priority"], 1)))

        for i, task in enumerate(sorted_tasks):
            row = self._make_task_row(task, i)
            self.list_box.append(row)

    def _make_task_row(self, task, idx):
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row_box.set_margin_start(8)
        row_box.set_margin_end(8)
        row_box.set_margin_top(4)
        row_box.set_margin_bottom(4)

        # Checkbox
        check = Gtk.CheckButton()
        check.set_active(task["done"])
        check.connect("toggled", self._on_toggle, idx)
        row_box.append(check)

        # Priority indicator
        p_dot = Gtk.Box()
        p_dot.set_size_request(4, 24)
        colors = {"high": "#d4883e", "medium": "#4a9e8e", "low": "rgba(255,255,255,0.2)"}
        p_dot.set_css_classes([f"priority-dot-{task['priority']}"])
        row_box.append(p_dot)

        # Text
        text_label = Gtk.Label(label=task["text"])
        text_label.set_halign(Gtk.Align.START)
        text_label.set_hexpand(True)
        text_label.set_xalign(0)
        text_label.set_ellipsize(3)
        if task["done"]:
            text_label.add_css_class("task-done")
        row_box.append(text_label)

        # Delete
        del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        del_btn.add_css_class("close-btn")
        del_btn.connect("clicked", self._on_delete, idx)
        row_box.append(del_btn)

        return row_box

    def _on_toggle(self, check, idx):
        self.tasks[idx]["done"] = check.get_active()
        if self.tasks[idx]["done"]:
            add_session("task", 0, completed=True)
        self._render()

    def _on_delete(self, btn, idx):
        self.tasks.pop(idx)
        self._render()


# ─── Timer Page (standalone now) ──────────────────────────────
class TimerPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(24)
        self.set_margin_bottom(24)

        # Spacer
        spacer1 = Gtk.Box()
        spacer1.set_vexpand(True)
        self.append(spacer1)

        title = Gtk.Label(label="focus")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.CENTER)
        self.append(title)

        self.timer_widget = CircularTimer(size=220)
        self.timer_widget.set_halign(Gtk.Align.CENTER)
        self.append(self.timer_widget)

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

        spacer2 = Gtk.Box()
        spacer2.set_vexpand(True)
        self.append(spacer2)

        # Timer state
        self.timer_duration = 25 * 60
        self.time_remaining = self.timer_duration
        self.timer_running = False
        self.timer_thread = None
        self.timer_stop = False

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
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        title = Gtk.Label(label="brain dump")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        subtitle = Gtk.Label(label="throw everything here. sort it later.")
        subtitle.add_css_class("page-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        self.append(subtitle)

        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.entry = Gtk.Entry()
        self.entry.add_css_class("capture-entry")
        self.entry.set_hexpand(True)
        self.entry.set_placeholder_text("what's in your head...")
        self.entry.connect("activate", self.on_add)
        input_box.append(self.entry)

        add_btn = Gtk.Button(label="dump")
        add_btn.add_css_class("accent-btn")
        add_btn.connect("clicked", self.on_add)
        input_box.append(add_btn)
        self.append(input_box)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
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
        while self.list_box.get_first_child():
            self.list_box.remove(self.list_box.get_first_child())

        captures = get_captures(50)
        if not captures:
            empty = Gtk.Label(label="empty. that's fine.")
            empty.add_css_class("empty-state")
            empty.set_margin_top(40)
            self.list_box.append(empty)
            return

        for c in captures:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(3)
            row.set_margin_bottom(3)

            lbl = Gtk.Label(label=c["text"])
            lbl.set_halign(Gtk.Align.START)
            lbl.set_ellipsize(3)
            lbl.set_hexpand(True)
            lbl.set_xalign(0)
            row.append(lbl)

            t = Gtk.Label(label=c["created_at"][11:16])
            t.add_css_class("empty-state")
            row.append(t)

            del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            del_btn.add_css_class("close-btn")
            del_btn.connect("clicked", self.on_delete, c["id"])
            row.append(del_btn)

            self.list_box.append(row)

    def on_delete(self, btn, cid):
        delete_capture(cid)
        self._load_captures()


# ─── Worries Page ──────────────────────────────────────────────
class WorriesPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        title = Gtk.Label(label="worry parking lot")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        subtitle = Gtk.Label(label="park it here so it stops bugging you.")
        subtitle.add_css_class("page-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        self.append(subtitle)

        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
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

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
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
            self.list_box.append(empty)
            return

        for w in worries:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(3)
            row.set_margin_bottom(3)

            cloud = Gtk.Label(label="☁")
            row.append(cloud)

            lbl = Gtk.Label(label=w["text"])
            lbl.set_halign(Gtk.Align.START)
            lbl.set_ellipsize(3)
            lbl.set_hexpand(True)
            lbl.set_xalign(0)
            row.append(lbl)

            dismiss = Gtk.Button(label="let go")
            dismiss.add_css_class("close-btn")
            dismiss.connect("clicked", self.on_dismiss, w["id"])
            row.append(dismiss)

            self.list_box.append(row)

    def on_dismiss(self, btn, wid):
        dismiss_worry(wid)
        self._load_worries()


# ─── Energy Page ───────────────────────────────────────────────
class EnergyPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        title = Gtk.Label(label="energy")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        self.energies = [("😫", "exhausted"), ("😕", "low"), ("😐", "meh"), ("🙂", "okay"), ("⚡", "wired")]

        energy_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        energy_box.set_halign(Gtk.Align.CENTER)

        for i, (emoji, label) in enumerate(self.energies, 1):
            btn = Gtk.Button(label=emoji)
            btn.add_css_class("energy-btn")
            btn.set_size_request(56, 56)
            btn.connect("clicked", self.on_energy, i)
            energy_box.append(btn)

        self.append(energy_box)

        today = get_today_energy()
        if today:
            emoji, label = self.energies[today["value"] - 1]
            tl = Gtk.Label(label=f"earlier: {emoji} {label}")
            tl.add_css_class("page-subtitle")
            tl.set_halign(Gtk.Align.CENTER)
            self.append(tl)

        section = Gtk.Label(label="recent")
        section.add_css_class("section-header")
        section.set_halign(Gtk.Align.START)
        self.append(section)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self.history_box)
        self.append(scroll)

        self._load_history()

    def on_energy(self, btn, value):
        add_energy(value)
        self._load_history()

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
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(8)
            row.set_margin_end(8)

            el = Gtk.Label(label=emoji)
            row.append(el)

            vl = Gtk.Label(label=f"{label} ({e['value']}/5)")
            vl.set_hexpand(True)
            vl.set_xalign(0)
            row.append(vl)

            tl = Gtk.Label(label=e["created_at"][11:16])
            tl.add_css_class("empty-state")
            row.append(tl)

            self.history_box.append(row)


# ─── Stats Page ────────────────────────────────────────────────
class StatsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        title = Gtk.Label(label="how you're doing")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        stats = get_stats()

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)

        self._add_stat(grid, 0, 0, str(stats["week_sessions"]), "this week")
        self._add_stat(grid, 1, 0, str(stats["total_sessions"]), "all time")
        self._add_stat(grid, 0, 1, str(stats["total_minutes"]), "minutes focused")
        self._add_stat(grid, 1, 1, str(stats["total_captures"]), "ideas captured")

        self.append(grid)

        count = stats["total_sessions"]
        msg = "you're here. that counts." if count == 0 else \
              "small numbers. still progress." if count < 5 else \
              "you're getting things done." if count < 20 else \
              "look at that. you've been busy."

        reassurance = Gtk.Label(label=msg)
        reassurance.add_css_class("reassurance")
        reassurance.set_halign(Gtk.Align.CENTER)
        reassurance.set_margin_top(20)
        self.append(reassurance)

    def _add_stat(self, grid, col, row, value, label):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("stat-card")
        card.set_size_request(140, 80)

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

        spacer1 = Gtk.Box()
        spacer1.set_vexpand(True)
        self.append(spacer1)

        title = Gtk.Label(label="breathe")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.CENTER)
        self.append(title)

        self.breath_circle = BreathingCircle(size=180)
        self.breath_circle.set_halign(Gtk.Align.CENTER)
        self.append(self.breath_circle)

        self.phase_label = Gtk.Label(label="ready")
        self.phase_label.add_css_class("breath-label")
        self.phase_label.set_halign(Gtk.Align.CENTER)
        self.append(self.phase_label)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.set_halign(Gtk.Align.CENTER)

        self.start_btn = Gtk.Button(label="begin")
        self.start_btn.add_css_class("teal-btn")
        self.start_btn.connect("clicked", self.on_toggle)
        controls.append(self.start_btn)
        self.append(controls)

        spacer2 = Gtk.Box()
        spacer2.set_vexpand(True)
        self.append(spacer2)

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
            if self.breath_timer:
                GLib.source_remove(self.breath_timer)
                self.breath_timer = None

    def _breath_cycle(self):
        if not self.running:
            return
        phases = [("inhale", 4000), ("hold", 4000), ("exhale", 4000)]
        self._run_phase(phases, 0)

    def _run_phase(self, phases, index):
        if not self.running:
            return
        if index >= len(phases):
            self.cycle_count += 1
            self._run_phase(phases, 0)
            return
        phase_name, duration = phases[index]
        self.breath_circle.set_phase(phase_name)
        self.phase_label.set_text(f"breathe {phase_name}")
        self.breath_timer = GLib.timeout_add(duration, lambda: self._run_phase(phases, index + 1))


# ─── Main Window ───────────────────────────────────────────────
class ZenithWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(900, 650)
        self.set_title("Zenith")

        # Setup keyboard shortcuts
        self._setup_shortcuts()

        # Create pages
        self.pages = {
            "todo": TodoPage(),
            "timer": TimerPage(),
            "dump": CapturePage(),
            "worries": WorriesPage(),
            "energy": EnergyPage(),
            "stats": StatsPage(),
            "breathe": BreathingPage(),
        }

        # Stack for page switching
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(200)
        for name, page in self.pages.items():
            self.stack.add_named(page, name)

        # Sidebar
        self.sidebar = Sidebar(self.on_nav)

        # Layout: sidebar + content
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        content.append(self.sidebar)
        content.append(self.stack)

        self.set_content(content)

    def _setup_shortcuts(self):
        """Global keyboard shortcuts."""
        controller = Gtk.ShortcutController()

        # Ctrl+Q = quit
        ctrl_q = Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>q"),
            action=Gtk.CallbackAction.new(lambda w, *a: Gtk.Application.get_default().quit()),
        )
        controller.add_shortcut(ctrl_q)

        # Ctrl+N = focus task entry
        ctrl_n = Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>n"),
            action=Gtk.CallbackAction.new(self._focus_task_entry),
        )
        controller.add_shortcut(ctrl_n)

        # Space = toggle timer when on timer page
        space = Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("space"),
            action=Gtk.CallbackAction.new(self._toggle_timer),
        )
        controller.add_shortcut(space)

        self.add_controller(controller)

    def _focus_task_entry(self, *args):
        if hasattr(self.pages["todo"], "task_entry"):
            self.stack.set_visible_child(self.pages["todo"])
            self.pages["todo"].task_entry.grab_focus()

    def _toggle_timer(self, *args):
        if self.stack.get_visible_child_name() == "timer":
            tp = self.pages["timer"]
            if tp.timer_running:
                tp.on_start(tp.start_btn)
            else:
                tp.on_start(tp.start_btn)

    def on_nav(self, page_id):
        self.stack.set_visible_child_name(page_id)


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
