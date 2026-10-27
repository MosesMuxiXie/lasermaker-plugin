import struct
from pathlib import Path

import pytest

from lasermaker_agent.native import read_native
from lasermaker_agent.windows_driver import validate_process, parse_dimension


def test_native_short_wrong_version_and_valid_header(tmp_path):
    filename = tmp_path / "test.lcpx"
    for data in (b"PRJF", b"NOT A PROJECT" * 30):
        filename.write_bytes(data)
        with pytest.raises(ValueError):
            read_native(filename)
    data = bytearray(346)
    data[:4] = b"PRJF"
    struct.pack_into("<III", data, 4, 11, 12, 2)
    filename.write_bytes(data)
    result = read_native(filename)
    assert result["format"] == "PRJF"
    assert result["version"] == [11, 12]
    assert result["layer_count"] == 2
    assert result["geometry_authoritative"] is False
    struct.pack_into("<I", data, 4, 99)
    filename.write_bytes(data)
    with pytest.raises(ValueError, match="UNSUPPORTED"):
        read_native(filename)


@pytest.mark.parametrize("values", [
    {"mode": "cut", "speed_mm_s": 0, "power_max_percent": 10},
    {"mode": "score", "speed_mm_s": 30, "power_max_percent": 101},
    {"mode": "cut", "speed_mm_s": 30, "power_max_percent": 20, "power_min_percent": 30},
    {"mode": "cut", "speed_mm_s": float("nan"), "power_max_percent": 20},
    {"mode": "emit", "speed_mm_s": 30, "power_max_percent": 20},
])
def test_invalid_process_never_reaches_ui(values):
    with pytest.raises(ValueError):
        validate_process(values)


def test_parse_numeric_dimensions_requires_unambiguous_units():
    assert parse_dimension("130.000 mm") == 130
    assert parse_dimension("110,50 mm") == 110.5
    with pytest.raises(ValueError):
        parse_dimension("130 px")
    with pytest.raises(ValueError):
        parse_dimension("")


def test_restarted_application_cannot_reuse_an_old_document_binding():
    from lasermaker_agent.windows_driver import WindowsDriver, DriverError
    driver = object.__new__(WindowsDriver)
    driver.pid = 999
    driver._idle = lambda: object()
    with pytest.raises(DriverError, match="APPLICATION_PROCESS_CHANGED"):
        driver.assert_document("unique-project-design.lcpx", expected_pid=111)


def test_disabled_window_is_reported_before_uia_traversal(monkeypatch):
    import win32gui, win32process, pywinauto
    from lasermaker_agent.windows_driver import WindowsDriver, DriverError
    driver = object.__new__(WindowsDriver)
    driver.pid, driver.hwnd = 111, 222
    import time
    driver.deadline = time.monotonic()+10
    driver._owned_windows = lambda: [{"hwnd": 333, "owner": 222, "title": "unknown prompt"}]
    monkeypatch.setattr(win32gui, "IsWindow", lambda h: True)
    monkeypatch.setattr(win32gui, "IsWindowEnabled", lambda h: False)
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", lambda h: (1, 111))
    def forbidden(*args, **kwargs):
        raise AssertionError("UIA traversal reached an inaccessible modal state")
    monkeypatch.setattr(pywinauto, "Desktop", forbidden)
    with pytest.raises(DriverError, match="UNEXPECTED_MODAL"):
        driver._window()


@pytest.mark.parametrize("transient_empty", [False, True])
def test_numeric_input_retries_focus_without_typing_into_an_unfocused_editor(transient_empty):
    import time
    from lasermaker_agent.windows_driver import WindowsDriver
    driver = object.__new__(WindowsDriver)
    driver.deadline = time.monotonic()+10
    state = {"clicks": 0, "value": "100", "typed": []}
    class Edit:
        def rectangle(self):
            return object()
        def has_keyboard_focus(self):
            return state["clicks"] >= 2
        def get_value(self):
            if transient_empty and state["typed"] and not state.get("returned_empty"):
                state["returned_empty"] = True
                return ""
            return state["value"]
    class Dialog:
        def type_keys(self, text, **kwargs):
            assert state["clicks"] >= 2
            state["typed"].append(text)
            if text != "^a":
                state["value"] = text
    driver._parameter_edit = lambda dialog, label: Edit()
    def click(dialog, rectangle):
        state["clicks"] += 1
    driver._input_click = click
    driver._enter_numeric(Dialog(), "速度", 101)
    assert state["clicks"] == 2 and state["typed"] == ["^a", "101"]


