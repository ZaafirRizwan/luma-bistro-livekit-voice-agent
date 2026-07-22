from copy import deepcopy
from datetime import datetime
from typing import Optional, Any
from pathlib import Path
import hashlib
import hmac
import logging
import re
import time
from collections import defaultdict
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

app=FastAPI(title="Luma Bistro Reservation API",version="1.0.0")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("luma")
class PIIRedactionFilter(logging.Filter):
    """Last-resort protection: logs must never contain raw phone numbers or emails."""
    phone_pattern=re.compile(r'(?<!\w)(?:\+?\d[\d .()\-]{6,}\d)(?!\w)')
    email_pattern=re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b')
    def filter(self, record):
        try:
            message=record.getMessage()
            record.msg=self.email_pattern.sub('[REDACTED_EMAIL]',self.phone_pattern.sub('[REDACTED_PHONE]',message))
            record.args=()
        except Exception:
            pass
        return True
for handler in logging.getLogger().handlers: handler.addFilter(PIIRedactionFilter())
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
RESTAURANT={"name":"Luma Bistro","timezone":"America/Los_Angeles","hours":"Tue-Sun 17:00-22:00; Mon closed","slot_minutes":30,"max_standard_party_size":8}
INITIAL={
 "2026-08-14":{"17:30":8,"18:00":4,"18:30":0,"19:00":2,"19:30":8,"20:00":6},
 "2026-08-15":{"17:30":6,"18:00":2,"18:30":4,"19:00":0,"19:30":0,"20:00":8},
 "2026-08-16":{"17:30":4,"18:00":4,"18:30":4,"19:00":4,"19:30":4,"20:00":4}}
capacity=deepcopy(INITIAL)
reservations={"res_existing_4821":{"reservation_id":"res_existing_4821","confirmation_code":"LUMA-4821","name":"Alex Morgan","phone":"+13105550147","date":"2026-08-14","time":"18:00","party_size":2,"notes":"Window seat if available","status":"confirmed"}}
idempotency={}
failures={"2026-08-16":0}
handoffs=[]
sessions: dict[str, dict[str, Any]] = {}
metrics=defaultdict(list)
request_latencies=defaultdict(list)
voice_latency_samples=[]

@app.middleware('http')
async def record_request_latency(request: Request, call_next):
    started=time.perf_counter()
    response=await call_next(request)
    # Operational-only telemetry: route/status/latency, never bodies or PII.
    key=f'{request.method} {request.url.path} {response.status_code}'
    request_latencies[key].append((time.perf_counter()-started)*1000)
    response.headers['Cache-Control']='no-store'
    response.headers['Pragma']='no-cache'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Permissions-Policy']='camera=(), geolocation=(), payment=(), microphone=(self)'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; connect-src 'self' https://cdn.jsdelivr.net wss:; media-src blob:; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response

def percentile(values, p):
    ordered=sorted(values)
    return round(ordered[min(len(ordered)-1, int((len(ordered)-1)*p))], 1) if ordered else None

def phone(v): return ''.join(c for c in v if c.isdigit() or c=='+')
def slot(d,t):
    if d not in capacity or t not in capacity[d]: raise HTTPException(422,detail={"code":"INVALID_SLOT"})
def alternatives(d,t,n):
    return [{"date":d,"time":s,"remaining_capacity":c} for s,c in sorted(capacity.get(d,{}).items()) if s!=t and c>=n][:3]

def tool(name: str, fn, **args):
    started=time.perf_counter()
    try:
        result=fn(**args)
        metrics[name].append((time.perf_counter()-started)*1000)
        log.info("tool=%s outcome=ok latency_ms=%.1f", name, metrics[name][-1])
        return result
    except HTTPException:
        metrics[name].append((time.perf_counter()-started)*1000)
        raise

def human_time(t: str):
    hour,minute=map(int,t.split(':')); suffix='PM' if hour>=12 else 'AM'; hour=hour-12 if hour>12 else hour
    return f"{hour}:{minute:02d} {suffix}" if minute else f"{hour} {suffix}"

def parse_phone(text):
    match=re.search(r'(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?){2}\d{4}',text)
    return phone(match.group()) if match else None

