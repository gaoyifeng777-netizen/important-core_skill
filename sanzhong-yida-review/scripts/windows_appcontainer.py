"""Windows whole-process boundary; only mutate newly staged adapter-owned trees.

No existing user/runtime ACL changes. The host owns temporary role profiles.
Unique AppContainer profiles are created per run and role and must be deleted after use.
The launcher is the trusted broker;
its general-purpose tools must never be exposed to the model in the child process.
"""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import json, os, subprocess, time, uuid
from pathlib import Path

K = C.WinDLL('kernel32', use_last_error=True)
A = C.WinDLL('advapi32', use_last_error=True)
U = C.WinDLL('userenv', use_last_error=True)
P = C.c_void_p
SIZE = C.c_size_t
DWORD = W.DWORD

class STARTUPINFO(C.Structure):
    _fields_ = [('cb',DWORD),('lpReserved',W.LPWSTR),('lpDesktop',W.LPWSTR),('lpTitle',W.LPWSTR),('dwX',DWORD),('dwY',DWORD),('dwXSize',DWORD),('dwYSize',DWORD),('dwXCountChars',DWORD),('dwYCountChars',DWORD),('dwFillAttribute',DWORD),('dwFlags',DWORD),('wShowWindow',W.WORD),('cbReserved2',W.WORD),('lpReserved2',P),('hStdInput',W.HANDLE),('hStdOutput',W.HANDLE),('hStdError',W.HANDLE)]
class STARTUPINFOEX(C.Structure):
    _fields_ = [('StartupInfo',STARTUPINFO),('lpAttributeList',P)]
class PROCESS_INFORMATION(C.Structure):
    _fields_ = [('hProcess',W.HANDLE),('hThread',W.HANDLE),('dwProcessId',DWORD),('dwThreadId',DWORD)]
class SECURITY_CAPABILITIES(C.Structure):
    _fields_ = [('AppContainerSid',P),('Capabilities',P),('CapabilityCount',DWORD),('Reserved',DWORD)]
class SECURITY_ATTRIBUTES(C.Structure):
    _fields_ = [('nLength',DWORD),('lpSecurityDescriptor',P),('bInheritHandle',W.BOOL)]
class SID_AND_ATTRIBUTES(C.Structure):
    _fields_ = [('Sid',P),('Attributes',DWORD)]
class IO_COUNTERS(C.Structure):
    _fields_ = [(n,C.c_ulonglong) for n in ['ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount']]
class BASIC_LIMIT(C.Structure):
    _fields_ = [('PerProcessUserTimeLimit',C.c_longlong),('PerJobUserTimeLimit',C.c_longlong),('LimitFlags',DWORD),('MinimumWorkingSetSize',SIZE),('MaximumWorkingSetSize',SIZE),('ActiveProcessLimit',DWORD),('Affinity',SIZE),('PriorityClass',DWORD),('SchedulingClass',DWORD)]
class EXTENDED_LIMIT(C.Structure):
    _fields_ = [('BasicLimitInformation',BASIC_LIMIT),('IoInfo',IO_COUNTERS),('ProcessMemoryLimit',SIZE),('JobMemoryLimit',SIZE),('PeakProcessMemoryUsed',SIZE),('PeakJobMemoryUsed',SIZE)]

def sig(lib, name, args, result=W.BOOL):
    f=getattr(lib,name); f.argtypes=args; f.restype=result; return f
