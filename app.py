import tkinter as tk
from tkinter import scrolledtext
import threading
import datetime
import requests
import json
import time
import os
import sys
import shutil

from scrapers.service import ScraperService
from scrapers.registry import provider_registry
from dataclasses import asdict

VERSION_LOCAL = "1.0.2"
VERSION_URL = "https://raw.githubusercontent.com/CastilloDevX/ploostream_server/main/version.txt"
EXE_URL = "https://github.com/CastilloDevX/ploostream_server/releases/latest/download/PloostreamScraper.exe"
FIREBASE_URL = "https://ploostream-db-default-rtdb.firebaseio.com/content.json"
MIN_INTERVAL_SECONDS = 900  # 15 minutos

# ===========================
#   ACTUALIZACIÓN AUTOMÁTICA
# ===========================
def check_for_updates():
    try:
        version_remota = requests.get(VERSION_URL, timeout=10).text.strip()
        if version_remota == VERSION_LOCAL:
            print("Ya estás actualizado")
            return

        print(f"Nueva versión detectada: {version_remota}")
        exe_actual = sys.executable
        nuevo_exe = exe_actual + ".new"

        with requests.get(EXE_URL, stream=True) as r:
            r.raise_for_status()
            with open(nuevo_exe, "wb") as f:
                shutil.copyfileobj(r.raw, f)

        updater = exe_actual + "_update.bat"
        with open(updater, "w") as f:
            f.write(f"""
@echo off
timeout /t 2 >NUL
del "{exe_actual}"
rename "{nuevo_exe}" "{os.path.basename(exe_actual)}"
start "" "{exe_actual}"
del "%~f0"
""")

        os.startfile(updater)
        sys.exit()

    except Exception as e:
        print("Error al buscar actualización:", e)


# ===========================
#     FUNCIÓN SCRAPING
# ===========================
def deep_clean(obj):
    if isinstance(obj, dict):
        return {str(k): deep_clean(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_clean(i) for i in obj]
    elif isinstance(obj, (int, float, str, bool)):
        return obj
    elif obj is None:
        return ""
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return str(obj)

def ejecutar_scraping(ui_update_callback, limpiar=True):
    try:
        if limpiar:
            ui_update_callback("clear")

        ui_update_callback("⏳ Iniciando scraping ...")
        ui_update_callback("→ Obteniendo eventos")
        ui_update_callback("Esto puede tardar unos segundos")

        service = ScraperService(provider_registry)
        events = service.build_events()
        raw_data = [asdict(e) for e in events]
        data = deep_clean(raw_data)

        count = len(data)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        ui_update_callback(f"✔ Scrapeo completado")
        ui_update_callback(f"→ ({timestamp}) Eventos obtenidos: {count}")

        from collections import defaultdict
        by_provider = defaultdict(list)
        for ev in events:
            by_provider[ev.provider].append(ev)

        for provider, items in by_provider.items():
            total_streams = sum(len(e.streams) for e in items)
            ui_update_callback(f"🔸 {provider}: {len(items)} partidos, {total_streams} streams")

        json.dumps(data)

        ui_update_callback("⏳ Enviando datos a Firebase ...")
        response = requests.put(FIREBASE_URL, json=data, headers={"Content-Type": "application/json"}, timeout=30)
        if response.status_code in (200, 201):
             ui_update_callback("✅ Datos enviados correctamente a Firebase.")
        else:
             ui_update_callback(f"❌ Error HTTP: {response.status_code}")

    except Exception as e:
        ui_update_callback(f"❌ Error:\n{str(e)}\n")


# ===========================
#          GUI TKINTER
# ===========================
class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Ploostream Scraper")
        self.root.geometry("620x520")
        self.root.configure(bg="#0d1b2a")
        self.auto_mode = tk.BooleanVar(value=False)

        tk.Label(root, text="Ploostream Scraper", font=("Segoe UI", 16, "bold"), fg="white", bg="#0d1b2a").pack(pady=10)

        top_frame = tk.Frame(root, bg="#0d1b2a")
        top_frame.pack(pady=5, fill="x", padx=20)

        tk.Button(top_frame, text="🕹 Scrapear", font=("Segoe UI", 11, "bold"), bg="#1d3557", fg="white",
                  command=self.run_scraping_thread).pack(side="left")

        tk.Button(top_frame, text="🧹 Limpiar", font=("Segoe UI", 11), bg="#6c757d", fg="white",
                  command=self.clear_log).pack(side="left", padx=(10, 0))

        self.interval_entry = tk.Entry(top_frame, width=10)
        self.interval_entry.insert(0, "3600")
        self.interval_entry.pack(side="right")

        self.switch = tk.Checkbutton(top_frame, text="⏱ Auto", variable=self.auto_mode, font=("Segoe UI", 11),
                                     bg="#0d1b2a", fg="white", selectcolor="#1d3557",
                                     command=self.toggle_auto_scraping)
        self.switch.pack(side="right", padx=(0, 10))

        self.log_box = scrolledtext.ScrolledText(root, width=70, height=22, font=("Consolas", 10),
                                                 bg="#1b263b", fg="white", insertbackground="white")
        self.log_box.pack(padx=20, pady=10)

    def log(self, text):
        if text == "clear":
            self.log_box.delete("1.0", tk.END)
        else:
            self.log_box.insert(tk.END, text + "\n")
            self.log_box.see(tk.END)

    def clear_log(self):
        self.log_box.delete("1.0", tk.END)

    def run_scraping_thread(self):
        threading.Thread(target=ejecutar_scraping, args=(self.log,), daemon=True).start()

    def toggle_auto_scraping(self):
        try:
            interval = int(self.interval_entry.get())
            if interval < MIN_INTERVAL_SECONDS:
                self.log("❌ Error: El intervalo debe ser de al menos 900 segundos (15 minutos).")
                self.auto_mode.set(False)
                return
        except ValueError:
            self.log("❌ Intervalo inválido. Ingresa un número entero.")
            self.auto_mode.set(False)
            return

        if self.auto_mode.get():
            self.log(f"🔄 Modo automático activado (cada {interval} segundos)")
            threading.Thread(target=self.auto_scrape_loop, args=(interval,), daemon=True).start()
        else:
            self.log("🛑 Modo automático desactivado")

    def auto_scrape_loop(self, interval):
        while self.auto_mode.get():
            ejecutar_scraping(self.log)
            for _ in range(interval):
                if not self.auto_mode.get():
                    return
                time.sleep(1)


if __name__ == "__main__":
    check_for_updates()
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()
