"""Standalone Windows UIA driver. This module never transmits or starts a machine job."""
from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import time
import contextlib
import threading
import tempfile
from pathlib import Path

from .geometry import number
from .store import ProjectError, file_lock

EXECUTABLE = Path(r"C:\Program Files\LaserMaker2\Bin\LaserMaker.exe")
SUPPORTED_VERSION = "2.1.7.2"
MODES = {"cut": "切割", "score": "描线", "engrave": "深雕", "shallow_engrave": "浅雕"}


class DriverError(ProjectError):
    pass


def parse_dimension(value):
    match = re.fullmatch(r"\s*([+-]?\d+(?:[.,]\d+)?)\s*(?:mm)?\s*", value)
    if not match:
        raise ValueError("INVALID_DIMENSION_OR_UNITS")
    return number(float(match[1].replace(",", ".")))


def validate_process(values):
    if values.get("mode") not in MODES:
        raise ValueError("UNSUPPORTED_PROCESS_MODE")
    speed = number(values["speed_mm_s"])
    maximum = number(values["power_max_percent"])
    is_line = values['mode'] in ('cut', 'score')
    if not is_line and 'power_min_percent' in values:
        raise ValueError('CORNER_POWER_NOT_APPLICABLE_TO_ENGRAVING')
    minimum = number(values.get("power_min_percent", maximum))
    if not 0 < speed <= 10000 or not 0 <= minimum <= maximum <= 100:
        raise ValueError("INVALID_SPEED_OR_POWER")
    result = {"mode": values["mode"], "speed_mm_s": speed, "power_max_percent": maximum,
              "machine_validated": False}
    if is_line:
        result['power_min_percent'] = minimum
    return result


