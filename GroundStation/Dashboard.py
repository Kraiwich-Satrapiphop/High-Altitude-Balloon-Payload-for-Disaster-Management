# Ground Station Monitoring Dashboard
#
# 4 panels:  Camera Image | GPS Map (OpenStreetMap)
#            Flight Data  | Control Panel
#
# Usage:
#   python Dashboard.py                  (default IP 127.0.0.1)
#   python Dashboard.py 192.168.1.10     (override server IP)

import tkinter as tk
from tkinter import ttk
import threading
import time
import pickle
import socket
import os
import sys
import numpy as np
import cv2
from datetime import datetime
from PIL import Image, ImageTk
import tkintermapview
import geocoder
import math

import csv

import Create_Unique_Folder as CUF
import SystemLogger as SL

CSV_HEADER = (
    "Uptime,Timestamp,UTC date time,Fix type,"
    "Latitude (degrees),Longtitude (degrees),"
    "Positional dilution of precision,"
    "Altitude (m) above Mean Sea Level,Ground speed (km/h),"
    "Satellites in view,Altitude (m) above elipsoid,"
    "Temperature Board,Temperature Ext LM75,Temperature Ext MS8607,"
    "Pressure Ext (hPa) MS8607,Humidity (%) MS8607,"
    "Light Intensity Clear (lx),Light Intensity Red (lx),"
    "Light Intensity Green (lx),Light Intensity Blue (lx),"
    "Light Intensity Infrared (lx),Light Intensity UVA,"
    "Supply Voltage (V),3.3 V board voltage,5 V board voltage,"
    "Vin1 voltage,Vin2 voltage,Vin3 voltage,"
    "In 1 State,In 1 Timestamp (s),In 2 State,In 2 Timestamp (s),"
    "Out 1 State,Out 1 Timestamp (s),Out 2 State,Out 2 Timestamp (s)"
)

# ── Network config ─────────────────────────────────────────────────────────────
SERVER_IP   = "192.168.144.157"
SERVER_PORT = 8081
BUFFER_SIZE = 256
TIMEOUT_SEC = 20

AUTO_INTERVAL_DEFAULT = 30   # seconds

# ── GPS default (used when no fix received) ────────────────────────────────────
DEFAULT_LAT = -37.8002
DEFAULT_LON = 144.9648

# ── Data field indices (matches TCPClient CSV header order) ───────────────────
F_UPTIME    = 0
F_TIMESTAMP = 1
F_FIX       = 3
F_LAT       = 4
F_LON       = 5
F_PDOP      = 6
F_ALT       = 7
F_SPEED     = 8
F_SATS      = 9
F_T_BOARD   = 11
F_T_LM75    = 12
F_T_MS      = 13
F_PRESSURE  = 14
F_HUMIDITY  = 15
F_V_SUPPLY  = 22
F_V33       = 23
F_V5        = 24

# ── Colour palette ─────────────────────────────────────────────────────────────
C_BG       = "#12121e"
C_PANEL    = "#1a1a2e"
C_HEADER   = "#16213e"
C_WIDGET   = "#0f3460"
C_TEXT     = "#dde1e7"
C_DIM      = "#6b7280"
C_BLUE     = "#64b5f6"
C_GREEN    = "#4ade80"
C_YELLOW   = "#facc15"
C_RED      = "#f87171"
C_ORANGE   = "#fb923c"
C_ACCENT   = "#e94560"
C_TRACK    = "#5e81ac"


# ── TCP helpers ────────────────────────────────────────────────────────────────
def _send_cmd(ip, cmd):
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    soc.settimeout(TIMEOUT_SEC)
    soc.connect((ip, SERVER_PORT))
    soc.sendall(pickle.dumps(cmd))
    return soc


def _recv_data(soc):
    raw_len  = soc.recv(BUFFER_SIZE).decode("utf-8")
    expected = int(raw_len)
    soc.sendall("d".encode("utf-8"))
    buf = b""
    while len(buf) < expected:
        chunk = soc.recv(BUFFER_SIZE)
        if not chunk:
            break
        buf += chunk
    return pickle.loads(buf)


# ── Helper: thin separator line ────────────────────────────────────────────────
def _sep(parent):
    tk.Frame(parent, bg=C_WIDGET, height=1).pack(fill=tk.X, padx=10, pady=6)


