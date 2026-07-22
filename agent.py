"""LiveKit worker for Luma Bistro. Run separately from the mock API."""
import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, RunContext, TurnHandlingOptions, function_tool, inference

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("luma.agent")
API_URL = os.getenv("RESERVATION_API_URL", "http://127.0.0.1:8000")
server = AgentServer()

@dataclass
class CallState:
    client: httpx.AsyncClient
    reservation_id: Optional[str] = None
    pending_action: Optional[str] = None
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_latencies_ms: list[float] = field(default_factory=list)
    confirmed_action: Optional[str] = None

class LumaAgent(Agent):
    def __init__(self):
        super().__init__(instructions="""You are Luma, the concise, warm phone host for Luma Bistro.
Restaurant facts: America/Los_Angeles; Tue-Sun 5-10 PM; 30-minute slots; parties over 8 need handoff.
You MUST use tools for every reservation fact and write. Never invent availability.
For a new reservation, collect name, phone, natural-language date/time, party size, and optional notes; convert them to the ISO date and 24-hour time required by tools internally. NEVER ask a caller to say an ISO date, a four-digit time, or any other tool format. Say natural phrases such as "Friday, August 14 at 6:30 PM." In this assessment, Friday August 14 is 2026-08-14, Saturday August 15 is 2026-08-15, and Sunday August 16 is 2026-08-16. If a natural date is genuinely ambiguous, confirm it naturally (for example, "Do you mean Friday, August 14?") rather than asking for YYYY-MM-DD. Understand spoken phone phrasing such as "four two four triple five zero one double eight" and normalize it internally; if uncertain, repeat the digits naturally for confirmation. Check availability; state all critical details and get an explicit yes, then call authorize_write(action='create') immediately before create_reservation.
For a change/cancellation, first find_reservation using phone or confirmation code; describe the exact change and get an explicit yes, then call authorize_write with the matching action immediately before the write.
If the caller corrects a detail, stop the prior confirmation, acknowledge it, and use the corrected value. Do not create twice: call create only once per confirmed request.
On tool errors, explain briefly. For a temporary availability failure retry exactly once; if it fails again, call handoff. Keep responses short and speakable.""")

    async def _request(self, state: CallState, method: str, path: str, **kwargs):
        started=time.perf_counter()
        response=await state.client.request(method, path, **kwargs)
        latency=(time.perf_counter()-started)*1000; state.tool_latencies_ms.append(latency)
        log.info("tool=%s status=%s latency_ms=%.1f", path, response.status_code, latency)
        if response.status_code >= 400:
            return {"ok":False,"status":response.status_code,"error":response.json().get('detail',{})}
        return {"ok":True,"data":response.json(),"latency_ms":round(latency,1)}

    @function_tool
    async def check_availability(self, context: RunContext[CallState], date: str, time: str, party_size: int) -> dict:
        """Check a requested ISO date and HH:MM time before offering or booking it."""
        if not 1 <= party_size <= 8: return {"ok":False,"error":"Party size must be 1 through 8; offer human handoff for larger parties."}
        result=await self._request(context.userdata,'GET','/availability',params={'date':date,'time':time,'party_size':party_size})
        if result.get('status') == 503:
            await asyncio.sleep(.5)
            result=await self._request(context.userdata,'GET','/availability',params={'date':date,'time':time,'party_size':party_size})
        return result

    @function_tool
    async def authorize_write(self, context: RunContext[CallState], action: str) -> dict:
        """Arm exactly one create, modify, or cancel write only after the caller has just explicitly said yes to the final summary."""
        if action not in {'create','modify','cancel'}:
            return {'ok':False,'error':'action must be create, modify, or cancel'}
        context.userdata.confirmed_action=action
        log.info('write authorized action=%s', action)
        return {'ok':True,'action':action,'message':'One confirmed write is authorized.'}

    @function_tool
    async def create_reservation(self, context: RunContext[CallState], name: str, phone: str, date: str, time: str, party_size: int, notes: Optional[str]=None) -> dict:
        """Create one already-confirmed reservation. Never call unless caller just explicitly confirmed all details."""
        state=context.userdata
        if state.confirmed_action != 'create':
            return {'ok':False,'error':'Creation blocked: restate critical details, obtain explicit confirmation, then call authorize_write(action="create").'}
        payload={'name':name,'phone':phone,'date':date,'time':time,'party_size':party_size,'notes':notes}
        try:
            return await self._request(state,'POST','/reservations',json=payload,headers={'Idempotency-Key':state.idempotency_key})
        finally:
            state.confirmed_action=None

    @function_tool
    async def find_reservation(self, context: RunContext[CallState], phone: Optional[str]=None, confirmation_code: Optional[str]=None) -> dict:
        """Find an existing reservation using a phone number or LUMA confirmation code."""
        result=await self._request(context.userdata,'GET','/reservations/search',params={'phone':phone,'confirmation_code':confirmation_code})
        if result.get('ok') and len(result['data']['results']) == 1: context.userdata.reservation_id=result['data']['results'][0]['reservation_id']
        return result

    @function_tool
    async def modify_reservation(self, context: RunContext[CallState], date: Optional[str]=None, time: Optional[str]=None, party_size: Optional[int]=None, notes: Optional[str]=None) -> dict:
        """Apply an already-confirmed modification to the reservation that was found in this call."""
        state=context.userdata
        if not state.reservation_id: return {'ok':False,'error':'Find the reservation first.'}
        if state.confirmed_action != 'modify': return {'ok':False,'error':'Modification blocked: get explicit confirmation then authorize_write(action="modify").'}
        try:
            return await self._request(state,'PATCH',f'/reservations/{state.reservation_id}',json={k:v for k,v in {'date':date,'time':time,'party_size':party_size,'notes':notes}.items() if v is not None})
        finally:
            state.confirmed_action=None

    @function_tool
    async def cancel_reservation(self, context: RunContext[CallState]) -> dict:
        """Cancel the found reservation after caller explicitly confirms cancellation."""
        if not context.userdata.reservation_id: return {'ok':False,'error':'Find the reservation first.'}
        if context.userdata.confirmed_action != 'cancel': return {'ok':False,'error':'Cancellation blocked: get explicit confirmation then authorize_write(action="cancel").'}
        try:
            return await self._request(context.userdata,'POST',f'/reservations/{context.userdata.reservation_id}/cancel')
        finally:
            context.userdata.confirmed_action=None

    @function_tool
    async def handoff(self, context: RunContext[CallState], reason: str, conversation_summary: str, customer_phone: Optional[str]=None) -> dict:
        """Queue a human handoff when the request cannot safely be completed."""
        return await self._request(context.userdata,'POST','/handoff',json={'reason':reason,'conversation_summary':conversation_summary,'customer_phone':customer_phone})

@server.rtc_session(agent_name='luma-reservation-agent')
async def entrypoint(ctx: JobContext):
    await ctx.connect()
    client=httpx.AsyncClient(base_url=API_URL,timeout=8.0)
    state=CallState(client=client)
    session=AgentSession(
        stt=inference.STT(model='deepgram/flux-general',language='en'),
        # Smaller streaming model keeps reservation turns responsive; tools enforce correctness.
        llm=inference.LLM(model='openai/gpt-4.1-mini',extra_kwargs={'temperature':0.2}),
        tts=inference.TTS(model='cartesia/sonic-3',voice='9626c31c-bec5-4cca-baa8-f8ba9e84c8bc',language='en'),
        # Semantic turn detection reduces awkward pauses and supports barge-in.
        turn_handling=TurnHandlingOptions(turn_detection=inference.TurnDetector()),
        userdata=state,
    )
    @session.on('error')
    def on_error(event): log.exception('session error: %s', event)
    await session.start(agent=LumaAgent(),room=ctx.room)
    await session.generate_reply(instructions='Greet the caller and ask how you can help with a reservation.')

if __name__ == '__main__':
    from livekit.agents import cli
    cli.run_app(server)
