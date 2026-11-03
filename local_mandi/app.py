"""Lightweight resident Windows GUI for the PC mandi publisher."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from feeder import sync, FeedError, Cancelled

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / ".runtime"


class App:
    def __init__(self, root, autostart=False):
        self.root, self.events = root, queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        self.running = False
        self.next_run = 0
        self.closing = False
        RUNTIME.mkdir(exist_ok=True)
        self.logger = logging.getLogger("mandi-pc")
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(RUNTIME / "service.log", maxBytes=250000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(handler)
        settings = {"states": "West Bengal, Uttar Pradesh", "minutes": "180"}
        try:
            settings.update(json.loads((RUNTIME / "settings.json").read_text()))
        except (OSError, ValueError):
            pass
        root.title("AnnaData • Mandi Price Publisher")
        root.geometry("800x570")
        root.minsize(690, 480)
        root.protocol("WM_DELETE_WINDOW", root.iconify)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f5f7f3")
        style.configure("TLabel", background="#f5f7f3", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#24513a")
        style.configure("TButton", padding=9)
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Mandi Price Publisher", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Your PC → official prices → Neon → AnnaData", padding=(0, 5, 0, 15)).pack(anchor="w")
        self.status = tk.StringVar(value="Stopped — no automatic refreshes")
        self.last = tk.StringVar(value="Last successful refresh: not yet")
        self.next = tk.StringVar(value="Next refresh: —")
        for value in (self.status, self.last, self.next):
            ttk.Label(frame, textvariable=value, wraplength=735).pack(anchor="w", pady=3)
        settings_frame = ttk.Frame(frame, padding=(0, 15))
        settings_frame.pack(fill="x")
        self.states = tk.StringVar(value=settings["states"])
        self.minutes = tk.StringVar(value=str(settings["minutes"]))
        ttk.Label(settings_frame, text="States (comma separated)").grid(row=0, column=0, sticky="w")
        ttk.Label(settings_frame, text="Refresh every (minutes)").grid(row=0, column=1, padx=12, sticky="w")
        self.state_entry = ttk.Entry(settings_frame, textvariable=self.states, width=48)
        self.state_entry.grid(row=1, column=0, sticky="ew", pady=5)
        self.interval_entry = ttk.Spinbox(settings_frame, from_=15, to=1440, textvariable=self.minutes, width=12)
        self.interval_entry.grid(row=1, column=1, padx=12, pady=5, sticky="w")
        settings_frame.columnconfigure(0, weight=1)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(0, 14))
        self.start_button = ttk.Button(buttons, text="Start service", command=self.start)
        self.start_button.pack(side="left")
        ttk.Button(buttons, text="Stop service", command=self.pause).pack(side="left", padx=6)
        self.refresh_button = ttk.Button(buttons, text="Refresh now", command=self.refresh)
        self.refresh_button.pack(side="left")
        ttk.Button(buttons, text="Quit", command=self.quit).pack(side="right")
        self.logbox = tk.Text(frame, height=12, wrap="word", font=("Consolas", 10), bg="#ffffff", relief="flat", state="disabled")
        self.logbox.pack(fill="both", expand=True)
        ttk.Label(frame, text="Closing the window minimizes it. Quit stops the app. Your PC must stay awake and online.", wraplength=735).pack(anchor="w", pady=(12, 0))
        self.root.after(200, self.tick)
        if autostart:
            self.root.after(400, self.start)

    def configuration(self):
        states = [s.strip() for s in self.states.get().split(",") if s.strip()]
        try:
            minutes = int(self.minutes.get())
            if not 15 <= minutes <= 1440 or not states:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Check settings", "Enter at least one state and a refresh interval from 15 to 1440 minutes.")
            return None
        (RUNTIME / "settings.json").write_text(json.dumps({"states": self.states.get(), "minutes": minutes}), encoding="utf-8")
        return states, minutes

    def log(self, text):
        self.events.put(("log", text))

    def start(self):
        if self.closing or not self.configuration():
            return
        self.running = True
        self.start_button.configure(state="disabled")
        self.refresh()

    def pause(self):
        self.running = False
        self.stop.set()
        self.next_run = 0
        self.start_button.configure(state="normal")
        self.status.set("Stopping after the current network operation…" if self.worker and self.worker.is_alive() else "Stopped")

    def refresh(self):
        if self.closing or (self.worker and self.worker.is_alive()):
            return
        config = self.configuration()
        if not config:
            self.pause()
            return
        states, minutes = config
        self.stop.clear()
        self.status.set("Refreshing official prices…")
        self.refresh_button.configure(state="disabled")
        self.state_entry.configure(state="disabled")
        self.interval_entry.configure(state="disabled")

        def work():
            try:
                result = sync(states, self.stop, self.log)
                self.events.put(("done", (result, minutes)))
            except FeedError as exc:
                self.log(str(exc))
                self.events.put(("done", ({"results": [], "errors": [str(exc)]}, minutes)))
            except Exception:
                self.log("Unexpected refresh error. No credentials are written to this log.")
                self.events.put(("done", ({"results": [], "errors": ["Unexpected refresh error"]}, minutes)))
        self.worker = threading.Thread(target=work, name="mandi-publisher", daemon=True)
        self.worker.start()

    def quit(self):
        self.closing = True
        self.pause()
        self.status.set("Stopping safely before exit…")

    def tick(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.logger.info(value)
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", time.strftime("%H:%M:%S ") + value + "\n")
                    if int(self.logbox.index("end-1c").split(".")[0]) > 300:
                        self.logbox.delete("1.0", "50.0")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "done":
                    result, minutes = value
                    (RUNTIME / "status.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                    if result["results"]:
                        total = sum(x["rows"] for x in result["results"])
                        self.last.set(f"Last successful publication: {time.strftime('%d %b %H:%M')} • {total} prices • " + ", ".join(x["state"] for x in result["results"]))
                    self.status.set(("Running" if self.running else "Stopped") + (" — refresh had errors; see log" if result["errors"] else " — refresh completed"))
                    self.next_run = time.time() + minutes * 60 if self.running else 0
                    self.refresh_button.configure(state="normal")
                    self.state_entry.configure(state="normal")
                    self.interval_entry.configure(state="normal")
        except queue.Empty:
            pass
        busy = self.worker and self.worker.is_alive()
        if self.closing and not busy:
            self.root.destroy()
            return
        if self.running and self.next_run and time.time() >= self.next_run and not busy:
            self.refresh()
        self.next.set("Next refresh: " + (time.strftime("%d %b %H:%M", time.localtime(self.next_run)) if self.running and self.next_run else "—"))
        self.root.after(300, self.tick)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--autostart", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--states", default="West Bengal,Uttar Pradesh")
    args = parser.parse_args()
    if args.once or args.dry_run:
        result = sync(args.states.split(","), dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 1 if result["errors"] else 0
    # Windows exclusive bind prevents overlapping GUI publishers. No listener.
    guard = socket.socket()
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        guard.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        guard.bind(("127.0.0.1", 47863))
    except OSError:
        root = tk.Tk(); root.withdraw()
        messagebox.showinfo("AnnaData", "The publisher is already open, or its local lock port is in use. Check the taskbar.")
        root.destroy()
        return 1
    root = tk.Tk()
    App(root, args.autostart)
    try:
        root.mainloop()
    finally:
        guard.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
