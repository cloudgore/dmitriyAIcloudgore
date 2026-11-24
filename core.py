"""Exact Russian command allowlist and one-shot wake state. No shell input."""
import re
import time
from dataclasses import dataclass


def normalize(text):
    return re.sub(r"[^а-яa-z0-9 ]", " ", text.lower().replace("ё", "е")).strip()


COMMANDS = {
    "включи музыку": "music", "открой музыку": "music",
    "запусти музыку": "music", "включи яндекс музыку": "music",
    "запусти яндекс музыку": "music", "музыку": "music", "музыка": "music",
    "открой яндекс музыку": "music", "плей пауза": "play_pause",
    "следующий трек": "next", "предыдущий трек": "previous",
    "громче": "volume_up", "сделай громче": "volume_up",
    "тише": "volume_down", "сделай тише": "volume_down",
    "выключи звук": "mute", "включи звук": "unmute",
    "открой блокнот": "notepad", "открой калькулятор": "calculator",
    "открой браузер": "browser", "который час": "time",
    "что ты умеешь": "help", "отмена": "cancel",
    "выключи помощника": "quit", "заверши работу помощника": "quit",
}


def add_phrase(phrase, action):
    previous = COMMANDS.setdefault(phrase, action)
    if previous != action:
        raise ValueError("Ambiguous command phrase: " + phrase)


# Expand ONLY known actions and objects. Extra words, negations and second
# actions are never discarded or interpreted as paths, URLs or shell input.
for action, verbs, objects in [
    ("music", ("включи", "включай", "запусти", "поставь", "открой", "включить", "запустить", "поставить", "открыть", "вруби", "включим"),
     ("музыку", "яндекс музыку", "музыку в яндексе")),
    ("notepad", ("открой", "запусти", "включи", "открыть", "запустить"), ("блокнот",)),
    ("calculator", ("открой", "запусти", "включи", "открыть", "запустить"), ("калькулятор",)),
    ("browser", ("открой", "запусти", "включи", "открыть", "запустить"), ("браузер",)),
    ("mute", ("выключи", "отключи", "убери"), ("звук",)),
    ("unmute", ("включи", "верни"), ("звук",)),
]:
    for verb in verbs:
        for obj in objects:
            add_phrase(verb + " " + obj, action)
            add_phrase(obj + " " + verb, action)

for action, phrases in {
    "volume_up": ("прибавь громкость", "увеличь громкость", "громкость прибавь", "погромче", "сделай звук громче"),
    "volume_down": ("убавь громкость", "уменьши громкость", "громкость убавь", "потише", "сделай звук тише"),
    "play_pause": ("нажми паузу", "поставь на паузу", "пауза", "переключи воспроизведение"),
    "next": ("включи следующий трек", "переключи трек", "следующая песня", "следующий"),
    "previous": ("включи предыдущий трек", "предыдущая песня", "предыдущий"),
    "time": ("скажи время", "сколько времени", "время скажи", "скажи который час"),
    "help": ("помощь", "покажи команды", "расскажи что ты умеешь"),
    "cancel": ("отмени", "ничего не надо"),
}.items():
    for phrase in phrases:
        add_phrase(phrase, action)

for action, phrases in {
    "pause": ("пауза", "поставь паузу", "поставь на паузу", "музыку на паузу", "поставь музыку на паузу",
              "останови музыку", "останови воспроизведение", "приостанови музыку", "пауза музыки"),
    "play": ("продолжи", "продолжи музыку", "возобнови музыку", "сними с паузы", "сними музыку с паузы",
             "продолжай музыку", "продолжи воспроизведение"),
    "next": ("дальше", "трек вперед", "музыку вперед", "переключи вперед", "переключи музыку вперед",
             "переключи на следующий трек", "включи следующий", "следующая песня", "следующую песню",
             "включи следующую песню", "следующий трек", "следующий"),
    "previous": ("назад", "трек назад", "музыку назад", "переключи назад", "переключи музыку назад",
                 "переключи на предыдущий трек", "включи предыдущий", "предыдущая песня", "предыдущую песню",
                 "включи предыдущую песню", "предыдущий трек", "предыдущий"),
}.items():
    for phrase in phrases:
        COMMANDS[phrase] = action


