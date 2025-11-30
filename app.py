import tkinter as tk
from tkinter import scrolledtext
import threading
import datetime
import requests
import json
import time

from scrapers.service import ScraperService
from scrapers.registry import provider_registry
from dataclasses import asdict

FIREBASE_URL = "https://ploostream-db-default-rtdb.firebaseio.com/content.json"
INTERVALO_SEGUNDOS = 3600  # 1 hora


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

        json.dumps(data)  # validación

        ui_update_callback(f"⏳ Enviando datos a la base de datos ...")
        
        response = requests.put(
            FIREBASE_URL,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        

        if response.status_code in (200, 201):
            ui_update_callback("✅ Datos enviados correctamente a Firebase.")
        else:
            ui_update_callback(f"❌ Error HTTP: {response.status_code}")

    except Exception as e:
        ui_update_callback(f"❌ Error:\n{str(e)}\n")


class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Ploostream Scraper")
        self.root.geometry("600x480")
        self.root.configure(bg="#0d1b2a")
        self.auto_mode = tk.BooleanVar(value=False)

        # Título
        tk.Label(
            root, text="Ploostream Scraper",
            font=("Segoe UI", 16, "bold"),
            fg="white", bg="#0d1b2a"
        ).pack(pady=10)

        # Controles superiores
        top_frame = tk.Frame(root, bg="#0d1b2a")
        top_frame.pack(pady=5, fill="x", padx=20)

        # Botones
        tk.Button(
            top_frame, text="🕹 Scrapear",
            font=("Segoe UI", 11, "bold"),
            bg="#1d3557", fg="white",
            command=self.run_scraping_thread
        ).pack(side="left")

        tk.Button(
            top_frame, text="🧹 Limpiar",
            font=("Segoe UI", 11),
            bg="#6c757d", fg="white",
            command=self.clear_log
        ).pack(side="left", padx=(10, 0))

        self.switch = tk.Checkbutton(
            top_frame,
            text="⏱ Auto (1h)",
            variable=self.auto_mode,
            font=("Segoe UI", 11),
            bg="#0d1b2a", fg="white",
            activebackground="#0d1b2a",
            activeforeground="white",
            selectcolor="#1d3557",
            command=self.toggle_auto_scraping
        )
        self.switch.pack(side="right")

        # Consola
        self.log_box = scrolledtext.ScrolledText(
            root, width=70, height=20,
            font=("Consolas", 10),
            bg="#1b263b", fg="white",
            insertbackground="white"
        )
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
        thread = threading.Thread(
            target=ejecutar_scraping,
            args=(self.log,)
        )
        thread.start()

    def toggle_auto_scraping(self):
        if self.auto_mode.get():
            self.log("🔄 Modo automático activado (cada 1 hora)")
            thread = threading.Thread(target=self.auto_scrape_loop, daemon=True)
            thread.start()
        else:
            self.log("🛑 Modo automático desactivado")

    def auto_scrape_loop(self):
        while self.auto_mode.get():
            ejecutar_scraping(self.log)
            for _ in range(INTERVALO_SEGUNDOS):
                if not self.auto_mode.get():
                    return
                time.sleep(1)


if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()
