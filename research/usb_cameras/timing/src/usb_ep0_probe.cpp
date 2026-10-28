// usb_ep0_probe.cpp -- does the device answer *standard* control requests on EP0? (independent of usbvideo.sys,
// Media Foundation, Frame Server and UVC metadata). For a USB device instance ID it finds the parent hub and the port
// (DEVPKEY_Device_Address) and sends IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION for: the device descriptor,
// string descriptor 0 (LANGID list) and the iProduct string. The hub driver issues these as real GET_DESCRIPTOR
// control transfers to the device.
// Build: timing\build_kiyo_probe.bat -> timing\build\usb_ep0_probe.exe
// Usage: usb_ep0_probe.exe "<USB\VID_xxxx&PID_xxxx\instance>" [...]
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winioctl.h>
#include <initguid.h>
#include <usbioctl.h>
#include <usbiodef.h>
#include <setupapi.h>
#include <cfgmgr32.h>
#include <devpkey.h>
#include <cstdio>
#include <string>
#include <vector>
#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "cfgmgr32.lib")
static std::string w2u(const wchar_t* w) { if (!w) return {}; int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr); std::string s(n > 0 ? n - 1 : 0, '\0'); if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, s.data(), n, nullptr, nullptr); return s; }
static std::string jesc(const std::string& s) { std::string o; for (char c : s) { if (c == '"' || c == '\\') { o += '\\'; o += c; } else o += c; } return o; }

static std::string get_desc(HANDLE hub, ULONG port, UCHAR type, UCHAR index, USHORT lang, const char* name, UCHAR* first_bytes_out = nullptr) {
    std::vector<BYTE> buf(sizeof(USB_DESCRIPTOR_REQUEST) + 255, 0);
    auto* r = (USB_DESCRIPTOR_REQUEST*)buf.data();
    r->ConnectionIndex = port; r->SetupPacket.bmRequest = 0x80; r->SetupPacket.bRequest = USB_REQUEST_GET_DESCRIPTOR;
    r->SetupPacket.wValue = (USHORT)((type << 8) | index); r->SetupPacket.wIndex = lang; r->SetupPacket.wLength = 255;
    DWORD ret = 0; LARGE_INTEGER f, t0, t1; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&t0);
    BOOL ok = DeviceIoControl(hub, IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION, buf.data(), (DWORD)buf.size(), buf.data(), (DWORD)buf.size(), &ret, nullptr);
    DWORD err = ok ? 0 : GetLastError(); QueryPerformanceCounter(&t1);
    int dlen = ok && ret > sizeof(USB_DESCRIPTOR_REQUEST) ? (int)(ret - sizeof(USB_DESCRIPTOR_REQUEST)) : 0;
    BYTE* d = buf.data() + sizeof(USB_DESCRIPTOR_REQUEST);
    if (first_bytes_out && dlen >= 16) memcpy(first_bytes_out, d, 18);
    std::string hexs; for (int i = 0; i < dlen && i < 40; ++i) { char b[4]; sprintf_s(b, "%02x", d[i]); hexs += b; }
    std::string txt; if (type == 3 && index && dlen > 2) { std::wstring w((wchar_t*)(d + 2), (dlen - 2) / 2); txt = w2u(w.c_str()); }
    char b[512]; sprintf_s(b, "\"%s\":{\"ok\":%s,\"win32_error\":%lu,\"ms\":%.2f,\"len\":%d,\"hex\":\"%s\",\"text\":\"%s\"}", name, ok ? "true" : "false", err,
                           (t1.QuadPart - t0.QuadPart) * 1e3 / f.QuadPart, dlen, hexs.c_str(), jesc(txt).c_str());
    return b;
}

int main(int argc, char** argv) {
    for (int a = 1; a < argc; ++a) {
        std::wstring id(argv[a], argv[a] + strlen(argv[a]));
        std::string js = "{\"tool\":\"usb_ep0_probe\",\"instance\":\"" + jesc(argv[a]) + "\"";
        DEVINST di = 0, parent = 0;
        if (CM_Locate_DevNodeW(&di, (DEVINSTID_W)id.c_str(), CM_LOCATE_DEVNODE_NORMAL) != CR_SUCCESS || CM_Get_Parent(&parent, di, 0) != CR_SUCCESS) { printf("%s,\"error\":\"devnode\"}\n", js.c_str()); continue; }
        DEVPROPTYPE pt; ULONG port = 0, sz = sizeof(port);
        CM_Get_DevNode_PropertyW(di, &DEVPKEY_Device_Address, &pt, (PBYTE)&port, &sz, 0);
        WCHAR pid[512]; CM_Get_Device_IDW(parent, pid, 512, 0);
        ULONG len = 0; CM_Get_Device_Interface_List_SizeW(&len, (LPGUID)&GUID_DEVINTERFACE_USB_HUB, pid, CM_GET_DEVICE_INTERFACE_LIST_PRESENT);
        std::vector<WCHAR> list(len + 1, 0); CM_Get_Device_Interface_ListW((LPGUID)&GUID_DEVINTERFACE_USB_HUB, pid, list.data(), len, CM_GET_DEVICE_INTERFACE_LIST_PRESENT);
        js += ",\"parent_hub\":\"" + jesc(w2u(pid)) + "\",\"port\":" + std::to_string(port);
        HANDLE hub = CreateFileW(list.data(), GENERIC_WRITE, FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, 0, nullptr);
        if (hub == INVALID_HANDLE_VALUE) { printf("%s,\"hub_open_error\":%lu}\n", js.c_str(), GetLastError()); continue; }
        UCHAR dd[18] = {0};
        js += "," + get_desc(hub, port, 1, 0, 0, "device_descriptor", dd);
        js += "," + get_desc(hub, port, 3, 0, 0, "string0_langids");
        UCHAR iprod = dd[15]; USHORT lang = 0x0409;
        js += "," + get_desc(hub, port, 3, iprod ? iprod : 2, lang, "string_iProduct");
        CloseHandle(hub);
        printf("%s}\n", js.c_str());
    }
    return 0;
}