def parse_party(text):
    match=re.search(r'\b(?:for|party of|make (?:that|it))\s+(\d+)\b',text.lower())
    return int(match.group(1)) if match else None

def parse_time(text):
    match=re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b',text.lower())
    if not match: return None
    h=int(match.group(1)); m=int(match.group(2) or 0); period=(match.group(3) or '').replace('.','')
    if period=='pm' and h<12: h+=12
    if period=='am' and h==12: h=0
    if h<17 and not period: return None
    return f'{h:02d}:{m:02d}'

def parse_date(text):
    text=text.lower()
    for day,date in {'friday':'2026-08-14','saturday':'2026-08-15','sunday':'2026-08-16'}.items():
        if day in text: return date
    return None

def reply(session_id: str, text: str, event='assistant'):
    s=sessions[session_id]; s['history'].append({'role':event,'text':text})
    return {'session_id':session_id,'say':text,'state':s['state'],'collected':s['slots'],'handoff':s.get('handoff')}

class Create(BaseModel):
    name:str=Field(min_length=2,max_length=100); phone:str=Field(min_length=7,max_length=30); date:str; time:str; party_size:int=Field(ge=1,le=8); notes:Optional[str]=None
class Update(BaseModel):
    date:Optional[str]=None; time:Optional[str]=None; party_size:Optional[int]=Field(default=None,ge=1,le=8); notes:Optional[str]=None
class Handoff(BaseModel):
    reason:str; customer_phone:Optional[str]=None; conversation_summary:str
class TokenRequest(BaseModel):
    participant_name: str = "Guest"
    room_name: Optional[str] = None
class VoiceLatencySample(BaseModel):
    call_id: str = Field(min_length=8,max_length=80)
    end_of_speech_to_audio_ms: float = Field(gt=0,le=60000)

@app.get('/health')
def health(): return {"status":"ok"}
@app.get('/restaurant')
def restaurant(): return RESTAURANT
@app.get('/availability')
def availability(date:str=Query(...),time:str=Query(...),party_size:int=Query(...,ge=1,le=8)):
    slot(date,time)
    if date=='2026-08-16' and failures[date]==0:
        failures[date]+=1
        raise HTTPException(503,detail={"code":"TEMPORARY_UPSTREAM_FAILURE","retry_after_ms":500})
    remaining=capacity[date][time]
    return {"available":remaining>=party_size,"date":date,"time":time,"party_size":party_size,"remaining_capacity":remaining,"alternatives":[] if remaining>=party_size else alternatives(date,time,party_size)}
@app.post('/reservations')
def create(p:Create,idempotency_key:str=Header(...,alias='Idempotency-Key')):
    if idempotency_key in idempotency: return idempotency[idempotency_key]
    slot(p.date,p.time)
    if capacity[p.date][p.time]<p.party_size: raise HTTPException(409,detail={"code":"SLOT_UNAVAILABLE","alternatives":alternatives(p.date,p.time,p.party_size)})
    r={"reservation_id":f"res_{uuid4().hex[:10]}","confirmation_code":f"LUMA-{uuid4().hex[:4].upper()}","name":p.name,"phone":phone(p.phone),"date":p.date,"time":p.time,"party_size":p.party_size,"notes":p.notes,"status":"confirmed","created_at":datetime.utcnow().isoformat()+'Z'}
    capacity[p.date][p.time]-=p.party_size; reservations[r['reservation_id']]=r; idempotency[idempotency_key]=r; return r
@app.get('/reservations/search')
def search(phone_number:Optional[str]=Query(None,alias='phone'),confirmation_code:Optional[str]=None):
    if not phone_number and not confirmation_code: raise HTTPException(422,detail={"code":"SEARCH_CRITERIA_REQUIRED"})
    p=phone(phone_number) if phone_number else None
    out=[r for r in reservations.values() if (p and r['phone']==p) or (confirmation_code and r['confirmation_code'].upper()==confirmation_code.upper())]
    return {"results":out}