sig(U,'DeriveAppContainerSidFromAppContainerName',[W.LPCWSTR,C.POINTER(P)],C.c_long)
sig(U,'CreateAppContainerProfile',[W.LPCWSTR,W.LPCWSTR,W.LPCWSTR,P,DWORD,C.POINTER(P)],C.c_long)
sig(U,'DeleteAppContainerProfile',[W.LPCWSTR],C.c_long)
sig(A,'ConvertSidToStringSidW',[P,C.POINTER(W.LPWSTR)])
sig(A,'ConvertStringSidToSidW',[W.LPCWSTR,C.POINTER(P)])
sig(A,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[W.LPCWSTR,DWORD,C.POINTER(P),C.POINTER(DWORD)])
sig(A,'SetFileSecurityW',[W.LPCWSTR,DWORD,P])
sig(A,'OpenProcessToken',[W.HANDLE,DWORD,C.POINTER(W.HANDLE)])
sig(A,'GetTokenInformation',[W.HANDLE,C.c_int,P,DWORD,C.POINTER(DWORD)])
sig(K,'GetCurrentProcess',[],W.HANDLE)
sig(K,'LocalFree',[P],P)
sig(A,'FreeSid',[P],P)
sig(K,'InitializeProcThreadAttributeList',[P,DWORD,DWORD,C.POINTER(SIZE)])
sig(K,'UpdateProcThreadAttribute',[P,DWORD,SIZE,P,SIZE,P,P])
sig(K,'DeleteProcThreadAttributeList',[P],None)
sig(K,'CreateProcessW',[W.LPCWSTR,W.LPWSTR,P,P,W.BOOL,DWORD,P,W.LPCWSTR,C.POINTER(STARTUPINFOEX),C.POINTER(PROCESS_INFORMATION)])
sig(K,'CreateJobObjectW',[P,W.LPCWSTR],W.HANDLE)
sig(K,'SetInformationJobObject',[W.HANDLE,C.c_int,P,DWORD])
sig(K,'AssignProcessToJobObject',[W.HANDLE,W.HANDLE])
sig(K,'ResumeThread',[W.HANDLE],DWORD)
sig(K,'WaitForSingleObject',[W.HANDLE,DWORD],DWORD)
sig(K,'GetExitCodeProcess',[W.HANDLE,C.POINTER(DWORD)])
sig(K,'TerminateProcess',[W.HANDLE,W.UINT])
sig(K,'CloseHandle',[W.HANDLE])
sig(K,'CreateFileW',[W.LPCWSTR,DWORD,DWORD,C.POINTER(SECURITY_ATTRIBUTES),DWORD,DWORD,W.HANDLE],W.HANDLE)
sig(K,'OpenProcess',[DWORD,W.BOOL,DWORD],W.HANDLE)
sig(K,'TerminateJobObject',[W.HANDLE,W.UINT])

def check(ok, label):
    if not ok: raise C.WinError(C.get_last_error(),label)
def sid_text(ptr):
    out=W.LPWSTR(); check(A.ConvertSidToStringSidW(ptr,C.byref(out)),'ConvertSidToStringSidW')
    try: return out.value
    finally: K.LocalFree(out)
def token_info(process):
    token=W.HANDLE(); check(A.OpenProcessToken(process,0x8,C.byref(token)),'OpenProcessToken')
    def query(kind):
        n=DWORD(); A.GetTokenInformation(token,kind,None,0,C.byref(n)); b=C.create_string_buffer(n.value)
        check(A.GetTokenInformation(token,kind,b,n,C.byref(n)),f'GetTokenInformation {kind}'); return b
    try:
        user=query(1); ac=query(29); acsid=query(31); il=query(25)
        return {'user_sid':sid_text(C.cast(user,C.POINTER(SID_AND_ATTRIBUTES)).contents.Sid),'is_appcontainer':C.cast(ac,C.POINTER(DWORD)).contents.value,'appcontainer_sid':sid_text(C.cast(acsid,C.POINTER(P)).contents.value) if C.cast(acsid,C.POINTER(P)).contents.value else None,'integrity_sid':sid_text(C.cast(il,C.POINTER(SID_AND_ATTRIBUTES)).contents.Sid)}
    finally: K.CloseHandle(token)
def derive_sid(name):
    ptr=P(); hr=U.DeriveAppContainerSidFromAppContainerName(name,C.byref(ptr))
    if hr < 0: raise RuntimeError(f'DeriveAppContainerSid failed 0x{hr & 0xffffffff:08x}')
    return ptr,sid_text(ptr)
def create_profile(name):
    ptr=P(); hr=U.CreateAppContainerProfile(name,name,'Synthetic isolated role probe',None,0,C.byref(ptr))
    if hr < 0: raise RuntimeError(f'CreateAppContainerProfile failed 0x{hr & 0xffffffff:08x}; no existing profile reused')
    return ptr,sid_text(ptr)
def delete_profile(name):
    hr=U.DeleteAppContainerProfile(name)
    if hr < 0: raise RuntimeError(f'DeleteAppContainerProfile failed 0x{hr & 0xffffffff:08x}')