class WindowsDriver:
    def __init__(self, executable=None, timeout=80):
        if os.name != "nt":
            raise DriverError("WINDOWS_INTERACTIVE_DESKTOP_REQUIRED")
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        self.executable = Path(executable or EXECUTABLE).resolve()
        self.deadline = time.monotonic() + min(max(float(timeout), 1), 80)
        self.pid = None
        self.hwnd = None

    def _remaining(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise DriverError("UI_DEADLINE_EXCEEDED")
        return left

    def _connect(self, launch=False):
        from pywinauto.application import Application
        if not self.executable.is_file():
            raise DriverError("LASERMAKER_NOT_INSTALLED")
        try:
            app = Application(backend="uia").connect(path=str(self.executable), timeout=1)
        except Exception as exc:
            if not launch:
                raise DriverError("LASERMAKER_NOT_RUNNING") from exc
            subprocess.Popen([str(self.executable)], cwd=self.executable.parent)
            app = Application(backend="uia").connect(path=str(self.executable),
                                                    timeout=min(12, self._remaining()))
        self.pid = app.process
        return app

    def _window(self, launch=False, restore=False):
        from pywinauto import Desktop
        import win32gui
        import win32process
        if self.hwnd and win32gui.IsWindow(self.hwnd) and \
                win32process.GetWindowThreadProcessId(self.hwnd)[1] == self.pid:
            self._require_enabled()
            w = Desktop(backend="uia").window(handle=self.hwnd).wrapper_object()
        else:
            app = self._connect(launch)
            def main_windows():
                windows = []
                def visit(hwnd, _):
                    if win32process.GetWindowThreadProcessId(hwnd)[1] == app.process and \
                            win32gui.GetWindowText(hwnd) == "LaserMaker 2.0":
                        windows.append(hwnd)
                win32gui.EnumWindows(visit, None)
                return windows or None
            windows = self._wait(main_windows) if launch else (main_windows() or [])
            if len(windows) != 1:
                raise DriverError("LASERMAKER_WINDOW_AMBIGUOUS_OR_MODAL")
            self.hwnd = windows[0]
            self._require_enabled()
            w = Desktop(backend="uia").window(handle=self.hwnd).wrapper_object()
        if restore:
            import win32api
            import win32con
            import win32gui
            if win32gui.IsIconic(w.handle):
                win32gui.ShowWindow(w.handle, win32con.SW_RESTORE)
            rect = w.rectangle()
            monitors = [win32api.GetMonitorInfo(m[0])["Work"] for m in win32api.EnumDisplayMonitors()]
            if not any(rect.right > l and rect.left < r and rect.bottom > t and rect.top < b
                       for l, t, r, b in monitors):
                l, t, r, b = monitors[0]
                win32gui.SetWindowPos(w.handle, None, l+30, t+30, min(1500, r-l-60),
                                     min(900, b-t-60), win32con.SWP_NOZORDER)
        return w

    def _require_enabled(self):
        import win32gui
        transition_deadline = time.monotonic() + min(2, self._remaining())
        while not win32gui.IsWindowEnabled(self.hwnd):
            windows = self._owned_windows()
            modals = [d for d in windows if d.get("hwnd") != self.hwnd and
                      (d.get("owner") == self.hwnd or d.get("class") == "#32770")
                      and d.get("class") != "Qt5QWindowPopupSaveBits"]
            if modals:
                raise DriverError("UNEXPECTED_MODAL: " + json.dumps(modals, ensure_ascii=False))
            if time.monotonic() >= transition_deadline:
                raise DriverError("WINDOW_DISABLED_WITHOUT_VISIBLE_MODAL")
            time.sleep(.05)

    def _owned_windows(self, visible=True):
        import win32gui
        import win32process
        result = []
        def visit(hwnd, _):
            if win32process.GetWindowThreadProcessId(hwnd)[1] == self.pid:
                if not visible or win32gui.IsWindowVisible(hwnd):
                    result.append({"hwnd": hwnd, "title": win32gui.GetWindowText(hwnd),
                                   "class": win32gui.GetClassName(hwnd),
                                   "enabled": bool(win32gui.IsWindowEnabled(hwnd)),
                                   "owner": win32gui.GetWindow(hwnd, 4)})
        win32gui.EnumWindows(visit, None)
        return result

    def _unlocked(self):
        from ctypes import wintypes as wt
        u = ctypes.windll.user32
        u.OpenInputDesktop.restype = wt.HANDLE
        handle = u.OpenInputDesktop(0, False, 1)
        if not handle:
            raise DriverError("DESKTOP_LOCKED_OR_INACCESSIBLE")
        try:
            name, needed = ctypes.create_unicode_buffer(256), wt.DWORD()
            if not u.GetUserObjectInformationW(handle, 2, name, ctypes.sizeof(name), ctypes.byref(needed)):
                raise DriverError("DESKTOP_STATE_UNAVAILABLE")
            if name.value != "Default":
                raise DriverError("DESKTOP_LOCKED_OR_SECURE_PROMPT")
        finally:
            u.CloseDesktop(handle)

    def _idle(self):
        import win32gui
        self._unlocked()
        w = self._window(launch=True, restore=True)
        def version_labels():
            labels = [c.window_text() for c in self._controls(w, "TabItem")]
            return labels if any(label.startswith("LaserMaker V") for label in labels) else None
        labels = self._wait(version_labels)
        if f"LaserMaker V{SUPPORTED_VERSION}" not in labels:
            raise DriverError("UNSUPPORTED_LASERMAKER_VERSION")
        modals = [d for d in self._owned_windows() if d["hwnd"] != w.handle and
                  d["class"] != "Qt5QWindowPopupSaveBits" and
                  (d["owner"] == w.handle or d["class"] == "#32770")]
        if not win32gui.IsWindowEnabled(w.handle) or modals:
            raise DriverError("UNEXPECTED_MODAL: " + json.dumps(modals, ensure_ascii=False))
        return w

    @contextlib.contextmanager
    def _foreground(self, hwnd):
        """Verify focus before key input, then return focus only if it is still ours."""
        import win32api
        import win32gui
        import win32process
        self._unlocked()
        previous = win32gui.GetForegroundWindow()
        if not win32gui.IsWindowEnabled(hwnd):
            raise DriverError("TARGET_DISABLED_BY_MODAL")
        current_thread = win32api.GetCurrentThreadId()
        foreground_thread = win32process.GetWindowThreadProcessId(previous)[0] if previous else 0
        attached = False
        try:
            if foreground_thread and current_thread != foreground_thread:
                attached = bool(ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, True))
            win32gui.BringWindowToTop(hwnd)
            if win32gui.GetForegroundWindow() != hwnd:
                win32gui.SetForegroundWindow(hwnd)
        except Exception as exc:
            raise DriverError("CANNOT_FOCUS_LASERMAKER") from exc
        finally:
            if attached:
                ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, False)
        until = min(self.deadline, time.monotonic()+.35)
        while win32gui.GetForegroundWindow() != hwnd and time.monotonic() < until:
            time.sleep(.01)
        if win32gui.GetForegroundWindow() != hwnd:
            raise DriverError("DESKTOP_IN_USE")
        try:
            yield
        finally:
            if previous and previous != hwnd and win32gui.IsWindow(previous) and \
                    win32gui.IsWindowEnabled(previous) and win32gui.GetForegroundWindow() == hwnd:
                try:
                    win32gui.SetForegroundWindow(previous)
                except Exception:
                    pass

    def _active_tab(self, w):
        parents = self._controls(w, "Tab")
        tabs = [c for parent in parents for c in parent.children(control_type="TabItem")]
        active = []
        for tab in tabs:
            try:
                if tab.is_selected():
                    active.append(tab)
            except Exception:
                pass
        if not active:
            # Qt 5 exposes the active tab as Tab.Name even when SelectionItem is absent.
            parent_names = {c.window_text() for c in parents}
            active = [c for c in tabs if c.window_text() in parent_names]
        if len(active) != 1:
            raise DriverError("ACTIVE_DOCUMENT_AMBIGUOUS")
        return active[0]

    def assert_document(self, expected_name, expected_pid=None):
        w = self._idle()
        if expected_pid is not None and self.pid != expected_pid:
            raise DriverError("APPLICATION_PROCESS_CHANGED")
        actual = self._active_tab(w).window_text()
        if actual not in (expected_name, Path(expected_name).stem):
            raise DriverError("ACTIVE_DOCUMENT_CHANGED")
        return w

    def _menu(self, index):
        """Observed 2.1.7.2 file-menu profile. Native Qt menu items have empty UIA names."""
        from pywinauto import Desktop
        w = self._idle()
        buttons = [c for c in self._controls(w, "Button") if c.window_text() == "文件"]
        if not buttons and index in (0, 1):
            label = "新建" if index == 0 else "打开"
            labels = [c for c in self._controls(w, "Text") if c.window_text() == label]
            if len(labels) != 1:
                raise DriverError("HOME_ACTION_LABEL_NOT_FOUND")
            r = labels[0].rectangle()
            cards = [c for c in self._controls(w, "Button") if
                     abs((c.rectangle().left+c.rectangle().right-r.left-r.right)/2) < 20 and
                     0 <= r.top-c.rectangle().bottom < 30]
            if len(cards) != 1:
                raise DriverError("HOME_ACTION_BUTTON_AMBIGUOUS")
            self._post_click(w, cards[0].rectangle())
            return
        if len(buttons) != 1:
            raise DriverError("FILE_BUTTON_NOT_FOUND")
        buttons[0].invoke()
        def find_menu():
            for item in self._owned_windows():
                if item["class"] == "Qt5QWindowPopupSaveBits":
                    menu = Desktop(backend="uia").window(handle=item["hwnd"]).wrapper_object()
                    children = menu.children(control_type="MenuItem")
                    if children:
                        return menu, children
            return None
        menu, items = self._wait(find_menu)
        if len(items) != 13 or index not in (0, 1, 2, 3) or not items[index].is_enabled():
            raise DriverError("FILE_MENU_PROFILE_MISMATCH_OR_DISABLED")
        # Qt UIA Invoke can block until a native modal closes. Reacquire the element in its own COM thread.
        hwnd = menu.handle
        def invoke():
            import comtypes
            comtypes.CoInitializeEx(0)
            try:
                wrapper = Desktop(backend="uia").window(handle=hwnd).wrapper_object()
                wrapper.children(control_type="MenuItem")[index].invoke()
            except Exception:
                # The postcondition is checked by the caller; Invoke may fail after successfully opening a modal.
                pass
            finally:
                comtypes.CoUninitialize()
        thread = threading.Thread(target=invoke, daemon=True)
        thread.start()

    def _common_dialog(self, save=False):
        def find():
            for item in self._owned_windows():
                if item["class"] == "#32770" and (("保存" in item["title"] or "另存" in item["title"])
                                                       if save else "打开" in item["title"]):
                    return item["hwnd"]
            return None
        return self._wait(find)

    def _dialog_path(self, hwnd, path):
        """Commit an absolute path through the native edit's change notifications.

        EM_REPLACESEL emits EN_CHANGE; unlike a keyboard Ctrl+A sequence it
        cannot leak a literal 'a' when a modifier key is missed.
        """
        import win32gui
        import win32con
        import win32process
        from ctypes import wintypes as wt
        self._unlocked()
        owner = win32gui.GetWindow(hwnd, 4) if win32gui.IsWindow(hwnd) else None
        # Qt's File menu can temporarily own IFileDialog through its hidden
        # popup HWND. This exact 2.1.7.2 owner profile was observed locally.
        popup_owner = bool(owner and win32gui.IsWindow(owner) and
            win32process.GetWindowThreadProcessId(owner)[1] == self.pid and
            win32gui.GetClassName(owner) == "Qt5QWindowPopupSaveBits" and
            not win32gui.IsWindowVisible(owner))
        if not win32gui.IsWindow(hwnd) or win32gui.GetClassName(hwnd) != "#32770" or \
                win32process.GetWindowThreadProcessId(hwnd)[1] != self.pid or \
                (owner != self.hwnd and not popup_owner):
            raise DriverError("FILE_DIALOG_IDENTITY_CHANGED")
        if not win32gui.IsWindowEnabled(hwnd):
            raise DriverError("FILE_DIALOG_BLOCKED_BY_PROMPT")
        filename = str(Path(path).resolve())
        edits = []
        def visit(control, _):
            if win32gui.GetClassName(control) == "Edit" and win32gui.GetDlgCtrlID(control) in (1148, 1001):
                edits.append(control)
        win32gui.EnumChildWindows(hwnd, visit, None)
        if len(edits) != 1:
            raise DriverError("FILENAME_CONTROL_AMBIGUOUS_OR_MISSING")
        edit = edits[0]
        send = ctypes.windll.user32.SendMessageTimeoutW
        send.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                         ctypes.POINTER(ctypes.c_size_t)]
        send.restype = wt.LPARAM
        def message(code, wparam=0, lparam=0):
            self._remaining()
            outcome = ctypes.c_size_t()
            if not send(edit, code, wparam, lparam, 2, 2000, ctypes.byref(outcome)):
                raise DriverError("FILENAME_CONTROL_MESSAGE_FAILED")
            return outcome.value
        limit = message(0x00D5)  # EM_GETLIMITTEXT; measured in UTF-16 code units.
        if len(filename.encode("utf-16-le"))//2 > limit:
            raise DriverError("PATH_EXCEEDS_FILE_DIALOG_LIMIT")
        message(0x00B1, 0, -1)  # EM_SETSEL: replace the full filename, never append.
        value = ctypes.create_unicode_buffer(filename)
        message(0x00C2, 1, ctypes.cast(value, ctypes.c_void_p).value)  # EM_REPLACESEL.
        readback = ctypes.create_unicode_buffer(32768)
        message(win32con.WM_GETTEXT, len(readback), ctypes.cast(readback, ctypes.c_void_p).value)
        if readback.value != filename:
            raise DriverError("FILENAME_READBACK_MISMATCH")
        if not win32gui.IsWindowEnabled(hwnd):
            raise DriverError("FILE_DIALOG_BLOCKED_BY_PROMPT")
        button = win32gui.GetDlgItem(hwnd, 1)
        if not button or win32gui.GetClassName(button) != "Button":
            raise DriverError("FILE_DIALOG_CONFIRM_NOT_FOUND")
        win32gui.PostMessage(button, win32con.BM_CLICK, 0, 0)
        self._wait(lambda: not win32gui.IsWindow(hwnd))

    def _open_file(self, path):
        path = Path(path).resolve(strict=True)
        w = self._idle()
        try:
            self._selection(w)
        except DriverError as exc:
            if str(exc) != 'SELECTION_FIELDS_NOT_FOUND':
                raise
            # On the empty home page LaserMaker can launch an ownerless
            # native file dialog. Establish its normal editor first; keep
            # the strict dialog identity/owner checks unchanged.
            self._new_document()
        self._menu(1)
        self._dialog_path(self._common_dialog(), path)
        def opened():
            w = self._window()
            tab = self._active_tab(w).window_text()
            return w if tab in (path.name, path.stem) else None
        return self._wait(opened)

    def _selection(self, w):
        edits = self._controls(w, "Edit")
        xy = sizes = None
        for edit in edits:
            parent = edit.parent()
            children = parent.children()
            names = [c.window_text() for c in children]
            fields = [c for c in children if c.element_info.control_type == "Edit"]
            if "X" in names and "Y" in names and len(fields) == 2:
                xy = fields
            if names.count("%") == 2 and len(fields) == 4:
                sizes = [fields[0], fields[2]]
        if xy is None or sizes is None:
            raise DriverError("SELECTION_FIELDS_NOT_FOUND")
        return {"position_mm": [parse_dimension(e.get_value()) for e in xy],
                "selection_size_mm": [parse_dimension(e.get_value()) for e in sizes],
                "position_anchor": "application_current_anchor"}

    def _select_all(self, w):
        import win32gui
        with self._foreground(w.handle):
            if win32gui.GetForegroundWindow() != w.handle:
                raise DriverError("FOCUS_CHANGED")
            w.type_keys("^a", set_foreground=False, pause=.01, vk_packet=False)
        return self._wait(lambda: (s if min(s["selection_size_mm"]) > 0 else None)
                          if (s := self._selection(self._window())) else None)

    def _post_click(self, w, rectangle, double=False):
        import win32gui
        import win32con
        x, y = (rectangle.left+rectangle.right)//2, (rectangle.top+rectangle.bottom)//2
        x, y = win32gui.ScreenToClient(w.handle, (x, y))
        value = ((y & 0xffff) << 16) | (x & 0xffff)
        messages = [(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON), (win32con.WM_LBUTTONUP, 0)]
        if double:
            messages += [(win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON), (win32con.WM_LBUTTONUP, 0)]
        for message, state in messages:
            win32gui.PostMessage(w.handle, message, state, value)

    def _input_click(self, w, rectangle):
        """Qt editors require real mouse activation; verify its exact recipient."""
        import win32gui
        from pywinauto import mouse
        point = ((rectangle.left+rectangle.right)//2, (rectangle.top+rectangle.bottom)//2)
        foreground = win32gui.GetForegroundWindow()
        recipient = win32gui.GetAncestor(win32gui.WindowFromPoint(point), 2)
        if foreground != w.handle or recipient != w.handle:
            # Keep the failed recipient as evidence; never click through another app.
            evidence = {"expected_hwnd": w.handle, "foreground_hwnd": foreground,
                        "recipient_hwnd": recipient, "point": point,
                        "foreground_class": win32gui.GetClassName(foreground) if foreground else None,
                        "recipient_class": win32gui.GetClassName(recipient) if recipient else None}
            raise DriverError("DESKTOP_IN_USE_OR_CONTROL_OCCLUDED: " + json.dumps(evidence))
        mouse.click(coords=point)

    def _layer_rows(self, w):
        from collections import Counter
        from PIL import Image
        from .capture import capture_window
        tables = self._controls(w, "Table")
        if len(tables) != 1:
            raise DriverError("LAYER_TABLE_NOT_FOUND")
        cells = tables[0].children(control_type="DataItem")
        if len(cells) % 4 or not cells:
            raise DriverError("LAYER_TABLE_PROFILE_MISMATCH")
        with tempfile.TemporaryDirectory(prefix="lasermaker-window-") as directory:
            path = Path(directory) / "layers.png"
            with self._foreground(w.handle):
                capture_window(w.handle, path, timeout=min(6, self._remaining()))
            image = Image.open(path).convert("RGB")
        origin = w.rectangle()
        result = []
        palette = {"#ff0000": (255, 0, 0), "#000000": (0, 0, 0),
                   "#ffff00": (255, 255, 0), "#0000ff": (0, 0, 255)}
        for i in range(0, len(cells), 4):
            r = cells[i].rectangle()
            pixels = Counter(image.crop((r.left-origin.left, r.top-origin.top,
                                         r.right-origin.left, r.bottom-origin.top)).get_flattened_data())
            counts = {name: sum(count for rgb, count in pixels.items()
                               if max(abs(rgb[j]-target[j]) for j in range(3)) < 12)
                      for name, target in palette.items()}
            ordered = sorted(counts.items(), key=lambda p: p[1], reverse=True)
            if ordered[0][1] < 80 or ordered[0][1] < ordered[1][1]*2:
                raise DriverError("LAYER_COLOR_NOT_UNAMBIGUOUS")
            result.append({"color": ordered[0][0], "speed_mm_s": parse_dimension(cells[i+1].window_text()),
                           "power_max_percent": parse_dimension(cells[i+2].window_text()),
                           "_rectangle": cells[i+1].rectangle()})
        return result

    def _layers(self, w):
        return [{k: v for k, v in row.items() if not k.startswith("_")} for row in self._layer_rows(w)]

    def _new_document(self):
        w = self._idle()
        before = {c.window_text() for c in self._controls(w, "Tab")}
        self._menu(0)
        def created():
            modals = [d for d in self._owned_windows() if d["hwnd"] != w.handle and d["owner"] == w.handle
                      and d["class"] != "Qt5QWindowPopupSaveBits"]
            if modals:
                raise DriverError("NEW_DOCUMENT_BLOCKED_BY_MODAL: " + json.dumps(modals, ensure_ascii=False))
            return any(c.window_text().startswith("设计") and c.window_text() not in before
                       for c in self._controls(self._window(), "Tab"))
        self._wait(created)
        return self._window()

    def import_design(self, path, expected_bounds=None):
        self._new_document()
        w = self._open_file(path)
        selection = self._wait(lambda: self._selection(w))  # SVG importer selects imported geometry.
        if expected_bounds:
            expected = [expected_bounds[2]-expected_bounds[0], expected_bounds[3]-expected_bounds[1]]
            if any(abs(a-b) > .05 for a, b in zip(selection["selection_size_mm"], expected)):
                raise DriverError("IMPORT_SIZE_MISMATCH")
        return {"path": str(Path(path).resolve()), "document_name": self._active_tab(w).window_text(),
                "import_verified": True, **selection, "layers": self._layers(w),
                "note": "Relative layout and size verified. Bed placement depends on the application's anchor/origin."}

    def _parameter_window(self):
        from pywinauto import Desktop
        def find():
            for item in self._owned_windows():
                if item["title"] == "加工参数":
                    return Desktop(backend="uia").window(handle=item["hwnd"]).wrapper_object()
            return None
        return self._wait(find)

    def _parameter_edit(self, dialog, label):
        labels = [c for c in self._controls(dialog, "Text") if c.window_text() == label]
        if len(labels) != 1:
            raise DriverError("PARAMETER_LABEL_NOT_FOUND: " + label)
        r = labels[0].rectangle()
        y = (r.top+r.bottom)/2
        edits = [c for c in self._controls(dialog, "Edit") if c.rectangle().left > r.right and
                 abs((c.rectangle().top+c.rectangle().bottom)/2-y) < 6]
        if len(edits) != 1:
            raise DriverError("PARAMETER_EDIT_AMBIGUOUS: " + label)
        return edits[0]

    def _enter_numeric(self, dialog, label, value):
        # Retrying focus and an absolute replacement cannot duplicate geometry.
        # Reacquire the editor each time: Qt can replace its accessibility object.
        for _ in range(3):
            self._remaining()
            edit = self._parameter_edit(dialog, label)
            self._input_click(dialog, edit.rectangle())
            until = time.monotonic()+.6
            while not edit.has_keyboard_focus() and time.monotonic() < until:
                time.sleep(.04)
            if not edit.has_keyboard_focus():
                continue
            dialog.type_keys("^a", set_foreground=False, vk_packet=False)
            dialog.type_keys(f"{value:g}", set_foreground=False, vk_packet=False)
            until = time.monotonic()+.8
            while True:
                actual = self._parameter_edit(dialog, label).get_value()
                try:
                    parsed = parse_dimension(actual)
                except ValueError:
                    parsed = None  # Qt may expose a transient empty edit value.
                if parsed is not None and abs(parsed-value) <= .005:
                    return
                if time.monotonic() >= until:
                    break
                time.sleep(.04)
        raise DriverError("PARAMETER_INPUT_NOT_CONFIRMED: " + label)

    def set_process(self, color, values):
        values = validate_process(values)
        w = self._idle()
        rows = [row for row in self._layer_rows(w) if row["color"] == color]
        if len(rows) != 1:
            raise DriverError("LAYER_COLOR_NOT_FOUND")
        self._post_click(w, rows[0]["_rectangle"], double=True)
        dialog = self._parameter_window()
        mode = [c for c in self._controls(dialog, "ListItem") if c.window_text() == MODES[values["mode"]]]
        if len(mode) != 1:
            raise DriverError("PROCESS_MODE_NOT_FOUND")
        if not mode[0].is_selected():
            with self._foreground(dialog.handle):
                self._input_click(dialog, mode[0].rectangle())
                self._wait(lambda: mode[0].is_selected())
        with self._foreground(dialog.handle):
            fields = [("速度", "speed_mm_s"), ("功率", "power_max_percent")]
            if values['mode'] in ('cut','score'):
                fields.append(("转角功率", "power_min_percent"))
            for label, key in fields:
                self._enter_numeric(dialog, label, values[key])
        selected = [c.window_text() for c in self._controls(dialog, "ListItem")
                    if c.window_text() in MODES.values() and c.is_selected()]
        if selected != [MODES[values["mode"]]]:
            raise DriverError("PROCESS_MODE_READBACK_MISMATCH")
        confirmation = [c for c in self._controls(dialog, "Button") if c.window_text().startswith("确认")]
        if len(confirmation) != 1:
            raise DriverError("PROCESS_CONFIRM_NOT_FOUND")
        hwnd = dialog.handle
        confirmation[0].invoke()
        import win32gui
        self._wait(lambda: not win32gui.IsWindow(hwnd))
        after = [row for row in self._layers(self._window()) if row["color"] == color]
        if len(after) != 1 or any(abs(after[0][key]-values[key]) > .005
                                 for key in ("speed_mm_s", "power_max_percent")):
            raise DriverError("PROCESS_TABLE_READBACK_MISMATCH")
        return {"color": color, "verified": values, "table_readback": after[0],
                "document_name": self._active_tab(self._window()).window_text()}

    def verify_process(self, color, expected):
        expected = validate_process(expected)
        w = self._idle()
        rows = [row for row in self._layer_rows(w) if row["color"] == color]
        if len(rows) != 1:
            raise DriverError("LAYER_COLOR_NOT_FOUND")
        self._post_click(w, rows[0]["_rectangle"], double=True)
        dialog = self._parameter_window()
        modes = [key for key, label in MODES.items() for c in self._controls(dialog, "ListItem")
                 if c.window_text() == label and c.is_selected()]
        actual = {"mode": modes[0] if len(modes) == 1 else None}
        fields = [("速度", "speed_mm_s"), ("功率", "power_max_percent")]
        if actual['mode'] in ('cut','score'):
            fields.append(("转角功率", "power_min_percent"))
        for label, key in fields:
            actual[key] = parse_dimension(self._parameter_edit(dialog, label).get_value())
        buttons = [c for c in self._controls(dialog, "Button") if c.window_text().startswith("确认")]
        if len(buttons) != 1:
            raise DriverError("PROCESS_CONFIRM_NOT_FOUND")
        hwnd = dialog.handle
        buttons[0].invoke()
        import win32gui
        self._wait(lambda: not win32gui.IsWindow(hwnd))
        keys = ['speed_mm_s','power_max_percent']
        if expected['mode'] in ('cut','score'):
            keys.append('power_min_percent')
        if actual["mode"] != expected["mode"] or any(abs(actual[k]-expected[k]) > .005 for k in keys):
            raise DriverError("SAVED_PROCESS_READBACK_MISMATCH: " + json.dumps(actual))
        return {"color": color, "process_readback": actual, "process_verified": True,
                "document_name": self._active_tab(self._window()).window_text()}

    def save_native(self, path):
        from .native import read_native
        path = Path(path).resolve()
        if path.suffix.lower() != ".lcpx" or path.exists():
            raise DriverError("NEW_LCPX_PATH_REQUIRED")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._idle()
        self._menu(3)
        self._dialog_path(self._common_dialog(save=True), path)
        self._wait(lambda: path.is_file() and path.stat().st_size >= 346)
        native = read_native(path)
        w = self._idle()
        tab = self._active_tab(w).window_text()
        if tab not in (path.name, path.stem):
            raise DriverError("SAVED_DOCUMENT_NAME_MISMATCH")
        return {"path": str(path), "sha256": native["sha256"], "save_verified": True,
                "reopen_verified": False, "document_name": tab, "layers": self._layers(w)}

    def _close_saved_tab(self, path):
        import win32gui
        from pywinauto.win32structures import RECT
        w = self.assert_document(Path(path).name)
        tab = self._active_tab(w)
        r = tab.rectangle()
        # Observed close glyph is centred half a tab-height from the right edge.
        h = r.bottom-r.top
        point = RECT()
        point.left = point.right = int(r.right-h*.5)
        point.top = point.bottom = (r.top+r.bottom)//2
        self._post_click(w, point)
        def closed():
            for item in self._owned_windows():
                if item["owner"] == w.handle and item["hwnd"] != w.handle and item["class"] != "Qt5QWindowPopupSaveBits":
                    raise DriverError("UNSAVED_DOCUMENT_OR_UNKNOWN_MODAL: " + item["title"])
            names = [c.window_text() for c in self._controls(self._window(), "TabItem")]
            return Path(path).name not in names and Path(path).stem not in names
        self._wait(closed)

    def reload_and_verify(self, path, expected_size=None):
        from .native import read_native
        path = Path(path).resolve(strict=True)
        before = read_native(path)
        w = self._idle()
        active = self._active_tab(w).window_text()
        if active in (path.name, path.stem):
            self._close_saved_tab(path)
        elif any(c.window_text() in (path.name, path.stem) for c in self._controls(w, "TabItem")):
            raise DriverError("TARGET_ALREADY_OPEN_IN_ANOTHER_TAB")
        w = self._open_file(path)
        selection = self._select_all(w)
        if expected_size and any(abs(a-b) > .05 for a, b in zip(selection["selection_size_mm"], expected_size)):
            raise DriverError("REOPEN_SIZE_MISMATCH")
        after = read_native(path)
        if before["sha256"] != after["sha256"]:
            raise DriverError("NATIVE_CHANGED_DURING_READBACK")
        return {"path": str(path), "sha256": after["sha256"], "reopen_verified": True,
                "document_name": self._active_tab(self._window()).window_text(),
                **selection, "layers": self._layers(self._window()),
                "process_order_verified": False, "simulation_verified": False}

    def _controls(self, w, control_type=None):
        self._remaining()
        return w.descendants(control_type=control_type) if control_type else w.descendants()

    def _text(self, w):
        return [c.window_text() for c in self._controls(w) if c.window_text()]

    def _wait(self, predicate):
        import sys
        caller = sys._getframe(1)
        location = f"{caller.f_code.co_name}:{caller.f_lineno}"
        while True:
            try:
                self._remaining()
            except DriverError as exc:
                raise DriverError(str(exc) + " at " + location) from exc
            try:
                value = predicate()
            except DriverError as exc:
                if str(exc) not in ("ACTIVE_DOCUMENT_AMBIGUOUS", "SELECTION_FIELDS_NOT_FOUND"):
                    raise
                value = None
            if value:
                return value
            time.sleep(.15)

    def inspect(self):
        w = self._window()
        controls = []
        for c in self._controls(w):
            info = c.element_info
            text = c.window_text()
            value = None
            if info.control_type == "Edit":
                try:
                    value = c.get_value()
                except Exception:
                    pass
            if text or value is not None or info.control_type in ("ComboBox", "Spinner", "DataGrid", "Table"):
                controls.append({"type": info.control_type, "name": text, "value": value,
                                 "automation_id": info.automation_id})
        version = next((s for s in (x["name"] for x in controls) if "LaserMaker V" in s), None)
        return {"pid": self.pid, "hwnd": w.handle, "title": w.window_text(),
                "rectangle": [w.rectangle().left, w.rectangle().top, w.rectangle().right, w.rectangle().bottom],
                "version_label": version,
                "supported_version": SUPPORTED_VERSION, "controls": controls,
                "device_start_available": False}

    def screenshot(self, path):
        from .capture import capture_window, recognize_window_image
        w = self._window()
        path = Path(path).resolve()
        with self._foreground(w.handle):
            result = capture_window(w.handle, path)
        return {**result, "screenshot": str(path), "ocr": recognize_window_image(path)}


def desktop_lock():
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LaserMakerAgent"
    return file_lock(root / "desktop.lock", timeout=3)
