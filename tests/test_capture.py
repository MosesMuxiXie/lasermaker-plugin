import sys
from types import SimpleNamespace
import numpy as np

from lasermaker_agent.capture import capture_window


def test_capture_skips_a_blank_initial_frame_without_using_the_desktop(tmp_path, monkeypatch):
    class Capture:
        def __init__(self, **kwargs):
            assert kwargs["window_hwnd"] == 888 and "monitor_index" not in kwargs
            self.handlers = {}
        def event(self, function):
            self.handlers[function.__name__] = function
        def start_free_threaded(self):
            control = SimpleNamespace(stopped=False)
            def stop():
                control.stopped = True
            control.stop = stop
            valid = np.zeros((4, 4, 4), dtype=np.uint8)
            valid[1, 1, 2] = 255
            for buffer in (np.zeros_like(valid), valid):
                if control.stopped:
                    break
                self.handlers["on_frame_arrived"](SimpleNamespace(frame_buffer=buffer), control)
            return control
    monkeypatch.setitem(sys.modules, "windows_capture", SimpleNamespace(WindowsCapture=Capture))
    result = capture_window(888, tmp_path / "window.png", timeout=.1)
    assert result["size"] == [4, 4] and result["blank_frames_skipped"] == 1
    assert (tmp_path / "window.png").is_file()
