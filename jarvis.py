"""Offline Russian Windows assistant. Run without args for a tray icon."""
import argparse
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import wave
import winsound

from core import Gate, COMMANDS, normalize,prepare_question
from audio_devices import resolve_input, device_signature
from audio_frontend import AudioFrontend, early_endpoint

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("jarvis")
POWERSHELL = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
MEDIA_KEYS = {"volume_up": 0xAF, "volume_down": 0xAE, "play_pause": 0xB3,
              "next": 0xB0, "previous": 0xB1}


def config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def speak(text, wave_path=None, cache=True):
    cfg = config()
    if not wave_path and cfg.get("speech_provider") == "silero":
        from silero_voice import speak_local
        speak_local(text)
        return
    if not wave_path and cfg.get("speech_provider") == "edge":
        try:
            clock=re.fullmatch(r'Сейчас (\d{2}):(\d{2})',text)
            if clock:
                from clock_voice import say_clock
                say_clock(int(clock[1]),int(clock[2]),cfg)
                return
            from voice import say_neural
            say_neural(text, cfg, cache=cache)
            return
        except Exception as error:
            LOG.warning("Neural voice unavailable: %s", type(error).__name__)
            if not cfg.get("speech_fallback", True):
                from voice import cached_notice
                if cached_notice(cfg):
                    return
                raise
    # Text is passed as DATA via environment, never interpolated into code.
    env = os.environ.copy()
    env["JARVIS_SPEECH"] = text
    args = [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-File", str(ROOT / "speak.ps1")]
    if wave_path:
        args += ["-WavePath", str(Path(wave_path).resolve())]
    subprocess.run(args, env=env, check=True, timeout=25,
                   creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)


def press_key(code, count=1):
    for _ in range(count):
        ctypes.windll.user32.keybd_event(code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(code, 0, 2, 0)
        time.sleep(.05)


def set_mute(muted):
    # Use Core Audio to set a known state instead of toggling a media key.
    env = os.environ.copy()
    env["JARVIS_MUTED"] = "1" if muted else "0"
    subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-File", str(ROOT / "mute.ps1")],
                   env=env, check=True, timeout=25, capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)


def execute(action, cfg):
    if action == "music":
        # URL is fixed and validated; recognized speech never becomes a URL/path.
        if cfg["music_url"] != "https://music.yandex.ru/":
            raise ValueError("Разрешён только адрес https://music.yandex.ru/")
        if cfg.get("music_autoplay", False):
            os.startfile(cfg["music_url"] + "?jarvis_play=1&jarvis_request=" + str(time.time_ns()))
            return "Включаю музыку"
        os.startfile(cfg["music_url"])
        return "Открываю Яндекс Музыку. Если нужно, нажмите играть в браузере."
    if action in ('play','pause','next','previous','play_pause'):
        from music_control import control
        if not control(action,cfg):
            return 'Не удалось управлять музыкой. Открой Яндекс Музыку и проверь расширение.'
        return {'play':'Продолжаю музыку','pause':'Музыка на паузе','next':'Переключаю на следующий трек',
                'previous':'Переключаю на предыдущий трек','play_pause':'Готово'}[action]
    if action in MEDIA_KEYS:
        press_key(MEDIA_KEYS[action], min(5, max(1, int(cfg["volume_key_presses"]))) if action.startswith("volume") else 1)
        return {"volume_up": "Громче", "volume_down": "Тише", "play_pause": "Плей пауза",
                "next": "Следующий трек", "previous": "Предыдущий трек"}[action]
    if action in ("mute", "unmute"):
        set_mute(action == "mute")
        return "Звук выключен" if action == "mute" else "Звук включён"
    if action in ("notepad", "calculator"):
        name = {"notepad": "notepad.exe", "calculator": "calc.exe"}[action]
        subprocess.Popen([str(Path(os.environ["SystemRoot"]) / "System32" / name)])
        return "Открываю"
    if action == "browser":
        os.startfile("https://ya.ru/")
        return "Открываю браузер"
    if action == "time":
        return "Сейчас " + time.strftime("%H:%M")
    if action == "help":
        return "Я открываю музыку и приложения, меняю громкость, отвечаю на вопросы. Для поиска скажите: найди в интернете, и ваш запрос."
    if action == "cancel":
        return "Отменено"
    if action == "quit":
        return "Выключаю помощника"
    raise ValueError("Команда отсутствует в белом списке")


class Assistant:
    def __init__(self, cfg):
        self.cfg = cfg
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.speaking = threading.Event()
        self.busy = threading.Event()
        self.audio = queue.Queue(maxsize=40)
        self.gate = Gate(cfg["wake_phrases"], cfg["command_timeout"])
        self.icon = None
        self.brain = None
        self.reset_audio = threading.Event()

    def reply(self, text, cache=True):
        self.speaking.set()
        try:
            speak(text, cache=cache)
        except Exception:
            LOG.exception("Ошибка голоса Windows")
        finally:
            time.sleep(.12)
            self.flush()
            self.speaking.clear()

    def flush(self):
        while True:
            try:
                self.audio.get_nowait()
            except queue.Empty:
                break

    def callback(self, data, frames, timing, status):
        if status:
            LOG.warning("Audio: %s", status)
            if getattr(status,'input_overflow',False):
                self.reset_audio.set()
        if self.stop.is_set() or self.paused.is_set() or self.speaking.is_set() or self.busy.is_set():
            return
        try:
            self.audio.put_nowait(bytes(data))
        except queue.Full:
            # Never process a backlog of stale commands.
            self.flush()
            self.reset_audio.set()

    def acknowledge_wake(self):
        if self.cfg.get('wake_ack','tone')=='voice':
            self.reply('Слушаю')
            return
        # Use the ordinary audio output, not the easily missed system Beep.
        self.speaking.set()
        try:
            from feedback import listening_tone
            winsound.PlaySound(listening_tone(),winsound.SND_MEMORY | winsound.SND_SYNC)
        except RuntimeError as error:
            LOG.warning('Activation sound unavailable: %s',error)
        finally:
            self.flush()
            self.speaking.clear()

    def handle(self, result):
        text = self.gate.canonicalize(result.get("text", ""))
        words = result.get("result", [])
        # Vosk also emits finalized EMPTY segments during silence. They are not
        # failed user commands and must never consume the wake window or speak.
        if not text or not words:
            return
        wake = next((w for w in self.gate.wakes if text == w or text.startswith(w + " ")), None)
        wake_count = len(wake.split()) if wake else 0
        wake_threshold=(self.cfg.get('name_confidence',.5) if wake in ('дима','димон','дмитрий') else
                        self.cfg['min_word_confidence'])
        if wake and (len(words) < wake_count or
                     any(w.get("conf", 0) < wake_threshold for w in words[:wake_count])):
            LOG.info('Обращение отклонено: низкая уверенность имени')
            return
        if wake:
            self.acknowledge_wake()
            self.gate.until=time.monotonic()+self.cfg['command_timeout']
            LOG.info('Активация подтверждена')
        command_words = words[wake_count:]
        if command_words:
            # An exact allowlisted phrase can survive one weakly scored word.
            # Wake verification stays strict; no fuzzy intent or shell matching.
            confidence = sum(w.get("conf", 0) for w in command_words) / len(command_words)
            if confidence < self.cfg.get("command_confidence", .60):
                if time.monotonic() < self.gate.until:
                    LOG.info("Фраза пропущена: низкая средняя уверенность; ожидание продолжается")
                return
        decision = self.gate.feed(text)
        if decision.kind == "wake":
            # Start the response window AFTER the spoken acknowledgment.
            self.gate.until = time.monotonic() + self.cfg["command_timeout"]
        elif decision.kind == "unknown":
            if self.cfg.get('brain_enabled', False) and 'unk' not in text.split():
                question = prepare_question(text[len(wake):].strip() if wake else text)
                if len(question.split()) >= 2 or question in ('привет','здравствуй','здравствуйте','погода'):
                    self.gate.reset()
                    self.answer_question(question)
            else:
                LOG.info("Фраза пропущена: отсутствует в белом списке; ожидание продолжается")
        elif decision.kind == "command":
            LOG.info("Разрешённая команда: %s", decision.action)
            try:
                text = execute(decision.action, self.cfg)
                self.reply(text)
                if decision.action == "quit":
                    self.stop.set()
            except Exception:
                LOG.exception("Не удалось выполнить команду")
                self.reply("Не удалось выполнить команду. Проверьте журнал.")

    def show_answer(self, question, answer, sources):
        payload = json.dumps({'question':question, 'answer':answer, 'sources':sources}, ensure_ascii=False).encode('utf-8')
        process = subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),
            str(ROOT/'response_window.py')], stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        process.stdin.write(payload)
        process.stdin.close()

    def compute_answer(self,question,query):
        from weather_service import parse_weather,get_weather
        weather=parse_weather(question)
        if weather is not None:
            return get_weather(weather)
        from local_brain import Brain
        from web_search import search,fallback_link
        if self.brain is None:
            self.brain=Brain()
        if not query:
            brain_question = question.strip()

    # Короткие запросы без глагола считаем просьбой дать справку.
            if 1 <= len(brain_question.split()) <= 3:
                    brain_question = (
            f"Кратко расскажи об этом: {brain_question}. "
            "Объясни, что это такое, простыми словами. "
            "Не говори, что ищешь информацию."
        )

            return self.brain.answer(brain_question), []
        try:
            sources=search(query)
        except Exception as error:
            LOG.warning('DuckDuckGo unavailable: %s',type(error).__name__)
            sources=[]
        if not sources:
            return ('Не удалось получить результаты DuckDuckGo. Откройте ссылку поиска в окне ответа.',
                    [{'title':'Поиск DuckDuckGo','url':fallback_link(query),'body':''}])
        try:
            return self.brain.answer(query,sources),sources
        except Exception as error:
            LOG.warning('Search summary unavailable: %s',type(error).__name__)
            return 'Нашёл источники, но локальная модель не смогла составить ответ. Ссылки доступны в окне.',sources

    def answer_question(self, question):
        from web_search import search_query
        self.busy.set()
        sources = []
        try:
            started=time.monotonic()
            query = search_query(question)
            from weather_service import parse_weather
            weather_request=parse_weather(question) is not None
            if self.icon:
                self.icon.title = 'Джарвис - ищу' if query or weather_request else 'Джарвис - думаю'
            completed=queue.Queue(maxsize=1)
            def generate():
                try:
                    completed.put((True,self.compute_answer(question,query)))
                except Exception as error:
                    completed.put((False,error))
            threading.Thread(target=generate,daemon=True).start()
            # This clip is cached and plays while inference/search is already
            # running, so the user gets immediate feedback without extra wait.
            self.reply('Ищу в интернете' if query or weather_request else 'Думаю')
            success,result=completed.get(timeout=130)
            if not success:
                raise result
            answer,sources=result
            LOG.info('Подготовка ответа: %.2f сек.',time.monotonic()-started)
            if self.stop.is_set():
                return
            try:
                self.show_answer(question, answer, sources)
            except Exception:
                LOG.exception('Не удалось показать окно ответа')
            # The full answer remains in the ephemeral window. Keep voice responses short.
            spoken = answer if len(answer) <= 420 else answer[:400].rsplit(' ',1)[0]+'. Подробности в окне ответа.'
            speech_started=time.monotonic()
            self.reply(spoken, cache=True)
            LOG.info('Озвучивание ответа: %.2f сек.',time.monotonic()-speech_started)
            LOG.info('Ответ завершён: %s', 'DuckDuckGo и Qwen3' if query else 'Qwen3')
        except Exception as error:
            LOG.warning('Local answer unavailable: %s', type(error).__name__)
            if not self.stop.is_set():
                self.reply('Не удалось получить ответ локальной модели. Проверьте, загружена ли Qwen.')
        finally:
            self.flush()
            self.busy.clear()
            if self.icon:
                self.icon.title = 'Джарвис — пауза' if self.paused.is_set() else 'Джарвис — слушает'

    def run(self, seconds=None):
        import sounddevice as sd
        from vosk import Model, KaldiRecognizer, SetLogLevel
        try:
            from music_control import start
            start(self.cfg)
        except Exception as error:
            LOG.warning('Music bridge unavailable: %s',type(error).__name__)
        SetLogLevel(-1)
        model = Model(str(ROOT / self.cfg["model_path"]))
        if self.cfg.get('brain_enabled',False):
            def warm_model():
                try:
                    from local_brain import warm_up
                    warm_up()
                    LOG.info('Qwen3 прогрета')
                except Exception as error:
                    LOG.warning('Qwen warmup unavailable: %s',type(error).__name__)
            threading.Thread(target=warm_model,daemon=True).start()
        deadline = time.monotonic() + seconds if seconds else float("inf")
        last_error = None
        while not self.stop.is_set() and time.monotonic() < deadline:
            self.cfg = config()
            self.gate.reset()
            self.flush()
            try:
                self.listen(sd, model, deadline)
                last_error = None
            except (sd.PortAudioError, ValueError) as error:
                if str(error) != last_error:
                    LOG.warning("Микрофон недоступен: %s", error)
                    last_error = str(error)
                if self.icon:
                    self.icon.title = "Джарвис — выберите микрофон"
                self.stop.wait(1)
            # No stream is open here; refresh the inventory after a selection/hotplug.
            sd._terminate()
            sd._initialize()

    def listen(self, sd, model, deadline):
        from vosk import KaldiRecognizer
        signature = device_signature(self.cfg)
        device = resolve_input(self.cfg, sd)
        info = sd.query_devices(device, "input")
        rate = int(info["default_samplerate"])
        recognizer = KaldiRecognizer(model, rate)
        recognizer.SetWords(True)
        # After a verified wake word, focus recognition on the allowlisted commands.
        # Keep [unk] so unrelated speech has an explicit rejection route.
        grammar = list(COMMANDS) + self.cfg["wake_phrases"] + [
            wake + " " + command for wake in self.cfg["wake_phrases"] for command in COMMANDS]
        command_recognizer = KaldiRecognizer(model, rate, json.dumps(grammar + ["[unk]"], ensure_ascii=False))
        command_recognizer.SetWords(True)
        active_recognizer = recognizer
        frontend=AudioFrontend(rate,self.cfg.get('microphone_gain',1.6),self.cfg.get('automatic_gain',True))
        LOG.info("Запуск, микрофон: %s; device=%s", info["name"], device)
        with sd.RawInputStream(samplerate=rate, blocksize=max(160, rate // 50), latency='low',
                               device=device, channels=1, dtype="int16", callback=self.callback):
            if self.icon:
                self.icon.title = "Джарвис — пауза" if self.paused.is_set() else "Джарвис — слушает"
            while not self.stop.is_set() and time.monotonic() < deadline:
                if device_signature(config()) != signature:
                    break
                if self.paused.is_set():
                    self.gate.reset()
                    recognizer.Reset()
                    command_recognizer.Reset()
                    frontend.reset_segment()
                    self.flush()
                    self.stop.wait(.1)
                    continue
                try:
                    block = self.audio.get(timeout=.2)
                except queue.Empty:
                    continue
                if self.reset_audio.is_set():
                    recognizer.Reset()
                    command_recognizer.Reset()
                    frontend.reset_segment()
                    self.gate.reset()
                    self.reset_audio.clear()
                target = command_recognizer if (not self.cfg.get('brain_enabled',False) and
                    time.monotonic() < self.gate.until) else recognizer
                if target is not active_recognizer:
                    target.Reset()
                    active_recognizer = target
                block,silence=frontend.process(block)
                if active_recognizer.AcceptWaveform(block):
                    self.handle(json.loads(active_recognizer.Result()))
                    active_recognizer.Reset()
                    frontend.reset_segment()
                else:
                    partial=json.loads(active_recognizer.PartialResult()).get('partial','')
                    if self.cfg.get('fast_endpoint',False) and frontend.has_speech and early_endpoint(partial,self.gate.recognition_wakes,silence,self.cfg.get('endpoint_silence',.45)):
                        self.handle(json.loads(active_recognizer.FinalResult()))
                        active_recognizer.Reset()
                        frontend.reset_segment()
        LOG.info("Микрофон закрыт")

    def tray(self, seconds=None):
        import pystray
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (64, 64), "#142536")
        draw = ImageDraw.Draw(image)
        draw.ellipse((14, 14, 50, 50), fill="#34d5dc")
        draw.ellipse((24, 24, 40, 40), fill="#142536")

        def pause(icon, item):
            if self.paused.is_set():
                self.paused.clear()
            else:
                self.paused.set()
            icon.title = "Джарвис — пауза" if self.paused.is_set() else "Джарвис — слушает"

        def quit_app(icon, item):
            self.stop.set()
            icon.stop()

        def microphone_settings(icon, item):
            subprocess.Popen([str(Path(sys.executable).with_name("pythonw.exe")),
                              str(ROOT / "microphone_settings.py")],
                             creationflags=subprocess.CREATE_NO_WINDOW)


        self.icon = pystray.Icon("Jarvis", image, "Джарвис — загрузка",
            pystray.Menu(pystray.MenuItem("Пауза микрофона", pause, checked=lambda item: self.paused.is_set()),
                         pystray.MenuItem("Выбрать микрофон…", microphone_settings),
                         pystray.MenuItem("Открыть инструкцию", lambda: os.startfile(str(ROOT / "README.txt"))),
                         pystray.MenuItem("Выход", quit_app)))

        def worker():
            try:
                self.icon.title = "Джарвис — слушает"
                self.run(seconds)
            except Exception:
                LOG.exception("Помощник остановлен из-за ошибки")
                ctypes.windll.user32.MessageBoxW(0, "Не удалось запустить Джарвиса. Откройте jarvis.log в папке помощника.", "Джарвис", 16)
            finally:
                self.stop.set()
                self.icon.stop()

        def setup(icon):
            icon.visible = True
            threading.Thread(target=worker, daemon=True).start()

        self.icon.run(setup=setup)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--devices", action="store_true")
    parser.add_argument("--console", action="store_true")
    parser.add_argument("--seconds", type=int)
    parser.add_argument("--speak-test", action="store_true")
    parser.add_argument("--tray-test", action="store_true")
    parser.add_argument("--recognize-wav")
    args = parser.parse_args()
    handler = RotatingFileHandler(ROOT / "jarvis.log", maxBytes=256000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    if args.devices:
        import sounddevice as sd
        print(sd.query_devices())
        return
    if args.speak_test:
        speak("Джарвис готов. Проверка русского голоса.")
        return
    cfg = config()
    if args.recognize_wav:
        from vosk import Model, KaldiRecognizer
        with wave.open(args.recognize_wav, "rb") as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                raise ValueError("Expected mono PCM16 WAV")
            rec = KaldiRecognizer(Model(str(ROOT / cfg["model_path"])), audio.getframerate())
            rec.SetWords(True)
            rec.AcceptWaveform(audio.readframes(audio.getnframes()))
            print(rec.FinalResult())
        return
    # A named local-session mutex prevents two copies listening/executing at once.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, False, "Local\\JarvisOfflineEgor")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        return
    try:
        assistant = Assistant(cfg)
        if args.tray_test:
            assistant.tray(args.seconds or 5)
        elif args.console or args.seconds:
            assistant.run(args.seconds)
        else:
            assistant.tray()
    finally:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        LOG.exception("Ошибка запуска")
        raise
