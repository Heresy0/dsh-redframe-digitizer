"""Private native-window primitives; no mouse input or third-party UI library."""
import ctypes as C
from ctypes import wintypes as W
import json, sys, time, subprocess
from pathlib import Path

if sys.platform != 'win32':
    raise RuntimeError('GetData desktop export requires Windows')
u = C.WinDLL('user32', use_last_error=True)
CB = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
u.EnumWindows.argtypes = [CB, W.LPARAM]
u.EnumChildWindows.argtypes = [W.HWND, CB, W.LPARAM]
u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.GetMenu.argtypes = [W.HWND]; u.GetMenu.restype = W.HMENU
u.GetSubMenu.argtypes = [W.HMENU, C.c_int]; u.GetSubMenu.restype = W.HMENU
u.GetMenuItemCount.argtypes = [W.HMENU]
u.GetMenuItemID.argtypes = [W.HMENU, C.c_int]; u.GetMenuItemID.restype = W.UINT
u.GetMenuStringW.argtypes = [W.HMENU, W.UINT, W.LPWSTR, C.c_int, W.UINT]
u.GetDlgCtrlID.argtypes = [W.HWND]
u.IsWindowVisible.argtypes = [W.HWND]
u.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.POINTER(C.c_size_t)]

def string(h, cls=False):
    b = C.create_unicode_buffer(2048)
    (u.GetClassNameW if cls else u.GetWindowTextW)(h,b,len(b))
    return b.value

def info(h):
    pid=W.DWORD(); u.GetWindowThreadProcessId(h,C.byref(pid))
    return dict(hwnd=int(h), pid=pid.value, cls=string(h,True), text=string(h), id=u.GetDlgCtrlID(h), visible=bool(u.IsWindowVisible(h)))

def windows(pid=None, parent=None):
    out=[]
    @CB
    def cb(h,l):
        row=info(h)
        if pid is None or row['pid']==pid: out.append(row)
        return True
    if parent: u.EnumChildWindows(parent,cb,0)
    else: u.EnumWindows(cb,0)
    return out

def menus(menu):
    out=[]
    for i in range(u.GetMenuItemCount(menu)):
        b=C.create_unicode_buffer(512);u.GetMenuStringW(menu,i,b,len(b),0x400)
        sub=u.GetSubMenu(menu,i)
        out.append(dict(text=b.value, command=u.GetMenuItemID(menu,i), children=menus(sub) if sub else []))
    return out

def send(h,msg,wp=0,lp=0):
    result=C.c_size_t()
    if not u.SendMessageTimeoutW(h,msg,wp,lp,2,3000,C.byref(result)):
        raise OSError(C.get_last_error(),'SendMessageTimeout failed')
    return result.value

def set_text(h,text):
    buf=C.create_unicode_buffer(str(text));return send(h,0xC,0,C.cast(buf,C.c_void_p).value)

