from __future__ import annotations

import ctypes
import os
import uuid


def show_shell_context_menu(hwnd: int, path: str, screen_x: int, screen_y: int):
    from ctypes import wintypes as w

    HRESULT = ctypes.c_long
    UINT = ctypes.c_uint
    PTR = ctypes.c_void_p
    ULONG = ctypes.c_ulong
    WINMETHOD = ctypes.WINFUNCTYPE

    class GUID(ctypes.Structure):
        _fields_ = [('Data1', w.DWORD), ('Data2', w.WORD), ('Data3', w.WORD),
                    ('Data4', ctypes.c_ubyte * 8)]

    def guid(value):
        return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)

    iid_folder = guid('000214e6-0000-0000-c000-000000000046')
    iid_menu = guid('000214e4-0000-0000-c000-000000000046')
    iid_menu2 = guid('000214f4-0000-0000-c000-000000000046')
    iid_menu3 = guid('bcfce0a0-ec17-11d0-8d10-00a0c90f2719')

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    user32 = ctypes.windll.user32
    shell32.SHParseDisplayName.argtypes = [w.LPCWSTR, PTR, ctypes.POINTER(PTR), w.DWORD, PTR]
    shell32.SHParseDisplayName.restype = HRESULT
    shell32.SHBindToParent.argtypes = [PTR, ctypes.POINTER(GUID), ctypes.POINTER(PTR), ctypes.POINTER(PTR)]
    shell32.SHBindToParent.restype = HRESULT
    user32.CreatePopupMenu.restype = PTR
    user32.DestroyMenu.argtypes = [PTR]
    user32.TrackPopupMenuEx.argtypes = [PTR, UINT, ctypes.c_int, ctypes.c_int, PTR, PTR]
    user32.TrackPopupMenuEx.restype = UINT

    def method(obj, index, result_type, *args):
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(PTR))).contents
        return WINMETHOD(result_type, PTR, *args)(vtbl[index])

    def check(hr):
        if hr < 0:
            print(f'Windows Shell HRESULT 0x{hr & 0xffffffff:08x}')

    def release(obj):
        if obj.value:
            method(obj, 2, ULONG)(obj)

    pidl = PTR()
    folder = PTR()
    menu_iface = PTR()
    menu2 = PTR()
    menu3 = PTR()
    popup = None

    check(shell32.SHParseDisplayName(os.path.abspath(path), None, ctypes.byref(pidl), 0, None))
    try:
        child_pidl = PTR()
        check(shell32.SHBindToParent(pidl, ctypes.byref(iid_folder),
                                     ctypes.byref(folder), ctypes.byref(child_pidl)))
        try:
            get_ui_object = method(folder, 10, HRESULT, PTR, UINT, ctypes.POINTER(PTR),
                                   ctypes.POINTER(GUID), PTR, ctypes.POINTER(PTR))
            children = (PTR * 1)(child_pidl)
            check(get_ui_object(folder, PTR(hwnd), 1, children, ctypes.byref(iid_menu), None, ctypes.byref(menu_iface)))
            popup = user32.CreatePopupMenu()
            if not popup:
                raise ctypes.WinError()
            check(method(menu_iface, 3, HRESULT, PTR, UINT, UINT, UINT, UINT)(
                menu_iface, popup, 0, 1, 0x7fff, 0))
            qi = method(menu_iface, 0, HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(PTR))
            qi(menu_iface, ctypes.byref(iid_menu3), ctypes.byref(menu3))
            if not menu3.value:
                qi(menu_iface, ctypes.byref(iid_menu2), ctypes.byref(menu2))
            original_wndproc = None
            callback = None
            GWL_WNDPROC = -4
            LRESULT = ctypes.c_ssize_t
            user32.CallWindowProcW.restype = LRESULT
            user32.CallWindowProcW.argtypes = [PTR, PTR, UINT, PTR, PTR]
            set_wndproc = user32.SetWindowLongPtrW
            set_wndproc.argtypes = [PTR, ctypes.c_int, PTR]
            set_wndproc.restype = PTR
            if menu3.value or menu2.value:
                @WINMETHOD(LRESULT, PTR, UINT, PTR, PTR)
                def wndproc(h, msg, wp, lp):
                    if msg in (0x116, 0x117, 0x120, 0x11f, 0x2b, 0x2c, 0x123):
                        if menu3.value:
                            result = LRESULT()
                            hr = method(menu3, 7, HRESULT, UINT, PTR, PTR, ctypes.POINTER(LRESULT))(
                                menu3, msg, wp, lp, ctypes.byref(result))
                            if hr >= 0:
                                return result.value
                        elif menu2.value:
                            hr = method(menu2, 6, HRESULT, UINT, PTR, PTR)(menu2, msg, wp, lp)
                            if hr >= 0:
                                return 0
                    return user32.CallWindowProcW(original_wndproc, h, msg, wp, lp)

                callback = wndproc
                original_wndproc = set_wndproc(PTR(hwnd), GWL_WNDPROC, ctypes.cast(callback, PTR))
                if not original_wndproc:
                    raise ctypes.WinError()

            try:
                cmd = user32.TrackPopupMenuEx(popup, 0x100 | 0x2, screen_x, screen_y, PTR(hwnd), None)
            finally:
                if original_wndproc:
                    set_wndproc(PTR(hwnd), GWL_WNDPROC, original_wndproc)
                callback = None

            if cmd:
                class CMINVOKECOMMANDINFO(ctypes.Structure):
                    _fields_ = [('cbSize', w.DWORD), ('fMask', w.DWORD), ('hwnd', PTR),
                                ('lpVerb', PTR), ('lpParameters', PTR), ('lpDirectory', PTR),
                                ('nShow', ctypes.c_int), ('dwHotKey', w.DWORD), ('hIcon', PTR)]

                info = CMINVOKECOMMANDINFO()
                info.cbSize = ctypes.sizeof(info)
                info.hwnd = PTR(hwnd)
                info.lpVerb = PTR(cmd - 1)
                info.nShow = 1
                check(method(menu_iface, 4, HRESULT, ctypes.POINTER(CMINVOKECOMMANDINFO))(
                    menu_iface, ctypes.byref(info)))
        finally:
            if popup:
                user32.DestroyMenu(popup)
            release(menu3)
            release(menu2)
            release(menu_iface)
            release(folder)
    finally:
        if pidl.value:
            ole32.CoTaskMemFree.argtypes = [PTR]
            ole32.CoTaskMemFree(pidl)