@app.patch('/reservations/{reservation_id}')
def update(reservation_id:str,p:Update):
    r=reservations.get(reservation_id)
    if not r: raise HTTPException(404,detail={"code":"NOT_FOUND"})
    if r['status']=='cancelled': raise HTTPException(409,detail={"code":"ALREADY_CANCELLED"})
    nd,nt,np=p.date or r['date'],p.time or r['time'],p.party_size or r['party_size']; slot(nd,nt)
    available=capacity[nd][nt]+(r['party_size'] if nd==r['date'] and nt==r['time'] else 0)
    if available<np: raise HTTPException(409,detail={"code":"SLOT_UNAVAILABLE","alternatives":alternatives(nd,nt,np)})
    capacity[r['date']][r['time']]+=r['party_size']; capacity[nd][nt]-=np
    r.update({"date":nd,"time":nt,"party_size":np,"notes":p.notes if p.notes is not None else r['notes']}); return r
@app.post('/reservations/{reservation_id}/cancel')
def cancel(reservation_id:str):
    r=reservations.get(reservation_id)
    if not r: raise HTTPException(404,detail={"code":"NOT_FOUND"})
    if r['status']!='cancelled': r['status']='cancelled'; capacity[r['date']][r['time']]+=r['party_size']
    return r
@app.post('/handoff')
def handoff(p:Handoff):
    h={"handoff_id":f"handoff_{uuid4().hex[:10]}","status":"queued",**p.model_dump()}; handoffs.append(h); return h
@app.post('/admin/reset')
def reset():
    global capacity,reservations,idempotency,failures,handoffs
    capacity=deepcopy(INITIAL); reservations={"res_existing_4821":{"reservation_id":"res_existing_4821","confirmation_code":"LUMA-4821","name":"Alex Morgan","phone":"+13105550147","date":"2026-08-14","time":"18:00","party_size":2,"notes":"Window seat if available","status":"confirmed"}}; idempotency={}; failures={"2026-08-16":0}; handoffs=[]
    return {"status":"reset"}

@app.get('/admin/metrics')
def get_metrics():
    """Small demo-safe operational view; production would export OpenTelemetry metrics."""
    voice=[sample['end_of_speech_to_audio_ms'] for sample in voice_latency_samples]
    return {"routes":[{"route":route,"count":len(values),"p50_ms":percentile(values,.5),"p95_ms":percentile(values,.95)} for route,values in sorted(request_latencies.items())],"voice_latency":{"count":len(voice),"p50_ms":percentile(voice,.5),"p95_ms":percentile(voice,.95),"last_ms":round(voice[-1],1) if voice else None},"handoff_count":len(handoffs)}

@app.post('/telemetry/voice-latency')
def record_voice_latency(sample: VoiceLatencySample):
    """Receive only timing metadata—never caller/agent transcript text or audio."""
    voice_latency_samples.append({"call_id":sample.call_id,"end_of_speech_to_audio_ms":sample.end_of_speech_to_audio_ms})
    return {"status":"recorded"}

@app.post('/token')
def token(request: TokenRequest, x_demo_access: Optional[str]=Header(None,alias='X-Demo-Access')):
    """Issue a short-lived, room-scoped browser token. Never expose API secrets."""
    import os
    from livekit import api
    url=os.getenv('LIVEKIT_URL')
    key=os.getenv('LIVEKIT_API_KEY')
    secret=os.getenv('LIVEKIT_API_SECRET')
    required_access=os.getenv('DEMO_ACCESS_TOKEN')
    if not all((url,key,secret)):
        raise HTTPException(503, detail='LiveKit is not configured. Copy .env.example to .env.')
    if required_access and not (x_demo_access and hmac.compare_digest(x_demo_access,required_access)):
        raise HTTPException(401, detail='Unauthorized')
    room=request.room_name or f'luma-{uuid4().hex[:12]}'
    identity=f'guest-{uuid4().hex[:12]}'
    jwt=(api.AccessToken(key,secret)
        .with_identity(identity).with_name(request.participant_name[:64])
        .with_ttl(__import__('datetime').timedelta(minutes=15))
        .with_grants(api.VideoGrants(room_join=True,room=room,can_publish=True,can_subscribe=True))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name='luma-reservation-agent')]))
        .to_jwt())
    return {'server_url':url,'participant_token':jwt,'room_name':room}

@app.get('/')
def web_client(): return FileResponse(Path('web/index.html'))

app.mount('/static', StaticFiles(directory='web'), name='static')
