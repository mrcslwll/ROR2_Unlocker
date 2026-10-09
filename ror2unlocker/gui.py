"""
The GUI. Deliberately, ironically retro: beveled gray Windows-98-style
chrome, Comic Sans everywhere, a scrolling marquee, and a hand-drawn
(not ripped from the game) "lunar bazaar" backdrop rendered straight onto
a Tk Canvas with rectangles, ovals and polygons.
"""

from __future__ import annotations

import random
import sys
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from . import data
from .game_scan import find_game_dir, scan_game
from .locator import ProfileInfo, list_profiles
from .save_manager import LUNAR_COINS_MAX, SaveFile, SaveFileError

FONT_FAMILY = "Comic Sans MS"
BEVEL_BG = "#c0c0c0"

WINDOW_W, WINDOW_H = 1040, 740


def F(size=10, weight="normal"):
    return (FONT_FAMILY, size, weight)


# ---------------------------------------------------------------------------
# Scrollable list container
# ---------------------------------------------------------------------------
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BEVEL_BG, **kw)
        self.canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        self.vbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg="white")

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._win, width=event.width)

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class _Tooltip:
    """Small hover popup used to explain '⚠ unconfirmed' catalog entries."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg="#ffffcc", fg="black",
                 relief="solid", bd=1, font=F(8), justify="left",
                 wraplength=380).pack()

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ---------------------------------------------------------------------------
# One tab's worth of checkbox rows for a category of Unlockables
# ---------------------------------------------------------------------------
class CategoryPanel(tk.Frame):
    def __init__(self, parent, app, category_name, items):
        super().__init__(parent, bg=BEVEL_BG)
        self.app = app
        self.category_name = category_name
        self.items = items
        self.vars: dict[str, tk.IntVar] = {}

        header = tk.Frame(self, bg=BEVEL_BG)
        header.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(
            header, text=f"{category_name}  ({len(items)} entries)",
            font=F(12, "bold"), bg=BEVEL_BG,
        ).pack(side="left")
        tk.Button(header, text="Select All", font=F(9), relief="raised",
                  command=self.select_all).pack(side="right", padx=2)
        tk.Button(header, text="Select None", font=F(9), relief="raised",
                  command=self.select_none).pack(side="right", padx=2)

        if any(not i.verified for i in items):
            tk.Label(
                self, bg=BEVEL_BG, fg="#a05a00", font=F(8),
                text="⚠ entries marked 'unconfirmed' are pattern-extrapolated IDs, not read "
                     "from the game -- hover one for details.",
            ).pack(fill="x", padx=8, anchor="w")
        elif any(i.achievement for i in items):
            tk.Label(
                self, bg=BEVEL_BG, fg="#555555", font=F(8),
                text="Every entry here was read straight from your installed game. Hover one "
                     "to see its real in-game challenge and unlock ID.",
            ).pack(fill="x", padx=8, anchor="w")

        self.scroll = ScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self._build_rows()

    def _build_rows(self):
        for item in self.items:
            var = tk.IntVar(value=0)
            self.vars[item.name] = var
            row = tk.Frame(self.scroll.inner, bg="white")
            row.pack(fill="x", anchor="w")
            label = item.name if item.verified else f"{item.name}  ⚠ unconfirmed"
            fg = "black" if item.verified else "#a05a00"
            cb = tk.Checkbutton(
                row, text=label, variable=var, bg="white", fg=fg,
                font=F(10), anchor="w", justify="left",
                command=lambda i=item, v=var: self._toggle(i, v),
            )
            cb.pack(side="left", fill="x", expand=True, anchor="w")
            if item.description:
                _Tooltip(cb, item.description)

    def _grant(self, item) -> None:
        """Apply an unlock, plus the survivor it belongs to if that's still locked."""
        sf = self.app.save_file
        sf.apply_unlockable(item)
        survivor = data.required_survivor(item)
        if survivor is not None and not sf.is_unlockable_granted(survivor):
            sf.apply_unlockable(survivor)
            self.app.log(f"Also unlocked {survivor.name} (needed to use {item.name})")
            self.app.refresh_all_panels()

    def _toggle(self, item, var):
        sf = self.app.save_file
        if sf is None:
            var.set(0)
            messagebox.showinfo("No save loaded", "Load a save file first (General tab).")
            return
        if var.get():
            self._grant(item)
            self.app.log(f"Unlocked: {item.name}")
        else:
            sf.revoke_unlockable(item)
            self.app.log(f"Re-locked: {item.name}")
        self.app.mark_dirty()

    def refresh_from_save(self):
        sf = self.app.save_file
        for item in self.items:
            var = self.vars[item.name]
            granted = bool(sf and sf.is_unlockable_granted(item))
            var.set(1 if granted else 0)

    def select_all(self):
        sf = self.app.save_file
        if sf is None:
            messagebox.showinfo("No save loaded", "Load a save file first (General tab).")
            return
        for item in self.items:
            self._grant(item)
            self.vars[item.name].set(1)
        self.app.log(f"Unlocked everything in: {self.category_name}")
        self.app.mark_dirty()

    def select_none(self):
        sf = self.app.save_file
        if sf is None:
            return
        for item in self.items:
            sf.revoke_unlockable(item)
            self.vars[item.name].set(0)
        self.app.log(f"Re-locked everything in: {self.category_name}")
        self.app.mark_dirty()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ROR2 Unlocker ™ -- Totally Legit Save Editor (2003 Edition)")
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.root.resizable(False, False)
        self.root.configure(bg="#301850")
        self._set_window_icon()

        self.save_file: SaveFile | None = None
        self.dirty = False
        self.category_panels: list[CategoryPanel] = []

        # Pick up anything a game update added since game_unlocks.py was
        # generated -- must happen before the tabs are built.
        scan_message = self._merge_installed_game_unlocks()

        self._build_background()
        self._build_panel()
        self._marquee_offset = WINDOW_W
        self._animate_marquee()
        self._blink_on = True
        self._animate_status_dot()

        self.log(scan_message)
        self._try_autoload()

    def _merge_installed_game_unlocks(self) -> str:
        try:
            game_dir = find_game_dir()
            if game_dir is None:
                return ("Risk of Rain 2 install not found -- using the built-in unlock list "
                        "(current as of Hallowed Concepts).")
            added = data.merge_game_scan(scan_game(game_dir))
        except (OSError, ValueError) as exc:
            return f"Couldn't scan the game install ({exc}) -- using the built-in unlock list."
        if not added:
            return f"Scanned {game_dir}: built-in unlock list is up to date with your game."
        names = ", ".join(i.name for i in added[:5]) + (" ..." if len(added) > 5 else "")
        return (f"Scanned {game_dir}: found {len(added)} unlock(s) newer than the built-in "
                f"list and added them automatically: {names}")

    def refresh_all_panels(self):
        for panel in self.category_panels:
            panel.refresh_from_save()

    # -- background art -------------------------------------------------
    def _set_window_icon(self):
        # Works both running from source and as a PyInstaller --onefile exe
        # (where bundled data lives under sys._MEIPASS at runtime).
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        icon_path = base / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except tk.TclError:
                pass

    def _build_background(self):
        self.bg_canvas = tk.Canvas(self.root, width=WINDOW_W, height=WINDOW_H,
                                    highlightthickness=0)
        self.bg_canvas.place(x=0, y=0)
        self._draw_bazaar(self.bg_canvas, WINDOW_W, WINDOW_H)

    @staticmethod
    def _lerp_color(c1, c2, t):
        r1, g1, b1 = c1
        r2, g2, b2 = c2
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _draw_bazaar(self, c: tk.Canvas, w: int, h: int):
        # sky gradient: deep indigo -> lunar violet -> dusty rose horizon
        top = (18, 8, 46)
        mid = (72, 30, 110)
        bottom = (168, 96, 130)
        horizon = int(h * 0.62)
        bands = 60
        for i in range(bands):
            t = i / bands
            y0 = int(t * horizon)
            y1 = int((i + 1) / bands * horizon)
            if t < 0.5:
                color = self._lerp_color(top, mid, t * 2)
            else:
                color = self._lerp_color(mid, bottom, (t - 0.5) * 2)
            c.create_rectangle(0, y0, w, y1, fill=color, outline=color)

        # ground
        ground_top = (70, 40, 70)
        ground_bottom = (30, 14, 34)
        gbands = 20
        for i in range(gbands):
            t = i / gbands
            y0 = horizon + int(t * (h - horizon))
            y1 = horizon + int((i + 1) / gbands * (h - horizon))
            color = self._lerp_color(ground_top, ground_bottom, t)
            c.create_rectangle(0, y0, w, y1, fill=color, outline=color)

        # stars
        rng = random.Random(1337)
        for _ in range(140):
            x = rng.randint(0, w)
            y = rng.randint(0, int(horizon * 0.85))
            r = rng.choice([1, 1, 1, 2])
            shade = rng.choice(["#ffffff", "#fff2c0", "#d9c8ff"])
            c.create_oval(x - r, y - r, x + r, y + r, fill=shade, outline="")

        # moon
        mx, my, mr = int(w * 0.82), int(h * 0.16), 62
        c.create_oval(mx - mr, my - mr, mx + mr, my + mr, fill="#f4ecd8", outline="#d8c9a0", width=2)
        for dx, dy, dr in [(-20, -10, 10), (15, 5, 14), (0, 25, 8), (-25, 20, 6)]:
            c.create_oval(mx + dx - dr, my + dy - dr, mx + dx + dr, my + dy + dr,
                           fill="#e0d3ae", outline="")

        # distant bazaar tents (silhouettes)
        tent_colors = ["#4a2f6b", "#5c3a80", "#3a2456"]
        rng2 = random.Random(7)
        for i in range(7):
            tw = rng2.randint(70, 120)
            tx = int(i * (w / 7) + rng2.randint(-15, 15))
            th = rng2.randint(90, 150)
            ty = horizon - th + rng2.randint(0, 20)
            color = tent_colors[i % len(tent_colors)]
            c.create_rectangle(tx, ty + th // 3, tx + tw, ty + th, fill=color, outline="")
            c.create_polygon(tx - 8, ty + th // 3, tx + tw + 8, ty + th // 3,
                              tx + tw // 2, ty, fill=color, outline="")
            flag_color = "#ffd76a" if i % 2 == 0 else "#7fe0d8"
            c.create_polygon(tx + tw // 2, ty, tx + tw // 2 + 14, ty + 8,
                              tx + tw // 2, ty + 16, fill=flag_color, outline="")

        # scattered lunar coins on the ground
        rng3 = random.Random(99)
        for _ in range(18):
            x = rng3.randint(20, w - 20)
            y = rng3.randint(horizon + 20, h - 20)
            r = rng3.randint(5, 9)
            c.create_oval(x - r, y - r, x + r, y + r, fill="#ffe08a", outline="#c9a84c", width=1)
            c.create_oval(x - r + 3, y - r + 3, x + r - 3, y + r - 3, outline="#c9a84c")

        # wooden sign
        sign_w, sign_h = 340, 56
        sx, sy = (w - sign_w) // 2, horizon - 20
        c.create_rectangle(sx, sy, sx + sign_w, sy + sign_h, fill="#5a3a20", outline="#2e1c10", width=3)
        c.create_text(sx + sign_w / 2, sy + sign_h / 2, text="✦ NEWT'S BAZAAR ✦",
                       font=(FONT_FAMILY, 20, "bold"), fill="#ffe9b0")

    # -- floating control panel ------------------------------------------
    def _build_panel(self):
        outer = tk.Frame(self.root, bg=BEVEL_BG, bd=4, relief="ridge")
        outer.place(x=20, y=20, width=WINDOW_W - 40, height=WINDOW_H - 40)

        self._build_marquee(outer)
        self._build_toolbar(outer)

        body = tk.Frame(outer, bg=BEVEL_BG)
        body.pack(fill="both", expand=True, padx=8, pady=(4, 4))

        self.tab_strip = tk.Frame(body, bg=BEVEL_BG)
        self.tab_strip.pack(fill="x")

        self.tab_container = tk.Frame(body, bg=BEVEL_BG, bd=2, relief="sunken")
        self.tab_container.pack(fill="both", expand=True, pady=(2, 0))

        self.tabs: dict[str, tk.Frame] = {}
        self.tab_buttons: dict[str, tk.Button] = {}
        self._build_general_tab()
        for cat_name, items in data.ALL_CATEGORIES.items():
            self._add_category_tab(cat_name, items)
        self._build_lab_tab()

        self._build_statusbar(outer)
        self.show_tab("General")

    def _build_marquee(self, parent):
        self.marquee_canvas = tk.Canvas(parent, height=28, bg="#101018", highlightthickness=0)
        self.marquee_canvas.pack(fill="x", padx=4, pady=(4, 0))
        self._marquee_text_id = self.marquee_canvas.create_text(
            0, 14,
            text="★ WELCOME TO THE R.O.R.2 UNLOCKER ★ 100% GUARANTEED* TO WORK "
                 "★ BEST VIEWED AT 800x600 ★ SITE UNDER CONSTRUCTION ★ "
                 "PLEASE BACK UP YOUR SAVE FIRST (WE DO IT AUTOMATICALLY, BUT STILL) ★",
            anchor="w", fill="#39ff14", font=F(11, "bold"),
        )

    def _animate_marquee(self):
        self.marquee_canvas.move(self._marquee_text_id, -2, 0)
        bbox = self.marquee_canvas.bbox(self._marquee_text_id)
        if bbox and bbox[2] < 0:
            self.marquee_canvas.coords(self._marquee_text_id, WINDOW_W, 14)
        self.root.after(30, self._animate_marquee)

    def _build_toolbar(self, parent):
        bar = tk.Frame(parent, bg=BEVEL_BG)
        bar.pack(fill="x", padx=6, pady=(4, 0))

        tk.Label(bar, text="Profile:", font=F(10, "bold"), bg=BEVEL_BG).pack(side="left")
        self.profile_var = tk.StringVar(value="")
        self.profile_combo = ttk.Combobox(
            bar, textvariable=self.profile_var, state="readonly",
            font=F(9), width=46, values=[],
        )
        self.profile_combo.pack(side="left", padx=4)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)

        tk.Button(bar, text="Rescan", font=F(9), command=self.rescan_profiles).pack(side="left", padx=2)
        tk.Button(bar, text="Browse for a file...", font=F(9), command=self.browse).pack(side="left", padx=2)
        tk.Button(bar, text="Reload", font=F(9), command=self.reload_save).pack(side="left", padx=2)

        path_bar = tk.Frame(parent, bg=BEVEL_BG)
        path_bar.pack(fill="x", padx=6, pady=(0, 4))
        self.path_var = tk.StringVar(value="(no save file loaded)")
        tk.Label(path_bar, textvariable=self.path_var, font=F(7), bg=BEVEL_BG,
                 fg="#555555", anchor="w").pack(side="left", fill="x", expand=True)

        self._profiles: list[ProfileInfo] = []

    def _build_statusbar(self, parent):
        bar = tk.Frame(parent, bg=BEVEL_BG, bd=2, relief="sunken")
        bar.pack(fill="x", side="bottom", padx=4, pady=(4, 4))
        self.dot_canvas = tk.Canvas(bar, width=14, height=14, bg=BEVEL_BG, highlightthickness=0)
        self.dot_canvas.pack(side="left", padx=4, pady=2)
        self.dot = self.dot_canvas.create_oval(2, 2, 12, 12, fill="#00c000", outline="")
        self.status_var = tk.StringVar(value="System Ready.")
        tk.Label(bar, textvariable=self.status_var, font=F(9), bg=BEVEL_BG, anchor="w").pack(
            side="left", fill="x", expand=True)

    def _animate_status_dot(self):
        self._blink_on = not self._blink_on
        color = "#00c000" if self._blink_on else "#003000"
        self.dot_canvas.itemconfig(self.dot, fill=color)
        self.root.after(600, self._animate_status_dot)

    # -- tabs -------------------------------------------------------------
    def _add_tab_button(self, name):
        btn = tk.Button(self.tab_strip, text=name, font=F(9, "bold"), relief="raised",
                         command=lambda n=name: self.show_tab(n))
        btn.pack(side="left", padx=1)
        self.tab_buttons[name] = btn

    def show_tab(self, name):
        for n, frame in self.tabs.items():
            frame.pack_forget()
            self.tab_buttons[n].configure(relief="raised", bg=BEVEL_BG)
        self.tabs[name].pack(fill="both", expand=True)
        self.tab_buttons[name].configure(relief="sunken", bg="#e0e0e0")

    def _add_category_tab(self, name, items):
        self._add_tab_button(name)
        panel = CategoryPanel(self.tab_container, self, name, items)
        self.tabs[name] = panel
        self.category_panels.append(panel)

    def _build_general_tab(self):
        self._add_tab_button("General")
        frame = tk.Frame(self.tab_container, bg=BEVEL_BG)
        self.tabs["General"] = frame

        info = tk.LabelFrame(frame, text="Profile", font=F(10, "bold"), bg=BEVEL_BG)
        info.pack(fill="x", padx=8, pady=6)
        self.profile_label = tk.Label(info, text="No save loaded yet.", font=F(10), bg=BEVEL_BG, anchor="w")
        self.profile_label.pack(fill="x", padx=6, pady=4)

        coins_frame = tk.LabelFrame(frame, text="Lunar Coins", font=F(10, "bold"), bg=BEVEL_BG)
        coins_frame.pack(fill="x", padx=8, pady=6)
        row1 = tk.Frame(coins_frame, bg=BEVEL_BG)
        row1.pack(fill="x")
        self.coins_var = tk.StringVar(value="0")
        tk.Entry(row1, textvariable=self.coins_var, font=F(11), width=14).pack(side="left", padx=6, pady=6)
        tk.Button(row1, text="Set Coins", font=F(9), command=self.set_coins).pack(side="left", padx=4)
        # Presets are capped at the real ceiling the save format can hold:
        # <coins> is a C# int32, so LUNAR_COINS_MAX (2,147,483,647) is the
        # highest value that won't overflow/corrupt in-game.
        for label, value in [
            ("10,000", 10_000),
            ("100,000", 100_000),
            ("999,999", 999_999),
            (f"MAX ({LUNAR_COINS_MAX:,})", LUNAR_COINS_MAX),
        ]:
            tk.Button(row1, text=label, font=F(9),
                      command=lambda v=value: self._set_coins_to(v)).pack(side="left", padx=2)
        tk.Label(
            coins_frame, bg=BEVEL_BG, fg="#555555", font=F(8), anchor="w",
            text=f"Coins are stored as a 32-bit number in the save file; the game itself "
                 f"cannot hold more than {LUNAR_COINS_MAX:,} without overflowing, so values "
                 f"are automatically clamped to that range.",
        ).pack(fill="x", padx=6, pady=(0, 4))

        big = tk.LabelFrame(frame, text="One-Click Nonsense", font=F(10, "bold"), bg=BEVEL_BG)
        big.pack(fill="x", padx=8, pady=6)
        tk.Button(
            big, text="☢ UNLOCK EVERYTHING ☢", font=F(14, "bold"),
            bg="#ffd700", activebackground="#ffe860", relief="raised", bd=4,
            command=self.unlock_everything,
        ).pack(side="left", padx=8, pady=8)
        tk.Button(
            big, text="Unlock All Achievements Only", font=F(10),
            command=self.unlock_all_achievements,
        ).pack(side="left", padx=8, pady=8)

        save_frame = tk.LabelFrame(frame, text="Save / Backup", font=F(10, "bold"), bg=BEVEL_BG)
        save_frame.pack(fill="x", padx=8, pady=6)
        tk.Button(save_frame, text="\U0001F4BE Save Changes to File", font=F(11, "bold"),
                  bg="#90ee90", command=self.save_changes).pack(side="left", padx=8, pady=8)
        tk.Button(save_frame, text="\U0001F195 Save As New Profile...", font=F(11, "bold"),
                  bg="#add8e6", command=self.save_as_new_profile).pack(side="left", padx=8, pady=8)
        tk.Button(save_frame, text="Restore Most Recent Backup", font=F(9),
                  command=self.restore_backup).pack(side="left", padx=8, pady=8)
        tk.Label(
            save_frame, bg=BEVEL_BG, fg="#555555", font=F(8),
            text="'Save As New Profile' writes everything you've changed into a brand-new "
                 "save file, so your original stays exactly as it was.",
        ).pack(side="left", padx=8)

        log_frame = tk.LabelFrame(frame, text="Activity Log", font=F(10, "bold"), bg=BEVEL_BG)
        log_frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.log_text = tk.Text(log_frame, height=10, bg="#101018", fg="#39ff14",
                                 font=(FONT_FAMILY, 9), insertbackground="#39ff14")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.log_text.configure(state="disabled")

        disclaimer = ("Tip: this tool edits your local save file only. Nothing is sent "
                      "anywhere. Steam Cloud will sync the edited file next time the game runs.")
        tk.Label(frame, text=disclaimer, font=F(8), bg=BEVEL_BG, fg="#555555",
                 wraplength=WINDOW_W - 80, justify="left").pack(fill="x", padx=8, pady=(0, 6))

    def _build_lab_tab(self):
        """
        A dedicated space for the unconfirmed Alloyed Collective guesses:
        one place to see every '⚠ unconfirmed' entry across all tabs, apply
        everything to a save the game will actually load, and record a
        verdict per item after checking in-game -- so the results are all
        sitting together in the Activity Log, ready to copy back into chat.
        """
        self._add_tab_button("🧪 DLC Lab")
        frame = tk.Frame(self.tab_container, bg=BEVEL_BG)
        self.tabs["🧪 DLC Lab"] = frame

        unverified = [i for i in data.all_unlockables() if not i.verified]

        header = tk.Frame(frame, bg=BEVEL_BG)
        header.pack(fill="x", padx=8, pady=6)
        tk.Label(
            header, bg=BEVEL_BG, font=F(9), justify="left", anchor="w",
            wraplength=WINDOW_W - 100,
            text=(
                f"Survivors, skills, skins, items and artifacts are now read straight from "
                f"your installed game, so none of them need testing. What's left below "
                f"({len(unverified)} entries) are Eclipse levels and stage logs, which the game "
                f"doesn't declare in a readable way -- their IDs are extrapolated from a real "
                f"save and still worth confirming.\n\n"
                f"Workflow: pick the profile you want to test with in the dropdown above, click "
                f"'Apply All Experimental Guesses' (unlocks everything, including these guesses, "
                f"into THAT profile -- a backup is made automatically), launch RoR2 with it, "
                f"check each one, then click ✅/❌ here so it lands in the Activity Log -- copy "
                f"that log back into chat and I'll fix the catalog.\n\n"
                f"⚠ This deliberately edits your existing, already-recognized profile rather than "
                f"creating a new one: testing showed Risk of Rain 2 reads its profile list from "
                f"Steam Cloud's own file manifest (userdata/.../632360/remotecache.vdf), not by "
                f"scanning the folder -- a brand-new file this app writes never gets added to "
                f"that manifest, so the game never sees it, no matter how it's named. Editing a "
                f"profile Steam already tracks sidesteps that entirely, and the automatic backup "
                f"keeps it reversible."
            ),
        ).pack(fill="x")
        tk.Button(
            header, text="\U0001F9EA Apply All Experimental Guesses to Current Profile",
            font=F(11, "bold"), bg="#ffb6c1", command=self._create_dlc_test_profile,
        ).pack(anchor="w", pady=(6, 0))

        scroll = ScrollableFrame(frame)
        scroll.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        for item in unverified:
            row = tk.Frame(scroll.inner, bg="white", bd=1, relief="groove")
            row.pack(fill="x", anchor="w", padx=2, pady=2)
            ids_text = " + ".join(item.unlocks)
            ach_text = f"  |  achievement: {item.achievement}" if item.achievement else ""
            tk.Label(row, text=f"{item.name}", font=F(10, "bold"), bg="white",
                     anchor="w", justify="left").pack(fill="x", padx=6, pady=(4, 0))
            tk.Label(row, text=f"{ids_text}{ach_text}", font=F(8), bg="white", fg="#555555",
                     anchor="w", justify="left", wraplength=WINDOW_W - 260).pack(
                fill="x", padx=6)
            if item.description:
                tk.Label(row, text=item.description, font=F(8), bg="white", fg="#a05a00",
                         anchor="w", justify="left", wraplength=WINDOW_W - 260).pack(
                    fill="x", padx=6, pady=(0, 4))
            btn_row = tk.Frame(row, bg="white")
            btn_row.pack(fill="x", padx=6, pady=(0, 6))
            tk.Button(btn_row, text="✅ Confirmed working", font=F(8),
                      command=lambda i=item: self._record_lab_verdict(i, True)).pack(side="left", padx=2)
            tk.Button(btn_row, text="❌ Did nothing", font=F(8),
                      command=lambda i=item: self._record_lab_verdict(i, False)).pack(side="left", padx=2)

    def _record_lab_verdict(self, item, works: bool):
        verdict = "WORKS" if works else "does NOT work"
        self.log(
            f"[DLC Lab result] {item.name}  ->  {verdict}  "
            f"(ids: {' + '.join(item.unlocks)}"
            + (f", achievement: {item.achievement}" if item.achievement else "")
            + ")"
        )

    def _create_dlc_test_profile(self):
        if not self._require_save():
            return
        profile_name = self.save_file.profile_name
        if not messagebox.askyesno(
            "Apply Experimental Guesses",
            f"This unlocks everything -- including every unconfirmed Alloyed "
            f"Collective guess -- directly on the CURRENTLY LOADED profile "
            f"('{profile_name}') and writes it to disk right away, so Risk of "
            f"Rain 2 will actually recognize it. A timestamped backup of the "
            f"current file is made automatically first (Restore Most Recent "
            f"Backup on the General tab undoes this).\n\n"
            f"Switch profiles first (top of the window) if this isn't the "
            f"one you want to test with. Continue?",
        ):
            return
        for item in data.all_unlockables():
            self.save_file.apply_unlockable(item)
        for ach in data.all_achievement_ids():
            self.save_file.add_achievement(ach)
        for panel in self.category_panels:
            panel.refresh_from_save()
        self.log("Applied every unlock (including unconfirmed guesses) for DLC testing.")
        self.save_changes()

    # -- logging / status --------------------------------------------------
    def log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"> {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.status_var.set(message)

    def mark_dirty(self):
        self.dirty = True
        self.status_var.set("Unsaved changes -- click 'Save Changes to File' when ready.")

    # -- save file lifecycle -----------------------------------------------
    def _try_autoload(self):
        self.rescan_profiles(select_first=True, silent_if_empty=True)

    def rescan_profiles(self, select_first: bool = False, silent_if_empty: bool = False):
        """Re-run detection and repopulate the Profile dropdown by name."""
        self.status_var.set("Scanning for save files...")
        self.root.update_idletasks()
        profiles = list_profiles()
        self._profiles = profiles

        if not profiles:
            self.profile_combo.configure(values=[])
            self.profile_var.set("")
            if silent_if_empty:
                self.log("No save file auto-detected. Use Rescan or Browse to locate one.")
            else:
                messagebox.showwarning(
                    "Not found",
                    "Couldn't find a Risk of Rain 2 save automatically, even after "
                    "checking common Steam locations on every drive.\n\n"
                    "Use 'Browse for a file...' and pick your UserProfile*.xml by hand. "
                    "It's normally in:\n"
                    r"Steam\userdata\<your id>\632360\remote\UserProfiles",
                )
            return

        labels = [p.label for p in profiles]
        self.profile_combo.configure(values=labels)
        self.log(f"Found {len(profiles)} profile(s): {', '.join(p.name for p in profiles)}")

        if select_first:
            self.profile_var.set(labels[0])
            self._load_profile(profiles[0])

    def _on_profile_selected(self, _event=None):
        label = self.profile_var.get()
        for p in self._profiles:
            if p.label == label:
                self._load_profile(p)
                return

    def browse(self):
        path = filedialog.askopenfilename(
            title="Select your RoR2 UserProfile save file",
            filetypes=[("XML save files", "*.xml"), ("All files", "*.*")],
        )
        if path:
            path = Path(path)
            self._load_path(path)
            # fold this manually-chosen file into the profile list too, so
            # switching back to it later doesn't require Browse again.
            name = self.save_file.profile_name if self.save_file else path.stem
            info = ProfileInfo(name=name, path=path)
            if info.label not in self.profile_combo["values"]:
                self.profile_combo.configure(values=[*self.profile_combo["values"], info.label])
                self._profiles.append(info)
            self.profile_var.set(info.label)

    def reload_save(self):
        if self.save_file:
            self._load_path(self.save_file.path)
        else:
            self.log("Nothing to reload -- no save file loaded yet.")

    def _load_profile(self, profile: ProfileInfo):
        self._load_path(profile.path)

    def _load_path(self, path: Path):
        try:
            self.save_file = SaveFile(path)
        except SaveFileError as exc:
            messagebox.showerror("Couldn't load save", str(exc))
            self.log(f"Failed to load {path}: {exc}")
            return
        except OSError as exc:
            messagebox.showerror("Couldn't load save", str(exc))
            return

        self.path_var.set(str(path))
        self.coins_var.set(str(self.save_file.get_coins()))
        self.profile_label.configure(
            text=f"Profile: {self.save_file.profile_name}    |    File: {path.name}"
        )
        self.dirty = False
        self.log(f"Loaded save file: {path}")
        for panel in self.category_panels:
            panel.refresh_from_save()

    # -- actions -----------------------------------------------------------
    def _require_save(self) -> bool:
        if self.save_file is None:
            messagebox.showinfo("No save loaded", "Load a save file first (see the General tab).")
            return False
        return True

    def set_coins(self):
        if not self._require_save():
            return
        try:
            value = int(self.coins_var.get().replace(",", "").strip())
        except ValueError:
            messagebox.showerror("Invalid number", "Lunar Coins must be a whole number.")
            return
        if value > LUNAR_COINS_MAX or value < 0:
            messagebox.showinfo(
                "Clamped",
                f"Risk of Rain 2 stores Lunar Coins as a 32-bit number, so it cannot go "
                f"below 0 or above {LUNAR_COINS_MAX:,}. Your value has been clamped to fit.",
            )
        self.save_file.set_coins(value)
        self.coins_var.set(str(self.save_file.get_coins()))
        self.log(f"Set Lunar Coins to {self.save_file.get_coins():,}")
        self.mark_dirty()

    def _set_coins_to(self, value: int):
        if not self._require_save():
            return
        self.save_file.set_coins(value)
        self.coins_var.set(str(self.save_file.get_coins()))
        self.log(f"Set Lunar Coins to {self.save_file.get_coins():,}")
        self.mark_dirty()
        self.mark_dirty()

    def unlock_all_achievements(self):
        if not self._require_save():
            return
        count = 0
        for ach in data.all_achievement_ids():
            if ach not in self.save_file.get_achievements():
                self.save_file.add_achievement(ach)
                count += 1
        self.log(f"Granted {count} achievements.")
        self.mark_dirty()

    def unlock_everything(self):
        if not self._require_save():
            return
        if not messagebox.askyesno(
            "Unlock Everything",
            "This will unlock every survivor, skill, skin, item, artifact, logbook "
            "entry and Newt altar, and grant every achievement.\n\n"
            "A backup of your current save is made automatically before saving. Proceed?",
        ):
            return
        total = 0
        for item in data.all_unlockables():
            self.save_file.apply_unlockable(item)
            total += 1
        for ach in data.all_achievement_ids():
            self.save_file.add_achievement(ach)
        for panel in self.category_panels:
            panel.refresh_from_save()
        self.log(f"UNLOCKED EVERYTHING. {total} unlockables granted, all achievements marked complete.")
        self.mark_dirty()

    def save_changes(self):
        if not self._require_save():
            return
        try:
            backup = self.save_file.save(make_backup=True)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            self.log(f"Save failed: {exc}")
            return
        self.dirty = False
        msg = "Save written to disk."
        if backup:
            msg += f" Backup created: {backup.name}"
        self.log(msg)
        self.status_var.set("Saved. Close and reopen Risk of Rain 2 to see changes.")
        messagebox.showinfo("Saved", msg + "\n\nMake sure Risk of Rain 2 is closed before "
                                            "(re)launching it so Steam Cloud doesn't overwrite this.")

    def save_as_new_profile(self):
        """
        Write everything currently staged in memory out as a brand-new save
        file (new random filename, in the same UserProfiles folder the
        game itself uses by default), leaving the loaded original alone.

        Caveat confirmed by testing: Risk of Rain 2 builds its profile list
        from Steam Cloud's own file manifest (remotecache.vdf), not by
        scanning the folder. A file written here directly never gets added
        to that manifest, so the game will not show it as a profile option
        -- no matter what it's named or how long you wait. This is still
        useful for keeping an edited copy on disk (e.g. to import elsewhere,
        or in case Valve/Hopoo change that behavior), but for a save you
        actually want to load in-game, edit an existing, already-recognized
        profile instead (Save Changes to File) or see the README for a
        workaround.
        """
        if not self._require_save():
            return

        default_name = f"{self.save_file.profile_name} (Edited)"
        default_dir = self.save_file.path.parent

        dialog = tk.Toplevel(self.root)
        dialog.title("Save As New Profile")
        dialog.configure(bg=BEVEL_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(
            dialog, bg=BEVEL_BG, fg="#a05a00", font=F(8), justify="left", anchor="w",
            wraplength=420,
            text="⚠ Testing shows Risk of Rain 2 will likely NOT list this new file as a "
                 "loadable profile -- it reads its profile list from Steam Cloud's own file "
                 "manifest, not the folder, and a file written directly here never gets added "
                 "to it. To edit a save the game will actually load, use 'Save Changes to "
                 "File' on an existing profile instead. See the README for a possible "
                 "workaround.",
        ).pack(padx=12, pady=(12, 4), fill="x")

        tk.Label(dialog, text="New profile name:", font=F(10, "bold"), bg=BEVEL_BG).pack(
            padx=12, pady=(4, 2), anchor="w")
        name_var = tk.StringVar(value=default_name)
        tk.Entry(dialog, textvariable=name_var, font=F(10), width=42).pack(
            padx=12, pady=(0, 8), fill="x")

        dest_var = tk.StringVar(value=str(default_dir / f"{uuid.uuid4()}.xml"))
        tk.Label(dialog, text="Will be created as a new save file here:", font=F(9),
                 bg=BEVEL_BG).pack(padx=12, anchor="w")
        tk.Label(dialog, textvariable=dest_var, font=F(8), bg=BEVEL_BG, fg="#555555",
                 wraplength=420, justify="left").pack(padx=12, pady=(0, 4), fill="x")

        def choose_location():
            path = filedialog.asksaveasfilename(
                title="Choose where to create the new save file",
                initialdir=str(default_dir),
                initialfile=Path(dest_var.get()).name,
                defaultextension=".xml",
                filetypes=[("XML save files", "*.xml")],
            )
            if path:
                dest_var.set(path)

        tk.Button(dialog, text="Choose a different location...", font=F(9),
                  command=choose_location).pack(padx=12, pady=(0, 8), anchor="w")

        btn_row = tk.Frame(dialog, bg=BEVEL_BG)
        btn_row.pack(padx=12, pady=(0, 12), fill="x")

        def do_create():
            new_path = Path(dest_var.get())
            new_name = name_var.get().strip() or default_name
            if new_path.exists() and not messagebox.askyesno(
                "File exists", f"{new_path.name} already exists. Overwrite it?"
            ):
                return
            original_name = self.save_file.profile_name
            try:
                self.save_file.set_profile_name(new_name)
                self.save_file.save_as(new_path)
            except OSError as exc:
                messagebox.showerror("Couldn't create file", str(exc))
                return
            finally:
                # don't rename the still-loaded original in memory
                self.save_file.set_profile_name(original_name)

            dialog.destroy()
            info = ProfileInfo(name=new_name, path=new_path)
            self.profile_combo.configure(values=[*self.profile_combo["values"], info.label])
            self._profiles.append(info)
            self.log(f"Created new save file '{new_name}' at {new_path}")
            if messagebox.askyesno(
                "Switch profile?", f"'{new_name}' was created.\n\nSwitch to editing it now?"
            ):
                self.profile_var.set(info.label)
                self._load_path(new_path)

        tk.Button(btn_row, text="Create", font=F(10, "bold"), bg="#90ee90",
                  command=do_create).pack(side="right", padx=4)
        tk.Button(btn_row, text="Cancel", font=F(9), command=dialog.destroy).pack(side="right", padx=4)

    def restore_backup(self):
        if not self._require_save():
            return
        backups = sorted(
            self.save_file.path.parent.glob(f"{self.save_file.path.stem}.backup_*{self.save_file.path.suffix}")
        )
        if not backups:
            messagebox.showinfo("No backups", "No backups found next to this save file yet.")
            return
        latest = backups[-1]
        if not messagebox.askyesno(
            "Restore Backup",
            f"Restore this backup?\n\n{latest.name}\n\nThis overwrites the current save file on disk."
        ):
            return
        import shutil
        shutil.copy2(latest, self.save_file.path)
        self._load_path(self.save_file.path)
        self.log(f"Restored backup: {latest.name}")

    # -- run -----------------------------------------------------------------
    def run(self):
        self.root.mainloop()


def main():
    App().run()