def set_acl(path: Path, sid: str, writable=False):
    """Apply a protected DACL only to a caller-created fixture and its contents."""
    path=Path(path).resolve(strict=True)
    marker=next((p for p in [path,*path.parents] if (p/'.sanzhong-appcontainer-stage').is_file() or (p/'.synthetic-appcontainer-root').is_file()),None)
    if marker is None: raise ValueError('Refusing ACL mutation outside marked synthetic root')
    user=token_info(K.GetCurrentProcess())['user_sid']
    flags='OICI' if path.is_dir() else ''
    rights='0x1301bf' if writable else '0x1200a9'
    sddl=f'D:P(A;{flags};FA;;;SY)(A;{flags};FA;;;BA)(A;{flags};FA;;;{user})(A;{flags};{rights};;;{sid})'
    sd=P(); check(A.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,C.byref(sd),None),'Convert DACL')
    filename=str(path)
    if len(filename) >= 248: filename='\\\\?\\'+filename
    try: check(A.SetFileSecurityW(filename,0x80000004,sd),'SetFileSecurity DACL')
    finally: K.LocalFree(sd)
    if writable:
        # This affects newly staged output only. No WRITE_DAC or WRITE_OWNER for child.
        sd=P(); check(A.ConvertStringSecurityDescriptorToSecurityDescriptorW('S:(ML;;NW;;;LW)',1,C.byref(sd),None),'Convert label')
        try: check(A.SetFileSecurityW(filename,0x10,sd),'SetFileSecurity label')
        finally: K.LocalFree(sd)

def acl_tree(root, sid, writable=False):
    paths=[Path(root),*Path(root).rglob('*')]
    if any(p.is_symlink() or bool(p.lstat().st_file_attributes & 0x400) for p in paths):
        raise ValueError('Reparse points forbidden in staged fixture')
    for p in paths: set_acl(p,sid,writable)