# ── Dashboard ──────────────────────────────────────────────────────────────────
class Dashboard:

    def __init__(self, root, ip, folder_path, logger):
        self.root        = root
        self.ip          = ip
        self.folder_path = folder_path
        self.logger      = logger
        self.csv_path    = folder_path + "/Data.csv"
        with open(self.csv_path, "w", newline="") as f:
            f.write("\nRecoreded Data from the Datalogger\n\n")
            f.write(CSV_HEADER + "\n")

        self.mode          = tk.StringVar(value="manual")
        self.auto_interval = tk.IntVar(value=AUTO_INTERVAL_DEFAULT)
        self._stop_auto    = threading.Event()
        self._fetch_lock   = threading.Lock()
        self.gps_history   = []          # [(lat, lon), ...]

        # map widget state — payload
        self._map_start_marker   = None
        self._map_current_marker = None
        self._map_path           = None

        # map widget state — ground station
        self._map_gs_marker = None
        self._map_gs_line   = None
        self._gs_lat        = None
        self._gs_lon        = None

        self._build_ui()
        self._init_map()

    # ── UI Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.title("Ground Station Dashboard")
        self.root.configure(bg=C_BG)
        self.root.geometry("1440x900")
        self.root.minsize(1100, 720)

        self._build_titlebar()

        grid = tk.Frame(self.root, bg=C_BG)
        grid.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        grid.columnconfigure(0, weight=55)
        grid.columnconfigure(1, weight=45)
        grid.rowconfigure(0, weight=70)
        grid.rowconfigure(1, weight=30)

        self._build_image_panel(grid)
        self._build_map_panel(grid)
        self._build_data_panel(grid)
        self._build_control_panel(grid)

    # ── Title bar ──────────────────────────────────────────────────────────────

    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=C_ACCENT, height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        tk.Label(bar, text="  GROUND STATION  |  HAB MONITORING SYSTEM",
                 bg=C_ACCENT, fg="white",
                 font=("Consolas", 12, "bold")).pack(side=tk.LEFT, padx=12, pady=6)

        self._clock_var = tk.StringVar()
        tk.Label(bar, textvariable=self._clock_var, bg=C_ACCENT, fg="white",
                 font=("Consolas", 11)).pack(side=tk.RIGHT, padx=14)
        self._tick_clock()

    def _tick_clock(self):
        self._clock_var.set(datetime.now().strftime("%Y-%m-%d   %H:%M:%S   "))
        self.root.after(1000, self._tick_clock)

    # ── Panel factory ──────────────────────────────────────────────────────────

    def _make_panel(self, parent, title, row, col):
        outer = tk.Frame(parent, bg=C_PANEL, bd=0)
        outer.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
        outer.grid_propagate(False)   # lock panel size — prevent content changes from resizing the grid
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        hdr = tk.Frame(outer, bg=C_HEADER, height=26)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        tk.Label(hdr, text=f"  {title}", bg=C_HEADER, fg=C_BLUE,
                 font=("Consolas", 9, "bold")).pack(side=tk.LEFT, pady=3)

        body = tk.Frame(outer, bg=C_PANEL)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        return body, hdr

    # ── Panel 1: Camera image ──────────────────────────────────────────────────

    def _build_image_panel(self, parent):
        body, hdr = self._make_panel(parent, "CAMERA  |  SpaceCam", 0, 0)

        self._img_ts_var = tk.StringVar(value="No image received")
        tk.Label(hdr, textvariable=self._img_ts_var, bg=C_HEADER,
                 fg=C_DIM, font=("Consolas", 8)).pack(side=tk.RIGHT, padx=10)

        self._img_label = tk.Label(body, bg=C_PANEL,
                                   text="Waiting for image...",
                                   fg=C_DIM, font=("Consolas", 11))
        self._img_label.grid(row=0, column=0, sticky="nsew")
        body.grid_propagate(False)   # image load must not push panel boundaries

    # ── Panel 2: GPS map (OpenStreetMap) ───────────────────────────────────────

    def _build_map_panel(self, parent):
        body, hdr = self._make_panel(parent, "GPS TRACK  |  OpenStreetMap", 0, 1)

        self._map_pos_var = tk.StringVar(value="Waiting for GPS fix...")
        tk.Label(hdr, textvariable=self._map_pos_var, bg=C_HEADER,
                 fg=C_DIM, font=("Consolas", 8)).pack(side=tk.RIGHT, padx=10)

        self._map_widget = tkintermapview.TkinterMapView(
            body, corner_radius=0)
        self._map_widget.grid(row=0, column=0, sticky="nsew")

    def _init_map(self):
        self._map_widget.set_position(DEFAULT_LAT, DEFAULT_LON)
        self._map_widget.set_zoom(15)

    # ── Panel 3: Flight data ───────────────────────────────────────────────────

    def _build_data_panel(self, parent):
        body, _ = self._make_panel(parent, "FLIGHT DATA", 1, 0)
        body.columnconfigure((0, 1, 2, 3), weight=1)
        body.rowconfigure(0, weight=1)

        self._dv = {}   # key -> (StringVar, Label, fmt)

        sections = [
            ("GPS", [
                ("Latitude",    "lat",     F_LAT,      "%.5f", "deg"),
                ("Longitude",   "lon",     F_LON,      "%.5f", "deg"),
                ("Altitude",    "alt",     F_ALT,      "%.1f",  "m"),
                ("Speed",       "speed",   F_SPEED,    "%.1f",  "km/h"),
                ("Satellites",  "sats",    F_SATS,     None,    ""),
                ("Fix Type",    "fix",     F_FIX,      None,    ""),
                ("PDOP",        "pdop",    F_PDOP,     "%.2f",  ""),
            ]),
            ("ENVIRONMENT", [
                ("Temp Board",  "t_board", F_T_BOARD,  "%.1f", "C"),
                ("Temp LM75",   "t_lm75",  F_T_LM75,   "%.1f", "C"),
                ("Temp MS8607", "t_ms",    F_T_MS,     "%.1f", "C"),
                ("Pressure",    "pres",    F_PRESSURE, "%.1f", "hPa"),
                ("Humidity",    "hum",     F_HUMIDITY, "%.1f", "%"),
            ]),
            ("POWER", [
                ("Supply V",    "v_sup",   F_V_SUPPLY, "%.2f", "V"),
                ("3.3 V Rail",  "v33",     F_V33,      "%.2f", "V"),
                ("5 V Rail",    "v5",      F_V5,       "%.2f", "V"),
            ]),
            ("SYSTEM", [
                ("Uptime",      "uptime",  F_UPTIME,    None, "s"),
                ("Timestamp",   "ts",      F_TIMESTAMP, None, ""),
            ]),
        ]

        for col_idx, (sec_name, fields) in enumerate(sections):
            col_frame = tk.Frame(body, bg=C_PANEL)
            col_frame.grid(row=0, column=col_idx, sticky="nsew", padx=5, pady=6)

            tk.Label(col_frame, text=sec_name, bg=C_PANEL, fg=C_ACCENT,
                     font=("Consolas", 9, "bold")).pack(anchor=tk.W, pady=(2, 5))

            for label, key, _, fmt, unit in fields:
                row_f = tk.Frame(col_frame, bg=C_PANEL)
                row_f.pack(fill=tk.X, pady=2)

                tk.Label(row_f, text=f"{label}:", bg=C_PANEL, fg=C_DIM,
                         font=("Consolas", 8), width=11,
                         anchor=tk.W).pack(side=tk.LEFT)

                var = tk.StringVar(value="--")
                val_lbl = tk.Label(row_f, textvariable=var, bg=C_PANEL,
                                   fg=C_TEXT, font=("Consolas", 9, "bold"),
                                   anchor=tk.W, width=10)
                val_lbl.pack(side=tk.LEFT)

                if unit:
                    tk.Label(row_f, text=f" {unit}", bg=C_PANEL, fg=C_DIM,
                             font=("Consolas", 8)).pack(side=tk.LEFT)

                self._dv[key] = (var, val_lbl, fmt)

    # ── Panel 4: Control panel (two-column compact layout) ────────────────────

    def _build_control_panel(self, parent):
        body, _ = self._make_panel(parent, "CONTROL PANEL", 1, 1)

        # Two equal columns inside the panel
        outer = tk.Frame(body, bg=C_PANEL)
        outer.grid(row=0, column=0, sticky="nsew", padx=6, pady=4)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        left  = tk.Frame(outer, bg=C_PANEL)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        tk.Frame(outer, bg=C_WIDGET, width=1).grid(
            row=0, column=1, sticky="ns", padx=4)

        right = tk.Frame(outer, bg=C_PANEL)
        right.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        outer.columnconfigure(2, weight=1)

        def lbl(parent, text, fg=C_DIM, font=("Consolas", 8)):
            return tk.Label(parent, text=text, bg=C_PANEL, fg=fg, font=font)

        def sechdr(parent, text):
            lbl(parent, text, fg=C_BLUE,
                font=("Consolas", 8, "bold")).pack(anchor=tk.W, pady=(4, 1))

        def mkbtn(parent, text, color, cmd):
            return tk.Button(parent, text=text, command=cmd,
                             bg=C_WIDGET, fg=color, font=("Consolas", 8, "bold"),
                             relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                             activebackground=C_HEADER, activeforeground=color)

        # ══ LEFT COLUMN ═══════════════════════════════════════════════════════

        # Status + IP on one row
        sechdr(left, "CONNECTION")
        con_row = tk.Frame(left, bg=C_PANEL)
        con_row.pack(fill=tk.X)
        self._dot_canvas = tk.Canvas(con_row, width=12, height=12,
                                     bg=C_PANEL, highlightthickness=0)
        self._dot_canvas.pack(side=tk.LEFT, padx=(0, 3))
        self._dot = self._dot_canvas.create_oval(2, 2, 10, 10, fill=C_RED, outline="")
        self._con_lbl = tk.Label(con_row, text="Disconnected", bg=C_PANEL,
                                 fg=C_RED, font=("Consolas", 8, "bold"))
        self._con_lbl.pack(side=tk.LEFT)

        ip_row = tk.Frame(left, bg=C_PANEL)
        ip_row.pack(fill=tk.X, pady=(2, 0))
        lbl(ip_row, "IP:").pack(side=tk.LEFT)
        self._ip_var = tk.StringVar(value=self.ip)
        tk.Entry(ip_row, textvariable=self._ip_var, bg=C_WIDGET, fg=C_TEXT,
                 font=("Consolas", 8), insertbackground=C_TEXT,
                 relief=tk.FLAT, width=14).pack(side=tk.LEFT, padx=4)

        # Mode + interval on two lines
        sechdr(left, "MODE  &  FETCH")
        mode_row = tk.Frame(left, bg=C_PANEL)
        mode_row.pack(fill=tk.X)
        for text, val in [("Manual", "manual"), ("Auto", "auto")]:
            tk.Radiobutton(mode_row, text=text, variable=self.mode, value=val,
                           bg=C_PANEL, fg=C_TEXT, selectcolor=C_WIDGET,
                           activebackground=C_PANEL, activeforeground=C_TEXT,
                           font=("Consolas", 8),
                           command=self._on_mode_change).pack(side=tk.LEFT, padx=(0, 6))

        int_row = tk.Frame(left, bg=C_PANEL)
        int_row.pack(fill=tk.X, pady=(2, 4))
        lbl(int_row, "Every:").pack(side=tk.LEFT)
        tk.Spinbox(int_row, from_=5, to=600, increment=5,
                   textvariable=self.auto_interval, width=5,
                   bg=C_WIDGET, fg=C_TEXT, buttonbackground=C_WIDGET,
                   font=("Consolas", 8), relief=tk.FLAT).pack(side=tk.LEFT, padx=4)
        lbl(int_row, "s").pack(side=tk.LEFT)

        btn_row = tk.Frame(left, bg=C_PANEL)
        btn_row.pack(fill=tk.X, pady=(0, 2))
        mkbtn(btn_row, "Get Image", C_BLUE,
              lambda: self._trigger("cam1")).pack(side=tk.LEFT, padx=(0, 3))
        mkbtn(btn_row, "Get Data",  C_GREEN,
              lambda: self._trigger("data")).pack(side=tk.LEFT, padx=(0, 3))
        mkbtn(btn_row, "Get Both",  C_ORANGE,
              lambda: self._trigger("both")).pack(side=tk.LEFT)

        # Last update + status at the bottom of left
        sechdr(left, "LAST UPDATE")
        self._lu_img_var  = tk.StringVar(value="Image :  --")
        self._lu_data_var = tk.StringVar(value="Data  :  --")
        for v in (self._lu_img_var, self._lu_data_var):
            tk.Label(left, textvariable=v, bg=C_PANEL, fg=C_GREEN,
                     font=("Consolas", 8, "bold")).pack(anchor=tk.W)

        sechdr(left, "STATUS")
        self._status_var = tk.StringVar(value="Ready.")
        tk.Label(left, textvariable=self._status_var, bg=C_PANEL, fg=C_DIM,
                 font=("Consolas", 8), wraplength=220,
                 justify=tk.LEFT).pack(anchor=tk.W)

        # ══ RIGHT COLUMN ══════════════════════════════════════════════════════

        sechdr(right, "GROUND STATION GPS")

        # Lat + Lon each on own row
        gs_lat_row = tk.Frame(right, bg=C_PANEL)
        gs_lat_row.pack(fill=tk.X, pady=1)
        lbl(gs_lat_row, "Lat:").pack(side=tk.LEFT)
        self._gs_lat_var = tk.StringVar(value="--")
        tk.Entry(gs_lat_row, textvariable=self._gs_lat_var, bg=C_WIDGET, fg=C_TEXT,
                 font=("Consolas", 8), insertbackground=C_TEXT,
                 relief=tk.FLAT, width=13).pack(side=tk.LEFT, padx=4)

        gs_lon_row = tk.Frame(right, bg=C_PANEL)
        gs_lon_row.pack(fill=tk.X, pady=1)
        lbl(gs_lon_row, "Lon:").pack(side=tk.LEFT)
        self._gs_lon_var = tk.StringVar(value="--")
        tk.Entry(gs_lon_row, textvariable=self._gs_lon_var, bg=C_WIDGET, fg=C_TEXT,
                 font=("Consolas", 8), insertbackground=C_TEXT,
                 relief=tk.FLAT, width=13).pack(side=tk.LEFT, padx=4)

        gs_btn_row = tk.Frame(right, bg=C_PANEL)
        gs_btn_row.pack(fill=tk.X, pady=(3, 2))
        mkbtn(gs_btn_row, "Auto-Detect", C_BLUE,
              self._detect_gs_location).pack(side=tk.LEFT, padx=(0, 4))
        mkbtn(gs_btn_row, "Set Manual",  C_ORANGE,
              self._apply_gs_manual).pack(side=tk.LEFT)

        self._gs_dist_var = tk.StringVar(value="Distance to payload: --")
        tk.Label(right, textvariable=self._gs_dist_var, bg=C_PANEL, fg=C_YELLOW,
                 font=("Consolas", 8, "bold")).pack(anchor=tk.W, pady=(2, 0))

    # ── Ground station location ────────────────────────────────────────────────

    def _detect_gs_location(self):
        self._set_status("Detecting ground station location...")
        threading.Thread(target=self._do_detect_gs, daemon=True).start()

    def _do_detect_gs(self):
        try:
            g = geocoder.ip("me")
            if g.ok and g.latlng:
                lat, lon = g.latlng
                self.root.after(0, self._set_gs_location, lat, lon)
                self.logger.log(f"[Dashboard] GS location detected: {lat:.5f}, {lon:.5f}")
            else:
                self._set_status("Auto-detect failed — enter coordinates manually")
        except Exception as e:
            self._set_status(f"GS detect error: {e}")

    def _apply_gs_manual(self):
        try:
            lat = float(self._gs_lat_var.get())
            lon = float(self._gs_lon_var.get())
            self._set_gs_location(lat, lon)
        except ValueError:
            self._set_status("Invalid coordinates — enter decimal degrees (e.g. 13.7439)")

    def _set_gs_location(self, lat, lon):
        self._gs_lat = lat
        self._gs_lon = lon
        self._gs_lat_var.set(f"{lat:.5f}")
        self._gs_lon_var.set(f"{lon:.5f}")
        self._refresh_gs_marker(fit_view=False)   # update marker/line, don't touch zoom
        self._set_status(f"Ground station set: {lat:.5f}, {lon:.5f}")

    def _refresh_gs_marker(self, fit_view=True):
        if self._gs_lat is None:
            return

        # Update ground station marker
        if self._map_gs_marker is not None:
            self._map_gs_marker.delete()
        self._map_gs_marker = self._map_widget.set_marker(
            self._gs_lat, self._gs_lon,
            text="Ground Station",
            marker_color_circle="#60a5fa",
            marker_color_outside="#1e3a5f",
            text_color="#000000",
            font="bold",
        )

        # Update line and distance to payload
        if self._map_gs_line is not None:
            self._map_gs_line.delete()
            self._map_gs_line = None

        if self.gps_history:
            payload_lat, payload_lon = self.gps_history[-1]
            self._map_gs_line = self._map_widget.set_path(
                [(self._gs_lat, self._gs_lon), (payload_lat, payload_lon)],
                color="#facc15",
                width=2,
            )
            dist = self._haversine(self._gs_lat, self._gs_lon, payload_lat, payload_lon)
            if dist >= 1000:
                self._gs_dist_var.set(f"Distance to payload: {dist/1000:.2f} km")
            else:
                self._gs_dist_var.set(f"Distance to payload: {dist:.0f} m")

            # Fit map to show both GS and payload
            if fit_view:
                mid_lat = (self._gs_lat + payload_lat) / 2
                mid_lon = (self._gs_lon + payload_lon) / 2
                self._map_widget.set_position(mid_lat, mid_lon)
                self._map_widget.set_zoom(self._zoom_for_distance(dist))
        else:
            # No payload yet — just centre on ground station
            if fit_view:
                self._map_widget.set_position(self._gs_lat, self._gs_lon)
                self._map_widget.set_zoom(15)

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a  = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2 * R * math.asin(math.sqrt(a))

    @staticmethod
    def _zoom_for_distance(dist_m):
        """Return a zoom level that comfortably shows a span of dist_m metres."""
        if   dist_m <   300: return 17
        elif dist_m <   700: return 16
        elif dist_m <  1500: return 15
        elif dist_m <  3000: return 14
        elif dist_m <  7000: return 13
        elif dist_m < 15000: return 12
        elif dist_m < 30000: return 11
        elif dist_m < 70000: return 10
        else:                return 9

    # ── Mode control ───────────────────────────────────────────────────────────

    def _on_mode_change(self):
        if self.mode.get() == "auto":
            self._stop_auto.clear()
            threading.Thread(target=self._auto_loop, daemon=True).start()
            self._set_status(f"Auto mode — fetching every {self.auto_interval.get()} s")
            self.logger.log(f"[Dashboard] Mode: AUTO  interval={self.auto_interval.get()}s")
        else:
            self._stop_auto.set()
            self._set_status("Manual mode")
            self.logger.log("[Dashboard] Mode: MANUAL")

    def _auto_loop(self):
        while not self._stop_auto.is_set():
            self._do_fetch("both")
            interval = self.auto_interval.get()
            for _ in range(interval):
                if self._stop_auto.is_set():
                    return
                time.sleep(1)

    # ── Fetch orchestration ────────────────────────────────────────────────────

    def _trigger(self, what):
        threading.Thread(target=self._do_fetch, args=(what,), daemon=True).start()

    def _do_fetch(self, what):
        if not self._fetch_lock.acquire(blocking=False):
            self._set_status("Busy — fetch in progress, please wait")
            self.logger.log(f"[Dashboard] WARN: Fetch '{what}' skipped — previous fetch still running")
            return
        try:
            ip = self._ip_var.get().strip()
            if what in ("data", "both"):
                self._fetch_data(ip)
            if what in ("cam1", "both"):
                self._fetch_image(ip)
        finally:
            self._fetch_lock.release()

    # ── Fetch: data ────────────────────────────────────────────────────────────

    def _fetch_data(self, ip):
        self._set_status("Fetching sensor data...")
        self.logger.log(f"[Dashboard] Sending 'data' -> {ip}:{SERVER_PORT}")
        t0 = time.time()
        try:
            soc = _send_cmd(ip, "data")
            res = _recv_data(soc)
            soc.close()
            elapsed = time.time() - t0
            if not res or not isinstance(res, str):
                self.logger.log(f"[Dashboard] ERROR: Data response empty or invalid  elapsed={elapsed:.3f}s")
                self._set_status("Data error: empty response from server")
                self.root.after(0, self._set_connected, False)
                return
            fields = res.split(";")
            self.logger.log(f"[Dashboard] Data received — fields={len(fields)}  length={len(res)}B  transmission={elapsed:.3f}s")
            ts = datetime.now().strftime("%H:%M:%S")
            self.root.after(0, self._apply_data, res, ts)
        except Exception as e:
            elapsed = time.time() - t0
            self._set_status(f"Data error: {e}")
            self.root.after(0, self._set_connected, False)
            self.logger.log(f"[Dashboard] ERROR: Data fetch failed — {type(e).__name__}: {e}  elapsed={elapsed:.3f}s")

    def _apply_data(self, raw, ts):
        if not isinstance(raw, str):
            self.logger.log("[Dashboard] ERROR: _apply_data received non-string payload")
            return
        fields = raw.split(";")
        self._set_connected(True)
        self._lu_data_var.set(f"Data  :  {ts}")

        def get(idx, fmt=None):
            try:
                v = fields[idx].strip()
                if fmt and v not in ("", "Inval.", "N/A"):
                    return fmt % float(v)
                return v
            except Exception:
                return "--"

        updates = {
            "lat":     get(F_LAT,      "%.5f"),
            "lon":     get(F_LON,      "%.5f"),
            "alt":     get(F_ALT,      "%.1f"),
            "speed":   get(F_SPEED,    "%.1f"),
            "sats":    get(F_SATS),
            "fix":     get(F_FIX),
            "pdop":    get(F_PDOP,     "%.2f"),
            "t_board": get(F_T_BOARD,  "%.1f"),
            "t_lm75":  get(F_T_LM75,   "%.1f"),
            "t_ms":    get(F_T_MS,     "%.1f"),
            "pres":    get(F_PRESSURE, "%.1f"),
            "hum":     get(F_HUMIDITY, "%.1f"),
            "v_sup":   get(F_V_SUPPLY, "%.2f"),
            "v33":     get(F_V33,      "%.2f"),
            "v5":      get(F_V5,       "%.2f"),
            "uptime":  get(F_UPTIME),
            "ts":      get(F_TIMESTAMP),
        }

        for key, val in updates.items():
            var, lbl, _ = self._dv[key]
            var.set(val)
            lbl.config(fg=self._field_color(key, val))

        # Save row to CSV (semicolons -> commas)
        try:
            with open(self.csv_path, "a", newline="") as f:
                f.write(raw.replace(";", ",") + "\n")
        except Exception as e:
            self.logger.log(f"[Dashboard] CSV write error: {e}")

        # GPS -> map
        INVALID = ("", "Inval.", "N/A", "--")
        try:
            lat_s = fields[F_LAT].strip()
            lon_s = fields[F_LON].strip()
            if lat_s not in INVALID and lon_s not in INVALID:
                lat, lon = float(lat_s), float(lon_s)
                gps_valid = True
            else:
                lat, lon = DEFAULT_LAT, DEFAULT_LON
                gps_valid = False
        except (ValueError, IndexError):
            lat, lon = DEFAULT_LAT, DEFAULT_LON
            gps_valid = False

        self.gps_history.append((lat, lon))
        if len(self.gps_history) > 300:
            self.gps_history.pop(0)
        self._update_map(lat, lon, gps_valid)

        if gps_valid:
            self._map_pos_var.set(f"{lat:.5f} N,  {lon:.5f} E")
        else:
            self._map_pos_var.set(f"No fix — showing default location")

        def _f(idx):
            try:    return fields[idx].strip()
            except: return "?"
        gps_str = f"Lat={lat:.5f} Lon={lon:.5f}" if gps_valid else "NO FIX"
        self.logger.log(
            f"[Dashboard] GPS={gps_str}  Sats={_f(F_SATS)}  Alt={_f(F_ALT)}m  "
            f"TBoard={_f(F_T_BOARD)}C  Pres={_f(F_PRESSURE)}hPa  "
            f"Vsup={_f(F_V_SUPPLY)}V  Uptime={_f(F_UPTIME)}s"
        )
        self._set_status(f"Data updated at {ts}")

    def _field_color(self, key, val):
        try:
            v = float(val)
        except (ValueError, TypeError):
            return C_TEXT
        if key in ("t_board", "t_lm75", "t_ms"):
            return C_RED if (v > 60 or v < -30) else C_YELLOW if (v > 50 or v < -20) else C_GREEN
        if key == "v_sup":
            return C_RED if (v < 7.0 or v > 8.4) else C_GREEN
        if key == "v33":
            return C_RED if (v < 3.1 or v > 3.5) else C_GREEN
        if key == "v5":
            return C_RED if (v < 4.7 or v > 5.3) else C_GREEN
        if key == "sats":
            return C_RED if v < 4 else C_YELLOW if v < 6 else C_GREEN
        return C_TEXT

    # ── Fetch: image ───────────────────────────────────────────────────────────

    def _fetch_image(self, ip):
        self._set_status("Fetching camera image...")
        self.logger.log(f"[Dashboard] Sending 'cam1' -> {ip}:{SERVER_PORT}")
        t0 = time.time()
        try:
            soc = _send_cmd(ip, "cam1")
            res = _recv_data(soc)
            soc.close()
            elapsed = time.time() - t0
            if not res:
                self.logger.log(f"[Dashboard] ERROR: Image response empty  elapsed={elapsed:.3f}s")
                self._set_status("Image error: empty response from server")
                self.root.after(0, self._set_connected, False)
                return
            nparr = np.frombuffer(res, np.uint8)
            img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Image decode failed")
            h, w    = img.shape[:2]
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            ts    = datetime.now().strftime("%H:%M:%S")
            fname = (f"{self.folder_path}/SpaceCam/"
                     f"SpaceCam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            cv2.imwrite(fname, img)
            self.root.after(0, self._apply_image, img_rgb, ts)
            self.logger.log(f"[Dashboard] Image received — {w}x{h}  size={len(res)}B  transmission={elapsed:.3f}s")
            self.logger.log(f"[Dashboard] Image saved: {fname}")
        except Exception as e:
            elapsed = time.time() - t0
            self._set_status(f"Image error: {e}")
            self.root.after(0, self._set_connected, False)
            self.logger.log(f"[Dashboard] ERROR: Image fetch failed — {type(e).__name__}: {e}  elapsed={elapsed:.3f}s")

    def _apply_image(self, img_rgb, ts):
        self._set_connected(True)
        w = max(self._img_label.winfo_width(),  200)
        h = max(self._img_label.winfo_height(), 150)
        ih, iw  = img_rgb.shape[:2]
        scale   = min(w / iw, h / ih)
        nw, nh  = int(iw * scale), int(ih * scale)
        resized = cv2.resize(img_rgb, (nw, nh), interpolation=cv2.INTER_AREA)

        pil_img = Image.fromarray(resized)
        tk_img  = ImageTk.PhotoImage(pil_img)
        self._img_label.config(image=tk_img, text="")
        self._img_label._photo = tk_img    # prevent GC

        self._img_ts_var.set(f"Updated {ts}")
        self._lu_img_var.set(f"Image :  {ts}")
        self._set_status(f"Image updated at {ts}")

    # ── Map update (tkintermapview) ────────────────────────────────────────────

    def _update_map(self, lat, lon, gps_valid=True):
        # Draw/update GPS track path
        if self._map_path is not None:
            self._map_path.delete()
            self._map_path = None
        if len(self.gps_history) > 1:
            self._map_path = self._map_widget.set_path(
                self.gps_history,
                color="#4a90d9",
                width=3,
            )

        # Place launch marker only once the payload has moved >10 m from start
        # (avoids overlapping with the current-position marker at launch)
        if self._map_start_marker is None and len(self.gps_history) > 1:
            s = self.gps_history[0]
            dist_from_start = self._haversine(s[0], s[1], lat, lon)
            if dist_from_start > 10:
                self._map_start_marker = self._map_widget.set_marker(
                    s[0], s[1],
                    text="Launch",
                    marker_color_circle="#4ade80",
                    marker_color_outside="#166534",
                    text_color="#000000",
                    font="bold",
                )

        # Update current position marker
        if self._map_current_marker is not None:
            self._map_current_marker.delete()
        marker_color = "#facc15" if not gps_valid else "#e94560"
        label = "Payload (no fix)" if not gps_valid else "Payload"
        self._map_current_marker = self._map_widget.set_marker(
            lat, lon,
            text=label,
            marker_color_circle=marker_color,
            marker_color_outside="#7f1d1d" if not gps_valid else "#7f1010",
            text_color="#000000",
            font="bold",
        )

        # Refresh GS line/distance, then fit both into view
        self._refresh_gs_marker(fit_view=gps_valid)

    # ── Status / connection helpers ────────────────────────────────────────────

    def _set_connected(self, connected):
        prev = getattr(self, "_connected_state", None)
        if connected != prev:
            if connected:
                self.logger.log("[Dashboard] Connection established")
            else:
                self.logger.log("[Dashboard] WARN: Connection lost")
            self._connected_state = connected
        color = C_GREEN if connected else C_RED
        text  = "Connected" if connected else "Disconnected"
        self._dot_canvas.itemconfig(self._dot, fill=color)
        self._con_lbl.config(text=text, fg=color)

    def _set_status(self, msg):
        self.root.after(0, self._status_var.set, msg)

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def on_close(self):
        self._stop_auto.set()
        self.logger.log("[Dashboard] Window closed")
        self.root.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else SERVER_IP

    folder_path = CUF.folder("Dashboard Session")
    os.makedirs(folder_path + "/SpaceCam", exist_ok=True)
    logger = SL.SystemLogger(folder_path, "dashboard_log.txt")
    logger.log(f"[Dashboard] Started  IP={ip}")

    root = tk.Tk()
    app  = Dashboard(root, ip, folder_path, logger)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

    logger.log("[Dashboard] Session ended")


if __name__ == "__main__":
    main()
