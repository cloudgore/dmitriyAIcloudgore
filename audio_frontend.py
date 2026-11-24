"""Small local PCM16 gain stage and silence timer. Never records audio."""
from array import array
import math


class AudioFrontend:
    def __init__(self, rate, gain=1.6, automatic=False):
        self.rate=rate
        self.gain=max(1.0,min(3.0,float(gain)))
        self.noise=8.0
        self.silence=0.0
        self.has_speech=False
        self.automatic=automatic
        self.current_gain=self.gain

    def process(self, data):
        samples=array('h',data)
        if not samples:
            return data,self.silence
        rms=math.sqrt(sum(float(x)*x for x in samples)/len(samples))
        threshold=max(12.0,self.noise*2.0)
        if rms>threshold:
            self.silence=0.0
            self.has_speech=True
        else:
            self.silence+=len(samples)/self.rate
        self.noise=.99*self.noise+.01*min(rms,self.noise*3+20)
        peak=max(abs(x) for x in samples)
        if self.automatic:
            target=max(self.gain,min(12.0,1400/max(1,rms))) if rms>threshold else 1.0
            self.current_gain=.75*self.current_gain+.25*target
        gain=min(self.current_gain if self.automatic else self.gain,30000/max(1,peak))
        if gain>1.01:
            samples=array('h',(int(x*gain) for x in samples))
            return samples.tobytes(),self.silence
        return data,self.silence

    def reset_segment(self):
        self.silence=0.0
        self.has_speech=False


def early_endpoint(partial,wakes,silence,command_silence=.45):
    partial=' '.join(partial.strip().split())
    if not partial:
        return False
    return silence >= (.24 if partial in wakes else max(.35,float(command_silence)))
