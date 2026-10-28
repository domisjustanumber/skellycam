// devrestart.cpp -- ELEVATED helper: restart PnP devices the way `devcon restart` does (SetupAPI DIF_PROPERTYCHANGE /
// DICS_PROPCHANGE), optionally terminating named processes immediately before each restart (vendor helper apps
// such as LogiTuneAgent.exe hold handles and veto the query-remove, then respawn within ~1 s).
// Fallback per device: DICS_DISABLE + DICS_ENABLE.
// Build: cl /nologo /O2 /EHsc devrestart.cpp setupapi.lib cfgmgr32.lib
// Usage: devrestart.exe [--kill a.exe,b.exe] [--disable-enable] <instance-id> [...]
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <setupapi.h>
#include <cfgmgr32.h>
#include <tlhelp32.h>
#include <cstdio>
#include <string>
#include <vector>
#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "cfgmgr32.lib")

static int kill_by_names(const std::vector<std::wstring>& names) {
    int n = 0;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32W pe{sizeof(pe)};
    for (BOOL ok = Process32FirstW(snap, &pe); ok; ok = Process32NextW(snap, &pe))
        for (auto& nm : names)
            if (_wcsicmp(pe.szExeFile, nm.c_str()) == 0) {
                HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, pe.th32ProcessID);
                if (h) { if (TerminateProcess(h, 1)) { ++n; wprintf(L"  killed %s pid=%lu\n", pe.szExeFile, pe.th32ProcessID); } CloseHandle(h); }
            }
    CloseHandle(snap);
    return n;
}

static bool change(HDEVINFO di, SP_DEVINFO_DATA& dd, DWORD state, DWORD scope) {
    SP_PROPCHANGE_PARAMS p{};
    p.ClassInstallHeader.cbSize = sizeof(SP_CLASSINSTALL_HEADER);
    p.ClassInstallHeader.InstallFunction = DIF_PROPERTYCHANGE;
    p.StateChange = state; p.Scope = scope; p.HwProfile = 0;
    if (!SetupDiSetClassInstallParamsW(di, &dd, &p.ClassInstallHeader, sizeof(p))) return false;
    return SetupDiCallClassInstaller(DIF_PROPERTYCHANGE, di, &dd) != FALSE;
}

int wmain(int argc, wchar_t** argv) {
    std::vector<std::wstring> kills, ids; bool disen = false;
    for (int i = 1; i < argc; ++i) {
        std::wstring a = argv[i];
        if (a == L"--kill" && i + 1 < argc) { std::wstring v = argv[++i]; size_t p0 = 0; while (true) { size_t p = v.find(L',', p0); kills.push_back(v.substr(p0, p == std::wstring::npos ? p : p - p0)); if (p == std::wstring::npos) break; p0 = p + 1; } }
        else if (a == L"--disable-enable") disen = true;
        else ids.push_back(a);
    }
    int rc = 0;
    for (auto& id : ids) {
        HDEVINFO di = SetupDiCreateDeviceInfoList(nullptr, nullptr);
        SP_DEVINFO_DATA dd{sizeof(dd)};
        if (!SetupDiOpenDeviceInfoW(di, id.c_str(), nullptr, 0, &dd)) { wprintf(L"%s: open failed %lu\n", id.c_str(), GetLastError()); rc = 1; continue; }
        if (!kills.empty()) kill_by_names(kills);
        bool ok;
        if (!disen) ok = change(di, dd, DICS_PROPCHANGE, DICS_FLAG_CONFIGSPECIFIC);
        else { ok = change(di, dd, DICS_DISABLE, DICS_FLAG_CONFIGSPECIFIC); if (!kills.empty()) kill_by_names(kills); ok = change(di, dd, DICS_ENABLE, DICS_FLAG_CONFIGSPECIFIC) && ok; }
        DWORD err = ok ? 0 : GetLastError();
        SP_DEVINSTALL_PARAMS_W ip{sizeof(ip)}; SetupDiGetDeviceInstallParamsW(di, &dd, &ip);
        ULONG st = 0, prob = 0; CM_Get_DevNode_Status(&st, &prob, dd.DevInst, 0);
        bool need = (ip.Flags & (DI_NEEDREBOOT | DI_NEEDRESTART)) != 0;
        wprintf(L"%s: %s ok=%d err=%lu install_flags_need_reboot=%d devnode_status=0x%lX problem=%lu DN_NEED_RESTART=%d\n",
                id.c_str(), disen ? L"disable+enable" : L"propchange", ok, err, need, st, prob, (st & DN_NEED_RESTART) ? 1 : 0);
        if (!ok || need || (st & DN_NEED_RESTART)) rc = 2;
        SetupDiDestroyDeviceInfoList(di);
    }
    return rc;
}
