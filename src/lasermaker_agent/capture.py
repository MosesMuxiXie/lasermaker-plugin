"""Capture one HWND via Windows Graphics Capture; never fall back to the desktop."""
import asyncio
import threading
from pathlib import Path


def capture_window(hwnd, path, timeout=8):
    from PIL import Image, ImageStat
    from windows_capture import WindowsCapture
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    done = threading.Event()
    result = {"hwnd": int(hwnd), "method": "Windows.Graphics.Capture", "path": str(path), "blank_frames_skipped": 0}
    capture = WindowsCapture(window_hwnd=int(hwnd), cursor_capture=False, draw_border=False)

    @capture.event
    def on_frame_arrived(frame, control):
        try:
            image = Image.fromarray(frame.frame_buffer[:, :, :3][:, :, ::-1].copy())
            if not any(hi > lo for lo, hi in ImageStat.Stat(image).extrema):
                result["blank_frames_skipped"] += 1
                return  # A moved/restored window may first produce an empty DWM surface.
            image.save(path)
            result["size"] = list(image.size)
        except Exception as exc:
            result["error"] = str(exc)
        done.set()
        control.stop()

    @capture.event
    def on_closed():
        done.set()

    control = capture.start_free_threaded()
    if not done.wait(timeout):
        control.stop()
        raise RuntimeError("WINDOW_CAPTURE_TIMEOUT")
    if "error" in result or "size" not in result:
        raise RuntimeError(result.get("error", "CAPTURE_WINDOW_CLOSED"))
    return result


async def _recognize(path):
    from PIL import Image
    from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter
    image = Image.open(path).convert("RGBA")
    writer = DataWriter()
    writer.write_bytes(image.tobytes("raw", "BGRA"))
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8,
                                                     image.width, image.height, BitmapAlphaMode.PREMULTIPLIED)
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        return {"available": False, "reason": "NO_INSTALLED_OCR_LANGUAGE"}
    recognized = await engine.recognize_async(bitmap)
    return {"available": True, "text": recognized.text, "lines": [
        {"text": line.text, "words": [
            {"text": word.text, "rectangle": [word.bounding_rect.x, word.bounding_rect.y,
                                              word.bounding_rect.width, word.bounding_rect.height]}
            for word in line.words]} for line in recognized.lines]}


def recognize_window_image(path):
    try:
        return asyncio.run(_recognize(path))
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