def launch(sid_ptr, argv, cwd, env=None, timeout=30, wait=True, network=False, stdin_path=None, stdout_path=None, stderr_path=None, host_io_root=None):
    """Create entire untrusted process in an AppContainer; return verified token."""
    n=SIZE(); K.InitializeProcThreadAttributeList(None,2,0,C.byref(n)); attr=C.create_string_buffer(n.value)
    check(K.InitializeProcThreadAttributeList(attr,2,0,C.byref(n)),'Init attributes')
    net_sid=P(); net_cap=None
    if network:
        check(A.ConvertStringSidToSidW('S-1-15-3-1',C.byref(net_sid)),'internetClient capability SID')
        net_cap=SID_AND_ATTRIBUTES(net_sid,4)
    caps=SECURITY_CAPABILITIES(sid_ptr,C.cast(C.pointer(net_cap),P) if net_cap else None,1 if network else 0,0)
    check(K.UpdateProcThreadAttribute(attr,0,0x20009,C.byref(caps),C.sizeof(caps),None,None),'Set SECURITY_CAPABILITIES')
    si=STARTUPINFOEX(); si.StartupInfo.cb=C.sizeof(si); si.lpAttributeList=C.cast(attr,P)
    pi=PROCESS_INFORMATION(); cmd=C.create_unicode_buffer(subprocess.list2cmdline([str(x) for x in argv]))
    clean_env={'SystemRoot':os.environ.get('SystemRoot',r'C:\Windows'),'WINDIR':os.environ.get('SystemRoot',r'C:\Windows'),'PATH':os.environ.get('SystemRoot',r'C:\Windows')+r'\System32','TEMP':str(cwd),'TMP':str(cwd)}
    for key in ['USERPROFILE','APPDATA','LOCALAPPDATA','HOMEDRIVE','HOMEPATH','USERNAME','USERDOMAIN']:
        if key in os.environ: clean_env[key]=os.environ[key]
    clean_env.update(env or {})
    envbuf=C.create_unicode_buffer('\0'.join(f'{k}={v}' for k,v in sorted(clean_env.items(),key=lambda kv:kv[0].upper()))+'\0\0')
    job=None; stdhandles=[]
    try:
        # Only these exact standard handles are inherited. No broker directory handles.
        sa=SECURITY_ATTRIBUTES(C.sizeof(SECURITY_ATTRIBUTES),None,True)
        def open_stream(path,write=False):
            if path:
                p=Path(path).resolve(); allowed=Path(cwd).resolve() if write else Path(cwd).resolve().parent
                if write:
                    # A host-private stdout archive is an intentional write-only
                    # inherited stream, never a general file/directory handle.
                    stage_root=Path(cwd).resolve().parent.parent
                    if (stage_root/'.sanzhong-appcontainer-stage').is_file() and p.is_relative_to(stage_root/'host'):
                        allowed=stage_root/'host'
                    if host_io_root is not None:
                        archive=Path(host_io_root).resolve()
                        if archive.name != 'host' or not (archive.parent/'.sanzhong-appcontainer-stage').is_file():
                            raise ValueError('Unmarked host archive for standard I/O')
                        if any(bool(q.lstat().st_file_attributes & 0x400) for q in [Path(host_io_root),*Path(host_io_root).parents]):
                            raise ValueError('Reparse point host archive is forbidden')
                        if p.parent == archive:
                            allowed=archive
                if not p.is_relative_to(allowed): raise ValueError('Standard I/O path outside staged role directory')
                if p.exists() and bool(p.stat().st_file_attributes & 0x400): raise ValueError('Reparse point stdio is forbidden')
            filename=str(p) if path else 'NUL'
            if path and len(filename) >= 248:
                filename='\\\\?\\'+filename
            h=K.CreateFileW(filename,0x40000000 if write else 0x80000000,3,C.byref(sa),2 if write and path else 3,0x80,None)
            check(h and h != P(-1).value,'CreateFile standard stream'); stdhandles.append(h); return h
        si.StartupInfo.dwFlags=0x100
        si.StartupInfo.hStdInput=open_stream(stdin_path)
        si.StartupInfo.hStdOutput=open_stream(stdout_path,True)
        si.StartupInfo.hStdError=open_stream(stderr_path,True)
        handles=(W.HANDLE*3)(*stdhandles)
        check(K.UpdateProcThreadAttribute(attr,0,0x20002,C.cast(handles,P),C.sizeof(handles),None,None),'Set explicit HANDLE_LIST')
        check(K.CreateProcessW(str(argv[0]),cmd,None,None,True,0x00080000|0x4|0x400|0x08000000,envbuf,str(cwd),C.byref(si),C.byref(pi)),'CreateProcessW AppContainer')
        info=token_info(pi.hProcess)
        if info['is_appcontainer'] != 1 or info['appcontainer_sid'] != sid_text(sid_ptr): raise RuntimeError('Child boundary token mismatch')
        job=K.CreateJobObjectW(None,None); check(job,'CreateJobObjectW')
        limits=EXTENDED_LIMIT(); limits.BasicLimitInformation.LimitFlags=0x2000
        check(K.SetInformationJobObject(job,9,C.byref(limits),C.sizeof(limits)),'Job kill-on-close')
        check(K.AssignProcessToJobObject(job,pi.hProcess),'AssignProcessToJobObject')
        check(K.ResumeThread(pi.hThread)!=0xffffffff,'ResumeThread')
        result={'pid':pi.dwProcessId,'token':info,'network_capability':'internetClient' if network else None,'argv':list(map(str,argv)),'cwd':str(cwd),'started_at':time.time(),'_handles':(pi.hProcess,pi.hThread,job)}
        pi.hProcess=None; pi.hThread=None; job=None
        if wait: return finish(result,timeout)
        return result
    finally:
        K.DeleteProcThreadAttributeList(attr)
        if net_sid: K.LocalFree(net_sid)
        for h in stdhandles: K.CloseHandle(h)
        if pi.hProcess: K.TerminateProcess(pi.hProcess,125); K.CloseHandle(pi.hProcess)
        if pi.hThread: K.CloseHandle(pi.hThread)
        if job: K.CloseHandle(job)

def finish(result, timeout=30):
    proc,thread,job=result.pop('_handles')
    try:
        state=K.WaitForSingleObject(proc,int(timeout*1000)); result['timed_out']=state==258
        if state==258: check(K.TerminateJobObject(job,124),'TerminateJobObject'); K.WaitForSingleObject(proc,5000)
        code=DWORD(); check(K.GetExitCodeProcess(proc,C.byref(code)),'GetExitCodeProcess')
        result['exit_code']=code.value; result['ended_at']=time.time(); return result
    finally:
        K.CloseHandle(job); K.CloseHandle(thread); K.CloseHandle(proc)
