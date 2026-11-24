"""Offline clock assembled from genuine cached Dmitry Neural word clips."""
from array import array
import io
import wave
import winsound

UNITS=('ноль','один','два','три','четыре','пять','шесть','семь','восемь','девять',
       'десять','одиннадцать','двенадцать','тринадцать','четырнадцать','пятнадцать',
       'шестнадцать','семнадцать','восемнадцать','девятнадцать')
TENS={20:'двадцать',30:'тридцать',40:'сорок',50:'пятьдесят'}


def number_words(number,feminine=False):
    if not 0<=number<=59:
        raise ValueError('Clock number out of range')
    if number>=20:
        return [TENS[number//10*10]]+(number_words(number%10,feminine) if number%10 else [])
    if feminine and number in (1,2):
        return ['одна' if number==1 else 'две']
    return [UNITS[number]]


def noun(number,forms):
    if 11<=number%100<=14:
        return forms[2]
    return forms[0] if number%10==1 else forms[1] if 2<=number%10<=4 else forms[2]


def clock_plan(hour,minute):
    if not 0<=hour<=23 or not 0<=minute<=59:
        raise ValueError('Invalid clock time')
    # Concise natural clock reading: «Сейчас одиннадцать двадцать пять».
    # No network-generated inflections are needed at playback time.
    return ['сейчас']+number_words(hour)+(['ноль'] if minute<10 else [])+number_words(minute)


def vocabulary():
    return sorted({word for h in range(24) for m in range(60) for word in clock_plan(h,m)})


def trim(samples,rate=24000):
    samples=array('h',samples)
    if not samples:
        return samples
    threshold=max(35,max(abs(x) for x in samples)*.015)
    step=rate//100
    active=[i for i in range(0,len(samples),step) if max(abs(x) for x in samples[i:i+step])>threshold]
    if not active:
        return samples
    return samples[max(0,active[0]-step):min(len(samples),active[-1]+3*step)]


def say_clock(hour,minute,cfg):
    import miniaudio
    from voice import cached_audio
    output=array('h')
    gap=array('h',[0]*1200)
    for token in clock_plan(hour,minute):
        path=cached_audio(token.capitalize(),cfg)
        decoded=miniaudio.decode_file(str(path),output_format=miniaudio.SampleFormat.SIGNED16,
                                      nchannels=1,sample_rate=24000)
        output.extend(trim(decoded.samples))
        output.extend(gap)
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(output.tobytes())
    winsound.PlaySound(buffer.getvalue(),winsound.SND_MEMORY)
