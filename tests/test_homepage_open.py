import pytest

from lasermaker_agent.windows_driver import WindowsDriver,DriverError


@pytest.mark.parametrize('on_homepage',[True,False])
def test_open_from_homepage_establishes_an_editor_before_file_dialog(tmp_path,on_homepage):
    path=tmp_path/'native.lcpx';path.write_bytes(b'fixture')
    driver=WindowsDriver.__new__(WindowsDriver)
    calls=[];editor=not on_homepage
    driver._idle=lambda:'window'
    driver._window=lambda:'window'
    def selection(window):
        if not editor:raise DriverError('SELECTION_FIELDS_NOT_FOUND')
        return {'selection_size_mm':[0,0]}
    driver._selection=selection
    def new_document():
        nonlocal editor
        editor=True;calls.append('new')
    driver._new_document=new_document
    def menu(index):
        assert editor,'Native file dialog from empty home has no owner HWND'
        calls.append(('menu',index))
    driver._menu=menu
    driver._common_dialog=lambda:123
    driver._dialog_path=lambda handle,p:calls.append(('path',handle,p))
    class Tab:
        def window_text(self):return path.name
    driver._active_tab=lambda window:Tab()
    driver._wait=lambda predicate:predicate()
    assert driver._open_file(path)=='window'
    assert calls[0]==('new' if on_homepage else ('menu',1))


def test_other_window_failure_does_not_create_an_editor(tmp_path):
    path=tmp_path/'native.lcpx';path.write_bytes(b'fixture')
    driver=WindowsDriver.__new__(WindowsDriver);driver._idle=lambda:'window'
    def blocked(window):raise DriverError('DESKTOP_BLOCKED')
    driver._selection=blocked
    driver._new_document=lambda:pytest.fail('Unexpected error must propagate')
    driver._menu=lambda index:pytest.fail('Must check the editor before opening a dialog')
    with pytest.raises(DriverError,match='DESKTOP_BLOCKED'):driver._open_file(path)
