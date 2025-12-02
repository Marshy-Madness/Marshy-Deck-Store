import decky
import json
import requests
import threading
import time
import urllib.parse
import mimetypes
import glob
import asyncio
from pathlib import Path
from decky import emit
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

PLUGIN_SLUG = "zipline-uploader"
SETTINGS_DIR = Path("/home/deck/homebrew/settings") / PLUGIN_SLUG
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

UPLOAD_CACHE = {}   # realpath -> timestamp
PLUGIN = None        # global Plugin instance (for event loop)


# ---------------------------------------------------------
# Settings
# ---------------------------------------------------------

def load_settings():
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text())
    except Exception as e:
        decky.logger.error(f"[Zipline] Failed to load settings: {e}")
    return {}


def save_settings(data):
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        return True
    except Exception as e:
        decky.logger.error(f"[Zipline] Failed to save settings: {e}")
        return False


# ---------------------------------------------------------
# File stabilization
# ---------------------------------------------------------

def wait_for_complete(path: Path, timeout=3):
    """Wait until the file stops growing before uploading."""
    last_size = -1
    stable = 0

    for _ in range(timeout * 10):
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            time.sleep(0.1)
            continue

        if size == last_size:
            stable += 1
            if stable >= 3:  # stable ~300ms
                return True
        else:
            stable = 0
            last_size = size

        time.sleep(0.1)

    return False


# ---------------------------------------------------------
# Screenshot Handler — SINGLE EVENT ONLY
# ---------------------------------------------------------

class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, settings):
        self.settings = settings

    def handle_event(self, event):
        filepath = Path(event.src_path)

        # skip steam temp file
        if filepath.name.lower() == "most_recent.jpg":
            return

        # skip directory events
        if event.is_directory:
            return

        real = str(filepath)
        now = time.time()

        # ✔ Duplicate protection using real string path
        last = UPLOAD_CACHE.get(real)
        if last and now - last < 2:  # Steam repeats events quickly
            return

        # Wait until file is fully written
        if not wait_for_complete(filepath):
            decky.logger.error("[Zipline] File did not stabilize, skipping")
            return

        UPLOAD_CACHE[real] = time.time()
        upload_to_zipline(filepath, self.settings)

    def on_created(self, e):
        self.handle_event(e)

    def on_modified(self, e):
        pass  # disabled 100%

    def on_moved(self, e):
        pass  # disabled to prevent duplicates


# ---------------------------------------------------------
# Upload Logic
# ---------------------------------------------------------

def upload_to_zipline(path: Path, settings):
    url = settings.get("uploadURL", "").strip()
    token = settings.get("token", "").strip()
    fmt = settings.get("selectedFormat", "DATE")
    use_folder = settings.get("useFolder", False)
    folder_id = settings.get("ziplineFolder", "")

    if not url or not token:
        return

    headers = {"Authorization": token, "Format": fmt}
    if use_folder and folder_id:
        headers["x-zipline-folder"] = folder_id

    try:
        with open(path, "rb") as f:
            mime, _ = mimetypes.guess_type(str(path))
            if mime is None:
                mime = "application/octet-stream"

            files = {"file": (path.name, f, mime)}
            res = requests.post(url, headers=headers, files=files)

        if not res.ok:
            decky.logger.error(
                f"[Zipline] Upload failed {res.status_code}: {res.text}"
            )
            return

        try:
            data = res.json()
        except Exception:
            try:
                data = json.loads(urllib.parse.unquote(res.text))
            except Exception:
                decky.logger.error(
                    f"[Zipline] JSON decode failed → {res.text}"
                )
                return

        link = data.get("files", [{}])[0].get("url", "")
        decky.logger.info(f"[Zipline] Uploaded → {link}")

        # ---------------------------------------------------------
        # Correct Decky event emission (thread-safe)
        # ---------------------------------------------------------
        asyncio.run_coroutine_threadsafe(
            emit("zipline_upload_success", str(path), link),
            PLUGIN.loop
        )

    except Exception as e:
        decky.logger.error(f"[Zipline] Upload exception: {e}")


# ---------------------------------------------------------
# Folder fetch
# ---------------------------------------------------------

def fetch_folders(settings):
    url = settings.get("uploadURL", "").strip()
    token = settings.get("token", "").strip()

    if not url or not token:
        return []

    base = url.split("/upload")[0] if "/upload" in url else url
    api = f"{base}/user/folders?noincl=true"

    try:
        res = requests.get(api, headers={"Authorization": token})
        if res.ok:
            return res.json()
    except Exception as e:
        decky.logger.error(f"[Zipline] Folder fetch exception: {e}")

    return []


# ---------------------------------------------------------
# Watch directories
# ---------------------------------------------------------

def get_screenshot_paths():
    paths = ["/home/deck/Pictures/Screenshots"]

    for p in glob.glob(
        "/home/deck/.local/share/Steam/userdata/*/760/remote/*/screenshots"
    ):
        paths.append(p)

    return paths


def start_monitor_thread(settings):
    handler = ScreenshotHandler(settings)
    obs = Observer()

    for p in get_screenshot_paths():
        if Path(p).exists():
            decky.logger.info(f"[Zipline] Watching: {p}")
            obs.schedule(handler, p, recursive=False)
        else:
            decky.logger.info(f"[Zipline] Missing: {p}")

    def loop():
        obs.start()
        try:
            while True:
                time.sleep(1)
        except Exception:
            pass
        obs.stop()
        obs.join()

    threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------
# Plugin class
# ---------------------------------------------------------

class Plugin:
    def __init__(self):
        global PLUGIN
        PLUGIN = self
        self.monitor_running = False
        self.loop = None

    async def _main(self):
        self.loop = asyncio.get_running_loop()

        settings = load_settings()
        if settings.get("autoStart", False):
            start_monitor_thread(settings)
            self.monitor_running = True

    async def settings_getSetting(self, args):
        key, default = args
        return load_settings().get(key, default)

    async def settings_setSetting(self, args):
        key, value = args
        data = load_settings()
        data[key] = value
        save_settings(data)
        return True

    async def settings_commit(self, args):
        return True

    async def get_folders(self, args):
        return fetch_folders(load_settings())

    async def start_monitoring(self, args):
        if not self.monitor_running:
            start_monitor_thread(load_settings())
            self.monitor_running = True
        return True

    async def _unload(self):
        decky.logger.info("[Zipline] Unloaded")
