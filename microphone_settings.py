"""User-facing microphone picker. No recordings or Windows settings changes."""
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import sounddevice as sd

from audio_devices import selectable_inputs, resolve_input, save_selection,initialize_audio_thread

ROOT = Path(__file__).resolve().parent


def main():
    window = tk.Tk()
    window.title('Микрофон Джарвиса')
    window.geometry('680x265')
    window.minsize(560, 265)
    window.attributes('-topmost', True)
    window.after(600, lambda: window.attributes('-topmost', False))
    panel = ttk.Frame(window, padding=20)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='Выберите микрофон', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
    ttk.Label(panel, text='Выбор сохранится и применится без перезапуска Джарвиса.').pack(anchor='w', pady=(5, 12))
    selected = tk.StringVar()
    combo = ttk.Combobox(panel, textvariable=selected, state='readonly')
    combo.pack(fill='x')
    status = tk.StringVar(value='«По умолчанию» — микрофон, выбранный в Windows.')
    ttk.Label(panel, textvariable=status, wraplength=620).pack(anchor='w', pady=12)
    results = queue.Queue()
    choices = []

    def refresh():
        try:
            # Refresh PortAudio's hardware inventory, local to this picker process.
            sd._terminate()
            sd._initialize()
            devices = selectable_inputs(sd)
            preference = {'Windows WASAPI': 0, 'MME': 1, 'Windows DirectSound': 2, 'Windows WDM-KS': 3}
            devices.sort(key=lambda d: (preference.get(d['hostapi'], 4), d['name'].casefold()))
            choices[:] = [None] + devices
            combo['values'] = ['По умолчанию в Windows'] + [d['name'] for d in devices]
            cfg = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
            try:
                current = resolve_input(cfg, sd)
            except ValueError:
                current = -1
            index = (0 if cfg.get('input_device') is None and not cfg.get('input_device_name') else
                     next((i for i, d in enumerate(choices) if d and d['index'] == current), 0))
            combo.current(index)
            status.set('Выберите устройство и нажмите «Применить».' if current != -1 else
                       'Сохранённый микрофон не найден. Выберите доступное устройство.')
        except Exception as error:
            status.set('Не удалось получить список микрофонов: ' + str(error))

    def apply():
        index = combo.current()
        if index < 0 or index >= len(choices):
            return
        device = choices[index]
        apply_button.config(state='disabled')
        refresh_button.config(state='disabled')
        combo.config(state='disabled')
        status.set('Проверяю доступ к микрофону…')

        def validate():
            release=initialize_audio_thread()
            try:
                if device:
                    resolve_input({'input_device_name':device['name'], 'input_hostapi':device['hostapi']}, sd)
                target = device['index'] if device else None
                info = sd.query_devices(target, 'input')
                rate = int(info['default_samplerate'])
                sd.check_input_settings(device=target, channels=1, dtype='int16', samplerate=rate)
                # Open briefly to catch Windows permission/driver failures before saving.
                # Incoming bytes are discarded immediately, never stored or transmitted.
                with sd.RawInputStream(device=target, samplerate=rate, channels=1, dtype='int16',
                                       callback=lambda *_: None):
                    time.sleep(.3)
                save_selection(ROOT/'config.json', device)
                results.put(None)
            except Exception as error:
                results.put(str(error))
            finally:
                release()

        threading.Thread(target=validate, daemon=True).start()

    def poll():
        try:
            error = results.get_nowait()
        except queue.Empty:
            pass
        else:
            apply_button.config(state='normal')
            refresh_button.config(state='normal')
            combo.config(state='readonly')
            if error:
                status.set('Выбор не изменён: устройство недоступно.')
                messagebox.showerror('Микрофон недоступен', error, parent=window)
            else:
                status.set('Сохранено. Джарвис переключится на выбранный микрофон.')
        window.after(100, poll)

    buttons = ttk.Frame(panel)
    buttons.pack(fill='x', side='bottom')
    refresh_button = ttk.Button(buttons, text='Обновить список', command=refresh)
    refresh_button.pack(side='left')
    ttk.Button(buttons, text='Закрыть', command=window.destroy).pack(side='right')
    apply_button = ttk.Button(buttons, text='Применить', command=apply)
    apply_button.pack(side='right', padx=8)
    refresh()
    poll()
    window.mainloop()


if __name__ == '__main__':
    main()
