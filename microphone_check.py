"""User-started live microphone test. No audio or transcription is saved."""
from array import array
import json
from pathlib import Path
import queue
import threading
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk
import sounddevice as sd
from vosk import Model,KaldiRecognizer,SetLogLevel
from audio_devices import resolve_input,initialize_audio_thread
from audio_frontend import AudioFrontend
from core import Gate

ROOT=Path(__file__).resolve().parent


def main():
    window=tk.Tk()
    window.title('Проверка микрофона — Дима')
    window.geometry('700x360')
    window.minsize(600,340)
    window.attributes('-topmost',True)
    window.after(800,lambda:window.attributes('-topmost',False))
    panel=ttk.Frame(window,padding=20)
    panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='Проверьте, как Дима вас слышит',font=('Segoe UI',14,'bold')).pack(anchor='w')
    ttk.Label(panel,text='Нажмите «Начать проверку», затем несколько раз скажите:\n«Дима», «Димон», «Дмитрий» и «Дима, который час».',wraplength=650).pack(anchor='w',pady=10)
    level=ttk.Progressbar(panel,maximum=100)
    level.pack(fill='x',pady=6)
    state=tk.StringVar(value='Готов к проверке. Запись не сохраняется.')
    ttk.Label(panel,textvariable=state,wraplength=650).pack(anchor='w',pady=5)
    partial=tk.StringVar(value='Здесь появятся распознанные слова.')
    ttk.Label(panel,textvariable=partial,wraplength=650,font=('Segoe UI',12)).pack(anchor='w',pady=8)
    events=queue.Queue()
    stop=threading.Event()
    resumed=threading.Event()

    def resume():
        if '--resume' in sys.argv and not resumed.is_set():
            resumed.set()
            subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),str(ROOT/'jarvis.py')],
                             creationflags=subprocess.CREATE_NO_WINDOW)

    def start():
        start_button.config(state='disabled')
        state.set('Загружаю распознавание…')
        def worker():
            release=initialize_audio_thread()
            try:
                SetLogLevel(-1)
                cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
                device=resolve_input(cfg,sd)
                info=sd.query_devices(device,'input')
                rate=int(info['default_samplerate'])
                rec=KaldiRecognizer(Model(str(ROOT/cfg['model_path'])),rate)
                rec.SetWords(True)
                frontend=AudioFrontend(rate,cfg.get('microphone_gain',1.6),cfg.get('automatic_gain',True))
                gate=Gate(cfg['wake_phrases'])
                audio=queue.Queue(maxsize=100)
                recognized=0
                wakes=0
                def callback(data,frames,timing,status):
                    try:
                        audio.put_nowait(bytes(data))
                    except queue.Full:
                        pass
                with sd.RawInputStream(device=device,samplerate=rate,channels=1,dtype='int16',
                        blocksize=rate//50,latency='low',callback=callback):
                    events.put(('state','СЛУШАЮ 20 секунд. Говорите сейчас. Микрофон: '+info['name']))
                    print(json.dumps({'event':'listening'},ensure_ascii=True),flush=True)
                    deadline=time.monotonic()+20
                    while not stop.is_set() and time.monotonic()<deadline:
                        try:
                            block=audio.get(timeout=.2)
                        except queue.Empty:
                            continue
                        peak=max(abs(x) for x in array('h',block))
                        events.put(('level',min(100,peak/100)))
                        block,_=frontend.process(block)
                        if rec.AcceptWaveform(block):
                            result=json.loads(rec.Result())
                            text=result.get('text','')
                            if text:
                                recognized+=1
                                canonical=gate.canonicalize(text)
                                valid=any(canonical==w or canonical.startswith(w+' ') for w in gate.wakes)
                                wakes+=int(valid)
                                events.put(('text',text+(' — обращение узнано' if valid else '')))
                                print(json.dumps({'event':'speech','wake_detected':valid},ensure_ascii=True),flush=True)
                        else:
                            text=json.loads(rec.PartialResult()).get('partial','')
                            if text:
                                events.put(('text',text))
                events.put(('done',f'Проверка завершена. Фраз: {recognized}, обращений узнано: {wakes}.'))
                print(json.dumps({'event':'complete','recognized_phrases':recognized,'wake_count':wakes}),flush=True)
            except Exception as error:
                events.put(('done','Ошибка микрофона: '+str(error)))
                print(json.dumps({'event':'error','type':type(error).__name__,'message':str(error)}),flush=True)
            finally:
                release()
                resume()
        threading.Thread(target=worker,daemon=True).start()

    def poll():
        try:
            while True:
                kind,value=events.get_nowait()
                if kind=='level':
                    level['value']=value
                elif kind=='text':
                    partial.set(value)
                else:
                    state.set(value)
                    if kind=='done':
                        start_button.config(state='disabled' if '--resume' in sys.argv else 'normal')
        except queue.Empty:
            pass
        window.after(100,poll)

    def close():
        stop.set()
        resume()
        window.destroy()

    row=ttk.Frame(panel)
    row.pack(side='bottom',fill='x')
    start_button=ttk.Button(row,text='Начать проверку',command=start)
    start_button.pack(side='left')
    ttk.Button(row,text='Закрыть',command=close).pack(side='right')
    window.protocol('WM_DELETE_WINDOW',close)
    poll()
    window.mainloop()


if __name__=='__main__':
    main()
