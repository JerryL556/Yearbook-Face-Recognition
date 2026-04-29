from __future__ import annotations

import ctypes
import json
import tempfile
import threading
import urllib.error
import urllib.request
import uuid
from io import BytesIO
from pathlib import Path

import tkinter as tk
from PIL import ImageGrab, ImageTk


API_BASE = "http://127.0.0.1:8000"


def enable_dpi_awareness() -> None:
    if not hasattr(ctypes, "windll"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def build_multipart_payload(field_name: str, filename: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = f"----StudentTaggerBoundary{uuid.uuid4().hex}"
    body = BytesIO()
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("utf-8")
    )
    body.write(file_bytes)
    body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def get_virtual_screen_bounds() -> tuple[int, int, int, int]:
    if hasattr(ctypes, "windll"):
        user32 = ctypes.windll.user32
        return (
            user32.GetSystemMetrics(76),
            user32.GetSystemMetrics(77),
            user32.GetSystemMetrics(78),
            user32.GetSystemMetrics(79),
        )
    root = tk.Tk()
    root.withdraw()
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    root.destroy()
    return (0, 0, width, height)


class RegionSelector:
    def __init__(self, parent: tk.Tk, on_complete, on_cancel) -> None:
        self.parent = parent
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self.overlay: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.preview_image = None
        self.screen_image = None
        self.screen_left = 0
        self.screen_top = 0
        self.screen_width = 0
        self.screen_height = 0
        self.display_width = 0
        self.display_height = 0
        self.start_x = 0
        self.start_y = 0
        self.rect_id: int | None = None

    def begin(self) -> None:
        self.parent.withdraw()
        self.parent.after(120, self._show_overlay)

    def _show_overlay(self) -> None:
        try:
            self.screen_left, self.screen_top, self.screen_width, self.screen_height = get_virtual_screen_bounds()
            self.screen_image = ImageGrab.grab(
                bbox=(
                    self.screen_left,
                    self.screen_top,
                    self.screen_left + self.screen_width,
                    self.screen_top + self.screen_height,
                ),
                all_screens=True,
            )
        except Exception:
            self._cancel()
            return

        self.display_width = self.screen_image.width
        self.display_height = self.screen_image.height
        self.overlay = tk.Toplevel(self.parent)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.geometry(
            f"{self.display_width}x{self.display_height}+{self.screen_left}+{self.screen_top}"
        )
        self.overlay.configure(bg="black")
        try:
            self.overlay.attributes("-alpha", 0.82)
        except tk.TclError:
            pass
        self.overlay.bind("<Escape>", lambda _event: self._cancel())

        self.preview_image = ImageTk.PhotoImage(self.screen_image)
        self.canvas = tk.Canvas(
            self.overlay,
            width=self.display_width,
            height=self.display_height,
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self.preview_image)
        self.canvas.create_rectangle(0, 0, self.display_width, 42, fill="#0d5c63", outline="")
        self.canvas.create_text(
            16,
            21,
            anchor="w",
            fill="white",
            font=("Segoe UI", 12, "bold"),
            text="Drag to select a region for face recognition. Press Esc to cancel.",
        )
        self.canvas.bind("<ButtonPress-1>", self._start_selection)
        self.canvas.bind("<B1-Motion>", self._update_selection)
        self.canvas.bind("<ButtonRelease-1>", self._finish_selection)

    def _start_selection(self, event) -> None:
        self.start_x = event.x
        self.start_y = event.y
        if self.canvas is None:
            return
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline="#0d5c63",
            width=3,
        )

    def _update_selection(self, event) -> None:
        if self.canvas is None or self.rect_id is None:
            return
        self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def _finish_selection(self, event) -> None:
        if self.screen_image is None:
            self._cancel()
            return
        x1, x2 = sorted((self.start_x, event.x))
        y1, y2 = sorted((self.start_y, event.y))
        if abs(x2 - x1) < 8 or abs(y2 - y1) < 8:
            self._cancel()
            return

        scale_x = self.screen_image.width / max(1, self.display_width)
        scale_y = self.screen_image.height / max(1, self.display_height)
        image_box = (
            int(round(x1 * scale_x)),
            int(round(y1 * scale_y)),
            int(round(x2 * scale_x)),
            int(round(y2 * scale_y)),
        )
        cropped = self.screen_image.crop(image_box)
        self._teardown()
        self.on_complete(cropped)

    def _cancel(self) -> None:
        self._teardown()
        self.on_cancel()

    def _teardown(self) -> None:
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None
        self.parent.deiconify()
        self.parent.lift()
        self.parent.attributes("-topmost", True)


class CaptureHelperApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Student Tagger Capture")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#0b2f33")
        self.root.geometry("240x124+28+120")

        self.drag_origin_x = 0
        self.drag_origin_y = 0
        self.health_check_running = False
        self.server_ready = False
        self.busy = False

        shell = tk.Frame(self.root, bg="#0b2f33", padx=1, pady=1)
        shell.pack(fill="both", expand=True)

        panel = tk.Frame(shell, bg="#f7eedb")
        panel.pack(fill="both", expand=True)

        title_bar = tk.Frame(panel, bg="#0d5c63", height=32)
        title_bar.pack(fill="x")
        title_bar.bind("<ButtonPress-1>", self._begin_drag)
        title_bar.bind("<B1-Motion>", self._drag_window)

        title = tk.Label(
            title_bar,
            text="Desktop Capture",
            bg="#0d5c63",
            fg="white",
            font=("Segoe UI", 10, "bold"),
        )
        title.pack(side="left", padx=10)
        title.bind("<ButtonPress-1>", self._begin_drag)
        title.bind("<B1-Motion>", self._drag_window)

        close_button = tk.Button(
            title_bar,
            text="x",
            command=self.root.destroy,
            bg="#0d5c63",
            fg="white",
            activebackground="#06383c",
            activeforeground="white",
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 10, "bold"),
        )
        close_button.pack(side="right")

        body = tk.Frame(panel, bg="#f7eedb", padx=12, pady=12)
        body.pack(fill="both", expand=True)

        self.capture_button = tk.Button(
            body,
            text="Capture Region",
            command=self.start_capture,
            bg="#0d5c63",
            fg="white",
            activebackground="#06383c",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            padx=10,
            pady=8,
        )
        self.capture_button.pack(fill="x")

        self.status_var = tk.StringVar(value="Waiting for web app...")
        status_label = tk.Label(
            body,
            textvariable=self.status_var,
            bg="#f7eedb",
            fg="#5b564e",
            anchor="w",
            justify="left",
            font=("Segoe UI", 9),
            pady=10,
        )
        status_label.pack(fill="x")

        self.capture_button.configure(state="disabled")
        self.root.after(250, self.poll_health)

    def _begin_drag(self, event) -> None:
        self.drag_origin_x = event.x
        self.drag_origin_y = event.y

    def _drag_window(self, event) -> None:
        x = self.root.winfo_x() + event.x - self.drag_origin_x
        y = self.root.winfo_y() + event.y - self.drag_origin_y
        self.root.geometry(f"+{x}+{y}")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def poll_health(self) -> None:
        if not self.health_check_running:
            self.health_check_running = True
            thread = threading.Thread(target=self._poll_health_worker, daemon=True)
            thread.start()
        self.root.after(2500, self.poll_health)

    def _poll_health_worker(self) -> None:
        ready = False
        try:
            with urllib.request.urlopen(f"{API_BASE}/health", timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
                ready = response.status == 200 and payload.get("status") in {"ok", "degraded"}
        except Exception:
            ready = False
        self.root.after(0, lambda: self._apply_health_state(ready))

    def _apply_health_state(self, ready: bool) -> None:
        self.health_check_running = False
        self.server_ready = ready
        if self.busy:
            return
        self.capture_button.configure(state="normal" if ready else "disabled")
        self.set_status("Ready to capture." if ready else "Waiting for web app...")

    def start_capture(self) -> None:
        if self.busy or not self.server_ready:
            return
        self.busy = True
        self.capture_button.configure(state="disabled")
        self.set_status("Select a region...")
        selector = RegionSelector(self.root, self._on_region_captured, self._on_capture_cancelled)
        selector.begin()

    def _on_capture_cancelled(self) -> None:
        self.busy = False
        self.capture_button.configure(state="normal" if self.server_ready else "disabled")
        self.set_status("Capture cancelled.")

    def _on_region_captured(self, image) -> None:
        self.set_status("Recognizing faces...")
        worker = threading.Thread(target=self._upload_capture, args=(image,), daemon=True)
        worker.start()

    def _upload_capture(self, image) -> None:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_path = Path(temp_file.name)
            image.save(temp_path, format="PNG")
            file_bytes = temp_path.read_bytes()
            payload, content_type = build_multipart_payload("file", "desktop_capture.png", file_bytes)
            request = urllib.request.Request(
                f"{API_BASE}/desktop-capture",
                data=payload,
                method="POST",
                headers={"Content-Type": content_type},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = str(exc)
            self.root.after(0, lambda: self._finish_capture(False, f"Capture failed: {detail}"))
            return
        except Exception as exc:
            self.root.after(0, lambda: self._finish_capture(False, f"Capture failed: {exc}"))
            return
        finally:
            try:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        matched = body.get("photo", {}).get("matched_count", 0)
        faces = body.get("photo", {}).get("face_count", 0)
        self.root.after(0, lambda: self._finish_capture(True, f"Done: {matched} matches across {faces} faces."))

    def _finish_capture(self, success: bool, message: str) -> None:
        self.busy = False
        self.capture_button.configure(state="normal" if self.server_ready else "disabled")
        self.set_status(message if success else message[:140])

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    enable_dpi_awareness()
    CaptureHelperApp().run()


if __name__ == "__main__":
    main()
