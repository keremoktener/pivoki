using System.Diagnostics;
using System.Runtime.InteropServices;
using Pivoki.Core;

namespace Pivoki.Windows;

internal static class ForegroundPause
{
    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint window,out uint processId);
    [DllImport("user32.dll")] private static extern nint GetShellWindow();
    [DllImport("user32.dll")] private static extern nint GetDesktopWindow();
    private static uint cachedProcessId;
    private static string cachedName="";

    internal static bool Active(Preferences p)
    {
        if(!p.PauseInFullScreen && p.PausedApplications.Length==0)return false;
        var foreground=GetForegroundWindow();
        if(foreground==0 || foreground==GetShellWindow() || foreground==GetDesktopWindow())return false;
        GetWindowThreadProcessId(foreground,out var pid);
        if(pid==Environment.ProcessId)return false;
        if(p.PauseInFullScreen && DesktopGeometry.CoversMonitor(foreground))return true;
        if(p.PausedApplications.Length==0)return false;
        if(cachedProcessId!=pid)
        {
            cachedProcessId=pid;
            try{using var process=Process.GetProcessById((int)pid);cachedName=process.ProcessName;}
            catch(Exception error)when(error is ArgumentException or InvalidOperationException or System.ComponentModel.Win32Exception){cachedName="";}
        }
        return p.PausedApplications.Contains(cachedName,StringComparer.OrdinalIgnoreCase);
    }
}