def test_foreground_accepts_a_short_os_activation_transition(monkeypatch):
    import time, win32gui, win32api, win32process
    from lasermaker_agent.windows_driver import WindowsDriver
    driver = object.__new__(WindowsDriver)
    driver.deadline = time.monotonic()+10
    driver._unlocked = lambda: None
    state = {"active": 1, "pending": None, "polls": 0}
    def foreground():
        if state["pending"] is not None:
            state["polls"] += 1
            if state["polls"] >= 2:
                state["active"], state["pending"] = state["pending"], None
        return state["active"]
    def activate(hwnd):
        state["pending"], state["polls"] = hwnd, 0
    monkeypatch.setattr(win32gui, "GetForegroundWindow", foreground)
    monkeypatch.setattr(win32gui, "SetForegroundWindow", activate)
    monkeypatch.setattr(win32gui, "BringWindowToTop", lambda hwnd: None)
    monkeypatch.setattr(win32gui, "IsWindowEnabled", lambda hwnd: True)
    monkeypatch.setattr(win32gui, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(win32api, "GetCurrentThreadId", lambda: 17)
    monkeypatch.setattr(win32process, "GetWindowThreadProcessId", lambda hwnd: (17, 111))
    with driver._foreground(2):
        assert foreground() == 2


@pytest.mark.parametrize('limit,popup_owner',[(259,False),(259,True),(2,False)])
def test_common_dialog_uses_notifying_native_edit_messages_without_keyboard(tmp_path,monkeypatch,limit,popup_owner):
    import ctypes,time,win32gui,win32process
    from lasermaker_agent.windows_driver import WindowsDriver,DriverError
    driver=object.__new__(WindowsDriver);driver.pid=123;driver.hwnd=11;driver.deadline=time.monotonic()+5
    driver._unlocked=lambda:None
    state={'text':'old.svg','open':True,'messages':[]}
    monkeypatch.setattr(win32gui,'IsWindow',lambda h:state['open'])
    monkeypatch.setattr(win32gui,'IsWindowEnabled',lambda h:True)
    monkeypatch.setattr(win32gui,'GetClassName',lambda h:'Edit' if h==33 else 'Button' if h==44 else 'Qt5QWindowPopupSaveBits' if h==55 else '#32770')
    monkeypatch.setattr(win32gui,'GetDlgCtrlID',lambda h:1148)
    monkeypatch.setattr(win32gui,'GetWindow',lambda h,flag:55 if popup_owner else 11)
    monkeypatch.setattr(win32gui,'IsWindowVisible',lambda h:h!=55)
    monkeypatch.setattr(win32process,'GetWindowThreadProcessId',lambda h:(1,123))
    monkeypatch.setattr(win32gui,'EnumChildWindows',lambda h,visit,arg:visit(33,arg))
    monkeypatch.setattr(win32gui,'GetDlgItem',lambda h,index:44)
    def post(*args):state['open']=False
    monkeypatch.setattr(win32gui,'PostMessage',post)
    def send(hwnd,message,wparam,lparam,flags,timeout,outcome):
        state['messages'].append(message)
        if message==0xD5:
            ctypes.cast(outcome,ctypes.POINTER(ctypes.c_size_t))[0]=limit
        elif message==0xB1:
            assert wparam==0 and lparam==-1
        elif message==0xC2:
            assert 0xB1 in state['messages']
            state['text']=ctypes.wstring_at(lparam)
        elif message==13:
            value=ctypes.create_unicode_buffer(state['text'])
            ctypes.memmove(lparam,value,ctypes.sizeof(value))
        return 1
    monkeypatch.setattr(ctypes.windll.user32,'SendMessageTimeoutW',send)
    import pywinauto
    monkeypatch.setattr(pywinauto,'Desktop',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No keyboard/UIA needed for native filename edit')))
    path=tmp_path/'中文 path.svg'
    if limit==2:
        with pytest.raises(DriverError,match='PATH_EXCEEDS_FILE_DIALOG_LIMIT'):
            driver._dialog_path(22,path)
        assert state['open'] and 0xC2 not in state['messages']
    else:
        driver._dialog_path(22,path)
        assert state['text']==str(path.resolve()) and not state['open']


@pytest.mark.parametrize('mode',['engrave','shallow_engrave'])
def test_engraving_processes_have_no_corner_power_control(monkeypatch,mode):
    import contextlib,time,win32gui
    from types import SimpleNamespace
    from lasermaker_agent.windows_driver import WindowsDriver,MODES
    d=object.__new__(WindowsDriver);d.deadline=time.monotonic()+10
    w=SimpleNamespace(handle=11);dialog=SimpleNamespace(handle=22)
    selected=SimpleNamespace(window_text=lambda:MODES[mode],is_selected=lambda:True)
    button=SimpleNamespace(window_text=lambda:'确认',invoke=lambda:None)
    d._idle=lambda:w;d._window=lambda:w;d._parameter_window=lambda:dialog
    d._controls=lambda target,kind:[selected] if kind=='ListItem' else [button] if kind=='Button' else []
    d._layer_rows=lambda target:[{'color':'#0000ff','_rectangle':object(),'speed_mm_s':100,'power_max_percent':15}]
    d._layers=lambda target:[{'color':'#0000ff','speed_mm_s':100,'power_max_percent':15}]
    d._post_click=lambda *a,**k:None;d._foreground=lambda h:contextlib.nullcontext()
    d._active_tab=lambda target:SimpleNamespace(window_text=lambda:'test.svg')
    fields=[]
    def enter(target,label,value):
        assert label in ('速度','功率')
        fields.append(label)
    d._enter_numeric=enter
    def edit(target,label):
        assert label in ('速度','功率')
        return SimpleNamespace(get_value=lambda:'100' if label=='速度' else '15')
    d._parameter_edit=edit
    monkeypatch.setattr(win32gui,'IsWindow',lambda h:False)
    values={'mode':mode,'speed_mm_s':100,'power_max_percent':15}
    result=d.set_process('#0000ff',values)
    assert fields==['速度','功率'] and 'power_min_percent' not in result['verified']
    verified=d.verify_process('#0000ff',values)
    assert 'power_min_percent' not in verified['process_readback']
    with pytest.raises(ValueError,match='CORNER_POWER_NOT_APPLICABLE'):
        validate_process({**values,'power_min_percent':13})
