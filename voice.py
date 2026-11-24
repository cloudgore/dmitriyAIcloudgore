"""Dmitry Neural TTS; only assistant reply text is sent to Microsoft."""
import asyncio
import ctypes
import hashlib
import logging
from pathlib import Path
import time
import uuid

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("jarvis")


async def synthesize(text, voice, rate, path):
    import edge_tts
    import aiohttp
    if voice != 'ru-RU-DmitryNeural':
        raise ValueError('Voice is not in the allowlist')
    # A fresh socket often succeeds after the service returns NoAudioReceived.
    # Delete incomplete output before each attempt; never play partial audio.
    for attempt in range(4):
        Path(path).unlink(missing_ok=True)
        try:
            communicator = edge_tts.Communicate(text, voice, rate=rate)
            await asyncio.wait_for(communicator.save(str(path)), timeout=25)
            if not Path(path).is_file() or not Path(path).stat().st_size:
                raise edge_tts.exceptions.NoAudioReceived('Empty audio')
            return
        except (edge_tts.exceptions.NoAudioReceived, aiohttp.ClientError, asyncio.TimeoutError):
            Path(path).unlink(missing_ok=True)
            if attempt == 3:
                raise
            LOG.info('Retrying Dmitry Neural synthesis: attempt %s', attempt+2)
            await asyncio.sleep(2 * (attempt + 1))


VOICE_UNAVAILABLE = 'Ответ можно прочитать в окне.'


def cached_notice(cfg):
    key = hashlib.sha256((cfg.get('neural_voice','ru-RU-DmitryNeural')+'\n'+
        cfg.get('neural_rate','+0%')+'\n'+VOICE_UNAVAILABLE).encode('utf-8')).hexdigest()
    path = ROOT/'voice-cache'/(key+'.mp3')
    if path.is_file() and path.stat().st_size:
        play_audio(path)
        return True
    return False


def cached_audio(text, cfg):
    voice = cfg.get("neural_voice", "ru-RU-DmitryNeural")
    if voice != "ru-RU-DmitryNeural":
        raise ValueError("Voice is not in the allowlist")
    rate = cfg.get("neural_rate", "+0%")
    if rate not in ("-10%", "-5%", "+0%", "+5%", "+10%"):
        raise ValueError("Unsupported voice rate")
    cache = ROOT / "voice-cache"
    cache.mkdir(exist_ok=True)
    key = hashlib.sha256((voice + "\n" + rate + "\n" + text).encode("utf-8")).hexdigest()
    path = cache / (key + ".mp3")
    if not path.is_file() or path.stat().st_size == 0:
        pending = cache / (key + '-' + uuid.uuid4().hex + ".part")
        try:
            asyncio.run(synthesize(text, voice, rate, pending))
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
    # Bounded cache, deleting only files this module names and owns.
    files = sorted((p for p in cache.glob("*.mp3") if len(p.stem) == 64 and
                    all(c in "0123456789abcdef" for c in p.stem)), key=lambda p: p.stat().st_mtime)
    for old in files[:-128]:
        if old != path:
            old.unlink(missing_ok=True)
    return path


def play_audio(path):
    path = Path(path).resolve()
    winmm = ctypes.WinDLL("winmm")
    winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    winmm.mciSendStringW.restype = ctypes.c_uint

    def send(command, output=None):
        error = winmm.mciSendStringW(command, output, len(output) if output is not None else 0, None)
        if error:
            raise OSError("Windows MP3 playback error " + str(error))

    send('open "' + str(path) + '" type mpegvideo alias jarvis_voice')
    try:
        send("play jarvis_voice")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            mode = ctypes.create_unicode_buffer(64)
            send("status jarvis_voice mode", mode)
            if mode.value != "playing":
                return
            time.sleep(.05)
        raise TimeoutError("Voice playback timed out")
    finally:
        send("close jarvis_voice")


def say_neural(text, cfg, cache=True):
    if not cache:
        folder = ROOT/'voice-cache'
        folder.mkdir(exist_ok=True)
        path = folder/('temporary-'+uuid.uuid4().hex+'.mp3')
        try:
            asyncio.run(synthesize(text, cfg.get('neural_voice','ru-RU-DmitryNeural'),
                                   cfg.get('neural_rate','+0%'), path))
            play_audio(path)
            return None
        finally:
            path.unlink(missing_ok=True)
    path = cached_audio(text, cfg)
    play_audio(path)
    return path
