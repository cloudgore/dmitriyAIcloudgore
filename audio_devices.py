"""Microphone identities that remain valid when device indexes change."""
import json
import ctypes
import os
from pathlib import Path


def initialize_audio_thread():
    # WASAPI's COM objects require initialization on the actual capture thread,
    # not just on the UI thread that first imported sounddevice.
    if os.name!='nt':
        return lambda:None
    ole=ctypes.OleDLL('ole32')
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,ctypes.c_uint]
    ole.CoInitializeEx.restype=ctypes.c_long
    result=ole.CoInitializeEx(None,0)
    if result in (0,1):
        return ole.CoUninitialize
    return lambda:None


def input_devices(sd):
    hosts = sd.query_hostapis()
    devices = []
    for index, device in enumerate(sd.query_devices()):
        if device['max_input_channels'] > 0:
            devices.append({'index': index, 'name': device['name'],
                            'hostapi': hosts[device['hostapi']]['name'],
                            'rate': int(device['default_samplerate'])})
    return devices


def device_signature(cfg):
    return (cfg.get('input_device'), cfg.get('input_device_name'), cfg.get('input_hostapi'))


def selectable_inputs(sd):
    devices=input_devices(sd)
    preferred=[d for d in devices if d['hostapi']=='Windows WASAPI']
    return preferred or [d for d in devices if d['hostapi']=='MME']


def resolve_input(cfg, sd):
    name = cfg.get('input_device_name')
    if name:
        matches = [d for d in input_devices(sd) if d['name'] == name and d['hostapi'] == cfg.get('input_hostapi')]
        if len(matches) != 1:
            raise ValueError('Выбранный микрофон недоступен. Выберите другой через значок Джарвиса.')
        return matches[0]['index']
    device=cfg.get('input_device')
    if device is None:
        # Follow the same Windows default physical device, using shared-mode
        # WASAPI where available rather than the higher-latency legacy mapper.
        current=sd.query_devices(None,'input')
        matches=[d for d in input_devices(sd) if d['hostapi']=='Windows WASAPI' and
                 (d['name']==current['name'] or d['name'].startswith(current['name']))]
        if len(matches)==1:
            return matches[0]['index']
    return device


def save_selection(path, device):
    path = Path(path)
    cfg = json.loads(path.read_text(encoding='utf-8'))
    cfg['input_device'] = device['index'] if device else None
    if device:
        cfg['input_device_name'] = device['name']
        cfg['input_hostapi'] = device['hostapi']
    else:
        cfg.pop('input_device_name', None)
        cfg.pop('input_hostapi', None)
    pending = path.with_suffix('.json.tmp')
    pending.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)
