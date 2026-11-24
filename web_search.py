"""Explicit DuckDuckGo search. Search results can never request PC actions."""
import ipaddress
from urllib.parse import urlparse, urlencode

PREFIXES = ('найди в интернете ', 'поищи в интернете ', 'найди информацию о ',
            'найди информацию про ', 'найди ', 'поищи ', 'поиск ')


def search_query(text):
    for prefix in PREFIXES:
        if text.startswith(prefix):
            query = text[len(prefix):].strip()
            return query[:350] or None
    return None


def public_link(url):
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme != 'https' or not host or parsed.username or parsed.password:
            return False
        if host == 'localhost' or host.endswith(('.local','.localhost')):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return '.' in host
    except (TypeError, ValueError):
        return False


def search(query):
    from ddgs import DDGS
    try:
        rows = DDGS(timeout=12).text(query[:350], region='ru-ru', safesearch='moderate',
                                    max_results=3, backend='duckduckgo')
    except Exception:
        rows = []
    results = [{'title':str(r.get('title','Источник'))[:180], 'url':r['href'],
             'body':str(r.get('body',''))[:900]} for r in rows if public_link(r.get('href',''))][:3]
    if results:
        return results
    # The official Instant Answer API is a distinct public service. It does not
    # solve or bypass the CAPTCHA protecting DuckDuckGo's HTML search page.
    import requests
    response = requests.get('https://api.duckduckgo.com/', params={'q':query[:350],
        'format':'json','no_html':1,'no_redirect':1}, timeout=12)
    response.raise_for_status()
    data = response.json()
    if data.get('AbstractText') and public_link(data.get('AbstractURL','')):
        results.append({'title':str(data.get('Heading','DuckDuckGo'))[:180],
                        'url':data['AbstractURL'],'body':str(data['AbstractText'])[:900]})
    related = list(data.get('RelatedTopics',[]))
    while related and len(results)<3:
        topic = related.pop(0)
        if 'Topics' in topic:
            related.extend(topic['Topics'])
        elif public_link(topic.get('FirstURL','')) and topic.get('Text'):
            results.append({'title':topic['Text'][:100],'url':topic['FirstURL'], 'body':topic['Text'][:900]})
    return results


def fallback_link(query):
    return 'https://duckduckgo.com/?'+urlencode({'q':query[:350]})
