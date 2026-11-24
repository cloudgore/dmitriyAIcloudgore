"""Fresh structured weather; no LLM estimates, arbitrary URLs, or location sensing."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
import requests

@dataclass(frozen=True)
class WeatherQuery:
    city: str
    day: str = 'now'

ALIASES={'самаре':'Самара','самара':'Самара','москве':'Москва','москва':'Москва',
         'санкт петербурге':'Санкт-Петербург','санкт петербург':'Санкт-Петербург',
         'казани':'Казань','казань':'Казань','тольятти':'Тольятти'}

def parse_weather(text):
    text=' '.join(text.lower().replace('ё','е').split())
    if not re.search(r'\bпогод[ауы]\b',text) or text.startswith(('что такое','почему','как образуется')):
        return None
    day='tomorrow' if re.search(r'\bзавтра\b',text) else 'today' if re.search(r'\bсегодня\b',text) else 'now'
    city=re.sub(r'\b(?:какая|какую|будет|сейчас|сегодня|завтра|скажи|покажи|узнай|расскажи|найди|пожалуйста|мне|прогноз|погода|погоду|погоды|на|в|городе|город|по|интернете)\b',' ',text)
    city=' '.join(city.split()).strip(' ?!.,')
    if not city: city='Самара'
    return WeatherQuery(ALIASES.get(city,city),day)

def description(code):
    if code==0: return 'ясно'
    if code in (1,2): return 'переменная облачность'
    if code==3: return 'пасмурно'
    if code in (45,48): return 'туман'
    if code in (51,53,55): return 'морось'
    if code in (56,57,66,67): return 'ледяные осадки'
    if code in (61,63,65,80,81,82): return 'дождь'
    if code in (71,73,75,77,85,86): return 'снег'
    if code in (95,96,99): return 'гроза'
    return 'переменная погода'

def number(value):
    value=float(value)
    if not math.isfinite(value): raise ValueError('Missing weather value')
    return str(round(value))

def get_weather(query):
    try:
        geo=requests.get('https://geocoding-api.open-meteo.com/v1/search',params={
            'name':query.city,'count':5,'language':'ru','format':'json'},timeout=(3,7))
        geo.raise_for_status()
        places=geo.json().get('results',[])
        if not places:
            return 'Не нашёл этот город. Назови город ещё раз.',[]
        # Prefer an exact city name over a fuzzy prefix result.
        places.sort(key=lambda p:(p.get('name','').casefold()==query.city.casefold(),p.get('population',0)),reverse=True)
        city=places[0]
        latitude,longitude=float(city['latitude']),float(city['longitude'])
        if not (-90<=latitude<=90 and -180<=longitude<=180): raise ValueError('Invalid coordinates')
        forecast=requests.get('https://api.open-meteo.com/v1/forecast',params={
            'latitude':latitude,'longitude':longitude,
            'current':'temperature_2m,apparent_temperature,weather_code,wind_speed_10m',
            'daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
            'wind_speed_unit':'ms','timezone':'auto','forecast_days':2},timeout=(3,7))
        forecast.raise_for_status()
        data=forecast.json()
        name=str(city['name'])[:80]
        if query.day=='now':
            current=data['current']
            stamp=datetime.fromisoformat(current['time']).replace(tzinfo=timezone.utc).timestamp()-int(data['utc_offset_seconds'])
            if abs(datetime.now(timezone.utc).timestamp()-stamp)>10800:
                raise ValueError('Weather data is stale')
            answer=(f'{name}: сейчас {number(current["temperature_2m"])} градусов, '
                f'{description(int(current["weather_code"]))}. Ощущается как {number(current["apparent_temperature"])}. '
                f'Ветер {number(current["wind_speed_10m"])} метров в секунду.')
            updated=current['time']
        else:
            index=1 if query.day=='tomorrow' else 0
            daily=data['daily']
            updated=daily['time'][index]
            label='завтра' if index else 'сегодня'
            answer=(f'{name}: {label} от {number(daily["temperature_2m_min"][index])} '
                f'до {number(daily["temperature_2m_max"][index])} градусов, '
                f'{description(int(daily["weather_code"][index]))}. '
                f'Вероятность осадков {number(daily["precipitation_probability_max"][index])} процентов.')
        return answer,[{'title':'Open-Meteo — прогноз погоды', 'url':forecast.url,
                        'body':f'Местное время данных: {updated}. Прогноз модели Open-Meteo.'}]
    except (requests.RequestException,ValueError,KeyError,IndexError,TypeError):
        return 'Не удалось получить свежую погоду. Попробуй чуть позже.',[]