# Additional finite music-only vocabulary; no general language execution.
for action, phrases in {
    'pause': ('поставить паузу','ставь паузу','сделай паузу','включи паузу','включить паузу',
              'останови','остановить музыку','выключи музыку','выруби музыку',
              'поставь воспроизведение на паузу','поставь песню на паузу','поставь трек на паузу',
              'поставь музыку паузу','музыка на паузу','музыка пауза'),
    'play': ('продолжить','продолжай','убери паузу','сними паузу','снять с паузы','возобнови',
             'продолжить музыку','продолжи играть','возобнови воспроизведение',
             'включи музыку обратно','продолжи песню','продолжи трек','продолжи воспроизведение музыки'),
    'next': ('следующая','вперёд','вперед','переключи песню','переключи трек','другую песню',
             'следующий трэк','включи следующий трэк','переключи на следующую песню'),
    'previous': ('предыдущая','предыдущий трэк','включи предыдущий трэк',
                 'переключи на предыдущую песню','верни предыдущую песню','верни предыдущий трек'),
}.items():
    for phrase in phrases:
        add_phrase(normalize(phrase),action)


for phrase, action in list(COMMANDS.items()):
    for prefix in ("пожалуйста ", "можешь ", "можешь пожалуйста ", "давай "):
        add_phrase(prefix + phrase, action)
    add_phrase(phrase + " пожалуйста", action)
    # Common polite placement between the verb and its object.
    if " " in phrase:
        first, rest = phrase.split(" ", 1)
        add_phrase(first + " пожалуйста " + rest, action)
        add_phrase(first + " мне " + rest, action)


# Reorder ONLY the exact words of an allowlisted music-control phrase.
# Unknown words, negation, duplicate words, extra actions remain rejected.
MUSIC_WORD_ORDERS = {}
for phrase,action in COMMANDS.items():
    if action in {'pause','play','next','previous','play_pause'}:
        words=tuple(sorted(w for w in phrase.split() if w not in {'пожалуйста','мне','ты','можешь'}))
        previous=MUSIC_WORD_ORDERS.setdefault(words,action)
        if previous != action:
            raise ValueError('Ambiguous music control vocabulary')


@dataclass
class Decision:
    kind: str
    action: str = ""


def resolve_command(text):
    if text in COMMANDS:
        return COMMANDS[text]
    # Only harmless polite filler is removable. Negations and all unknown
    # words remain, so additional actions/paths never become executable.
    compact=' '.join(w for w in text.split() if w not in {'пожалуйста','мне','ты','можешь'})
    return COMMANDS.get(compact) or MUSIC_WORD_ORDERS.get(tuple(sorted(compact.split())))


def prepare_question(text):
    text=re.sub(r'\bо\s+з\s+у\b|\bо\s+зу\b','озу',text)
    if text in {'озу','что такое озу','объясни что такое озу','расскажи про озу'}:
        return 'Что такое оперативная память (ОЗУ)?'
    return text


class Gate:
    def __init__(self, wake_phrases, timeout=8, clock=time.monotonic):
        self.wakes = [normalize(w) for w in wake_phrases]
        self.timeout, self.clock, self.until = timeout, clock, 0
        # Russian ASR can spell the stressed name Димон as the homophone демон.
        # This fixed correction applies only at the start, and only if Димон is enabled.
        self.aliases = {'демон':'димон'} if 'димон' in self.wakes else {}
        if 'дима' in self.wakes:
            self.aliases['димо']='дима'
        self.recognition_wakes = self.wakes + list(self.aliases)

    def canonicalize(self, text):
        text=' '.join(normalize(text).split())
        for alias,canonical in self.aliases.items():
            if text==alias or text.startswith(alias+' '):
                return canonical+text[len(alias):]
        return text

    def reset(self):
        self.until = 0

    def feed(self, text):
        text = self.canonicalize(text)
        if not text:
            return Decision("ignore")
        # Activation must START the utterance; incidental mentions do not activate.
        for wake in self.wakes:
            if text == wake or text.startswith(wake + " "):
                command = text[len(wake):].strip()
                self.until = self.clock() + self.timeout
                if not command:
                    return Decision("wake")
                break
        else:
            if self.clock() >= self.until:
                self.reset()
                return Decision("ignore")
            command = text
        action = resolve_command(command)
        if action:
            self.reset()  # A successful command consumes the activation.
            return Decision("command", action)
        # Noise/unknown speech does not terminate or extend the response window.
        return Decision("unknown")
