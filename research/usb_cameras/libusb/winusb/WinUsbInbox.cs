// WinUsbInbox.cs - SetupAPI helper used by install_winusb_c930e.ps1 / dryrun_winusb_driverlist.ps1.
// Goal: put Microsoft's INBOX, Microsoft-signed %WINDIR%\INF\winusb.inf "WinUsb Device" driver on
// one device instance (programmatic equivalent of Device Manager > Update driver > Browse > Let me
// pick > Universal Serial Bus devices > WinUsb Device). No custom INF, no catalog, no certificate.
//
// Two ways of building the candidate driver list are implemented (both READ-ONLY):
//  "per-device": open the device, set DI_ENUMSINGLEINF -> winusb.inf on the device element and
//                build its class/compat lists. Expected to be empty: winusb.inf is class USBDevice
//                while the camera is class USB/Image, and no hardware/compatible ID matches.
//  "inherit":    build a SET-level class driver list from winusb.inf on a class-less set, then open
//                the device with DIOD_INHERIT_CLASSDRVS (documented SetupDiOpenDeviceInfo flag) so
//                the element inherits it. Install() uses this list.
// Install() (admin only): SetupDiSetSelectedDriver + DiInstallDevice (newdev.dll).
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class WinUsbInbox
{
    const int DI_ENUMSINGLEINF = 0x00010000;
    const int DI_FLAGSEX_ALLOWEXCLUDEDDRVS = 0x00000800;
    const uint SPDIT_CLASSDRIVER = 1;
    const uint SPDIT_COMPATDRIVER = 2;
    const uint DIOD_INHERIT_CLASSDRVS = 0x00000002;

    [StructLayout(LayoutKind.Sequential)]
    public struct SP_DEVINFO_DATA { public uint cbSize; public Guid ClassGuid; public uint DevInst; public IntPtr Reserved; }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct SP_DEVINSTALL_PARAMS
    {
        public int cbSize; public int Flags; public int FlagsEx; public IntPtr hwndParent;
        public IntPtr InstallMsgHandler; public IntPtr InstallMsgHandlerContext; public IntPtr FileQueue;
        public IntPtr ClassInstallReserved; public int Reserved;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string DriverPath;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct SP_DRVINFO_DATA
    {
        public int cbSize; public uint DriverType; public IntPtr Reserved;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string Description;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string MfgName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string ProviderName;
        public long DriverDate; public ulong DriverVersion;
    }

    [DllImport("setupapi.dll", SetLastError = true)]
    static extern IntPtr SetupDiCreateDeviceInfoList(IntPtr classGuid, IntPtr hwnd);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "SetupDiOpenDeviceInfoW")]
    static extern bool SetupDiOpenDeviceInfo(IntPtr set, string instanceId, IntPtr hwnd, uint flags, ref SP_DEVINFO_DATA data);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "SetupDiGetDeviceInstallParamsW")]
    static extern bool GetParamsDev(IntPtr set, ref SP_DEVINFO_DATA data, ref SP_DEVINSTALL_PARAMS p);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "SetupDiSetDeviceInstallParamsW")]
    static extern bool SetParamsDev(IntPtr set, ref SP_DEVINFO_DATA data, ref SP_DEVINSTALL_PARAMS p);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "SetupDiGetDeviceInstallParamsW")]
    static extern bool GetParamsSet(IntPtr set, IntPtr nullData, ref SP_DEVINSTALL_PARAMS p);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "SetupDiSetDeviceInstallParamsW")]
    static extern bool SetParamsSet(IntPtr set, IntPtr nullData, ref SP_DEVINSTALL_PARAMS p);
    [DllImport("setupapi.dll", SetLastError = true, EntryPoint = "SetupDiBuildDriverInfoList")]
    static extern bool BuildDev(IntPtr set, ref SP_DEVINFO_DATA data, uint type);
    [DllImport("setupapi.dll", SetLastError = true, EntryPoint = "SetupDiBuildDriverInfoList")]
    static extern bool BuildSet(IntPtr set, IntPtr nullData, uint type);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "SetupDiEnumDriverInfoW")]
    static extern bool EnumDev(IntPtr set, ref SP_DEVINFO_DATA data, uint type, uint index, ref SP_DRVINFO_DATA drv);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "SetupDiEnumDriverInfoW")]
    static extern bool EnumSet(IntPtr set, IntPtr nullData, uint type, uint index, ref SP_DRVINFO_DATA drv);
    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Unicode, EntryPoint = "SetupDiSetSelectedDriverW")]
    static extern bool SetupDiSetSelectedDriver(IntPtr set, ref SP_DEVINFO_DATA data, ref SP_DRVINFO_DATA drv);
    [DllImport("setupapi.dll", SetLastError = true)]
    static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
    [DllImport("newdev.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool DiInstallDevice(IntPtr hwnd, IntPtr set, ref SP_DEVINFO_DATA data, ref SP_DRVINFO_DATA drv, uint flags, out bool reboot);

    static string InfPath() { return Environment.ExpandEnvironmentVariables(@"%WINDIR%\INF\winusb.inf"); }
    static Win32Exception W(string what) { return new Win32Exception(Marshal.GetLastWin32Error(), what); }
    static SP_DEVINSTALL_PARAMS NewParams() { var p = new SP_DEVINSTALL_PARAMS(); p.cbSize = Marshal.SizeOf(typeof(SP_DEVINSTALL_PARAMS)); return p; }
    static SP_DRVINFO_DATA NewDrv() { var d = new SP_DRVINFO_DATA(); d.cbSize = Marshal.SizeOf(typeof(SP_DRVINFO_DATA)); return d; }
    static SP_DEVINFO_DATA NewDev() { var d = new SP_DEVINFO_DATA(); d.cbSize = (uint)Marshal.SizeOf(typeof(SP_DEVINFO_DATA)); return d; }

    static IntPtr NewSet()
    {
        IntPtr set = SetupDiCreateDeviceInfoList(IntPtr.Zero, IntPtr.Zero);
        if (set == new IntPtr(-1)) throw W("SetupDiCreateDeviceInfoList");
        return set;
    }

    static IntPtr PreparePerDevice(string instanceId, uint type, out SP_DEVINFO_DATA data)
    {
        IntPtr set = NewSet();
        data = NewDev();
        if (!SetupDiOpenDeviceInfo(set, instanceId, IntPtr.Zero, 0, ref data)) throw W("SetupDiOpenDeviceInfo(" + instanceId + ")");
        var p = NewParams();
        if (!GetParamsDev(set, ref data, ref p)) throw W("SetupDiGetDeviceInstallParams");
        p.DriverPath = InfPath(); p.Flags |= DI_ENUMSINGLEINF; p.FlagsEx |= DI_FLAGSEX_ALLOWEXCLUDEDDRVS;
        if (!SetParamsDev(set, ref data, ref p)) throw W("SetupDiSetDeviceInstallParams");
        if (!BuildDev(set, ref data, type)) throw W("SetupDiBuildDriverInfoList");
        return set;
    }

    static IntPtr PrepareInherit(string instanceId, out SP_DEVINFO_DATA data)
    {
        IntPtr set = NewSet();
        var p = NewParams();
        if (!GetParamsSet(set, IntPtr.Zero, ref p)) throw W("SetupDiGetDeviceInstallParams(set)");
        p.DriverPath = InfPath(); p.Flags |= DI_ENUMSINGLEINF; p.FlagsEx |= DI_FLAGSEX_ALLOWEXCLUDEDDRVS;
        if (!SetParamsSet(set, IntPtr.Zero, ref p)) throw W("SetupDiSetDeviceInstallParams(set)");
        if (!BuildSet(set, IntPtr.Zero, SPDIT_CLASSDRIVER)) throw W("SetupDiBuildDriverInfoList(set)");
        data = NewDev();
        if (!SetupDiOpenDeviceInfo(set, instanceId, IntPtr.Zero, DIOD_INHERIT_CLASSDRVS, ref data))
            throw W("SetupDiOpenDeviceInfo(" + instanceId + ", DIOD_INHERIT_CLASSDRVS)");
        return set;
    }

    static List<SP_DRVINFO_DATA> EnumAll(IntPtr set, ref SP_DEVINFO_DATA data, uint type)
    {
        var l = new List<SP_DRVINFO_DATA>();
        for (uint i = 0; ; i++) { var d = NewDrv(); if (!EnumDev(set, ref data, type, i, ref d)) break; l.Add(d); }
        return l;
    }

    static string Fmt(string tag, SP_DRVINFO_DATA d) { return tag + "|" + d.Description + "|" + d.MfgName + "|" + d.ProviderName; }

    public static string[] ListSetDrivers()
    {
        var r = new List<string>();
        IntPtr set = IntPtr.Zero;
        try
        {
            set = NewSet();
            var p = NewParams();
            if (!GetParamsSet(set, IntPtr.Zero, ref p)) throw W("get set params");
            p.DriverPath = InfPath(); p.Flags |= DI_ENUMSINGLEINF; p.FlagsEx |= DI_FLAGSEX_ALLOWEXCLUDEDDRVS;
            if (!SetParamsSet(set, IntPtr.Zero, ref p)) throw W("set set params");
            if (!BuildSet(set, IntPtr.Zero, SPDIT_CLASSDRIVER)) throw W("build set list");
            for (uint i = 0; ; i++) { var d = NewDrv(); if (!EnumSet(set, IntPtr.Zero, SPDIT_CLASSDRIVER, i, ref d)) break; r.Add(Fmt("set/class", d)); }
            if (r.Count == 0) r.Add("set/class|(empty)");
        }
        catch (Win32Exception e) { r.Add("set/class|ERROR " + e.NativeErrorCode + ": " + e.Message); }
        finally { if (set != IntPtr.Zero) SetupDiDestroyDeviceInfoList(set); }
        return r.ToArray();
    }

    public static string[] ListDrivers(string instanceId)
    {
        var r = new List<string>();
        foreach (uint type in new uint[] { SPDIT_CLASSDRIVER, SPDIT_COMPATDRIVER })
        {
            string tag = "per-device/" + (type == SPDIT_CLASSDRIVER ? "class" : "compat");
            IntPtr set = IntPtr.Zero;
            try
            {
                SP_DEVINFO_DATA data;
                set = PreparePerDevice(instanceId, type, out data);
                var l = EnumAll(set, ref data, type);
                if (l.Count == 0) r.Add(tag + "|(empty)");
                foreach (var d in l) r.Add(Fmt(tag, d));
            }
            catch (Win32Exception e) { r.Add(tag + "|ERROR " + e.NativeErrorCode + ": " + e.Message); }
            finally { if (set != IntPtr.Zero) SetupDiDestroyDeviceInfoList(set); }
        }
        {
            IntPtr set = IntPtr.Zero;
            try
            {
                SP_DEVINFO_DATA data;
                set = PrepareInherit(instanceId, out data);
                var l = EnumAll(set, ref data, SPDIT_CLASSDRIVER);
                if (l.Count == 0) r.Add("inherit/class|(empty)");
                foreach (var d in l) r.Add(Fmt("inherit/class", d));
            }
            catch (Win32Exception e) { r.Add("inherit/class|ERROR " + e.NativeErrorCode + ": " + e.Message); }
            finally { if (set != IntPtr.Zero) SetupDiDestroyDeviceInfoList(set); }
        }
        return r.ToArray();
    }

    // Installs "WinUsb Device" from the inbox winusb.inf on instanceId. Requires elevation.
    public static string Install(string instanceId, out bool reboot)
    {
        SP_DEVINFO_DATA data;
        IntPtr set = PrepareInherit(instanceId, out data);
        try
        {
            foreach (var d in EnumAll(set, ref data, SPDIT_CLASSDRIVER))
            {
                if (d.Description.IndexOf("WinUsb Device", StringComparison.OrdinalIgnoreCase) < 0) continue;
                var drv = d;
                if (!SetupDiSetSelectedDriver(set, ref data, ref drv)) throw W("SetupDiSetSelectedDriver");
                if (!DiInstallDevice(IntPtr.Zero, set, ref data, ref drv, 0, out reboot)) throw W("DiInstallDevice");
                return "installed: " + d.Description + " / " + d.ProviderName;
            }
            throw new InvalidOperationException("'WinUsb Device' not in the inherited winusb.inf class driver list for " + instanceId);
        }
        finally { SetupDiDestroyDeviceInfoList(set); }
    }
}
