"""Loopback-only bridge. Browser can receive fixed music actions, never run code."""
import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PORT = 17843
ACTIONS = frozenset({'play','pause','next','previous','play_pause'})


class MusicBridge:
    def __init__(self, extension_id):
        if not re.fullmatch('[a-p]{32}',extension_id):
            raise ValueError('Invalid music extension ID')
        self.origin='chrome-extension://'+extension_id
        self.lock=threading.Lock()
        self.clients={}
        self.pending=None
        self.last_result=None
        self.denied=0
        self.requests=0
        bridge=self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def allowed(self):
                valid=(self.headers.get('Host')==f'127.0.0.1:{PORT}' and
                    self.headers.get('Origin') in (None,bridge.origin) and
                    self.headers.get('X-Jarvis-Client')==extension_id)
                if not valid: bridge.denied+=1
                bridge.requests+=1
                return valid
            def reply(self,status,payload):
                body=json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                self.send_header('Cache-Control','no-store')
                if self.headers.get('Origin')==bridge.origin:
                    self.send_header('Access-Control-Allow-Origin',bridge.origin)
                    self.send_header('Access-Control-Allow-Headers','X-Jarvis-Client, Content-Type')
                    self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_OPTIONS(self):
                self.reply(200 if self.headers.get('Origin')==bridge.origin else 403,{})
            def do_GET(self):
                if self.path=='/health' and self.headers.get('Host')==f'127.0.0.1:{PORT}':
                    with bridge.lock:
                        now=time.monotonic()
                        clients=sum(now-v[0]<3 for v in bridge.clients.values())
                    return self.reply(200,{'version':2,'clients':clients,'requests':bridge.requests,
                        'denied':bridge.denied,'last_result':bridge.last_result})
                if not self.allowed(): return self.reply(403,{})
                parts=urlsplit(self.path)
                args=parse_qs(parts.query)
                if parts.path!='/poll': return self.reply(404,{})
                client=args.get('tab',[''])[0]
                if not client.isdigit() or len(client)>16: return self.reply(400,{})
                now=time.monotonic()
                with bridge.lock:
                    bridge.clients[client]=(now,args.get('playing',['0'])[0]=='1',args.get('active',['0'])[0]=='1')
                    bridge.clients={k:v for k,v in bridge.clients.items() if now-v[0]<2}
                    ranked=sorted(bridge.clients,key=lambda k:bridge.clients[k][1:],reverse=True)
                    pending=bridge.pending
                    result={}
                    if pending and now<pending['expires'] and not pending.get('sent') and ranked[0]==client:
                        pending['sent']=client
                        result={'id':pending['id'],'action':pending['action']}
                self.reply(200,result)
            def do_POST(self):
                if not self.allowed(): return self.reply(403,{})
                if self.path!='/result': return self.reply(404,{})
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=512: raise ValueError()
                    data=json.loads(self.rfile.read(size))
                except (ValueError,TypeError): return self.reply(400,{})
                with bridge.lock:
                    pending=bridge.pending
                    if pending and data.get('id')==pending['id'] and str(data.get('tab'))==pending.get('sent'):
                        pending['ok']=data.get('ok') is True
                        bridge.last_result={'action':pending['action'],'ok':pending['ok']}
                        pending['event'].set()
                self.reply(200,{})

        self.server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
        self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def command(self,action):
        if action not in ACTIONS: raise ValueError('Music action not allowlisted')
        with self.lock:
            if self.pending is not None: return False
            pending={'id':secrets.token_hex(16),'action':action,'expires':time.monotonic()+4,'event':threading.Event()}
            self.pending=pending
        try:
            pending['event'].wait(4)
            return pending.get('ok',False)
        finally:
            with self.lock: self.pending=None


_bridge=None
def start(cfg):
    global _bridge
    if _bridge is None:
        _bridge=MusicBridge(cfg['music_extension_id'])
    return _bridge

def control(action,cfg):
    return start(cfg).command(action)
