"""Audible local activation cue through the normal Windows audio output."""
from array import array
from functools import lru_cache
import io
import math
import wave


@lru_cache(maxsize=1)
def listening_tone():
    rate=24000
    samples=array('h')
    for frequency,duration in [(900,.06),(1350,.08)]:
        count=int(rate*duration)
        for i in range(count):
            fade=min(1,i/(rate*.008),(count-1-i)/(rate*.008))
            samples.append(int(11000*max(0,fade)*math.sin(2*math.pi*frequency*i/rate)))
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(samples.tobytes())
    return output.getvalue()
