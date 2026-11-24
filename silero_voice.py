
import io
import re
import threading
import wave
import winsound
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "models" / "silero" / "v5_ru.pt"

_model = None
_lock = threading.Lock()


def load_model():
    global _model

    if _model is None:
        import torch

        torch.set_num_threads(4)

        _model = torch.package.PackageImporter(
            str(MODEL_PATH)
        ).load_pickle("tts_models", "model")

        _model.to(torch.device("cpu"))

    return _model


def split_text(text, max_chars=180):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue

        words = sentence.split()

        for word in words:
            if current and len(current) + len(word) + 1 > max_chars:
                chunks.append(current)
                current = word
            else:
                current = (current + " " + word).strip()

    if current:
        chunks.append(current)

    return chunks


def speak_local(text):
    import torch

    with _lock:
        model = load_model()

        for chunk in split_text(text):
            with torch.inference_mode():
                audio = model.apply_tts(
                    text=chunk,
                    speaker="eugene",
                    sample_rate=24000,
                )

            samples = (
                audio.clamp(-1, 1) * 32767
            ).to(torch.int16)

            buffer = io.BytesIO()

            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(samples.numpy().tobytes())

            winsound.PlaySound(
                buffer.getvalue(),
                winsound.SND_MEMORY | winsound.SND_SYNC,
            )
