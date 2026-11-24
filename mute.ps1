$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class JarvisAudio {
 [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class Enumerator {}
 [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IEnum {
  int EnumAudioEndpoints(int flow, uint mask, out IntPtr devices);
  [PreserveSig] int GetDefaultAudioEndpoint(int flow, int role, out IDevice device);
 }
 [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IDevice {
  [PreserveSig] int Activate(ref Guid iid, uint context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object obj);
 }
 [ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IVolume {
  int RegisterControlChangeNotify(IntPtr p);
  int UnregisterControlChangeNotify(IntPtr p);
  int GetChannelCount(out uint count);
  int SetMasterVolumeLevel(float level, Guid context);
  int SetMasterVolumeLevelScalar(float level, Guid context);
  int GetMasterVolumeLevel(out float level);
  int GetMasterVolumeLevelScalar(out float level);
  int SetChannelVolumeLevel(uint channel, float level, Guid context);
  int SetChannelVolumeLevelScalar(uint channel, float level, Guid context);
  int GetChannelVolumeLevel(uint channel, out float level);
  int GetChannelVolumeLevelScalar(uint channel, out float level);
  [PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)] bool muted, Guid context);
  [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)] out bool muted);
 }
 public static bool Access(bool? muted) {
  IEnum enumerator = (IEnum)new Enumerator();
  IDevice device = null;
  object obj = null;
  try {
   Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(0, 1, out device));
   Guid iid = typeof(IVolume).GUID;
   Marshal.ThrowExceptionForHR(device.Activate(ref iid, 23, IntPtr.Zero, out obj));
   IVolume volume = (IVolume)obj;
   if (muted.HasValue) Marshal.ThrowExceptionForHR(volume.SetMute(muted.Value, Guid.Empty));
   bool current;
   Marshal.ThrowExceptionForHR(volume.GetMute(out current));
   return current;
  } finally {
   if (obj != null) Marshal.ReleaseComObject(obj);
   if (device != null) Marshal.ReleaseComObject(device);
   Marshal.ReleaseComObject(enumerator);
  }
 }
}
'@
if ($env:JARVIS_MUTED -eq 'probe') { [JarvisAudio]::Access($null) }
else { [void][JarvisAudio]::Access($env:JARVIS_MUTED -eq '1') }
