import { Room, RoomEvent, Track } from 'https://cdn.jsdelivr.net/npm/livekit-client@2.15.6/+esm';

const status = document.querySelector('#status'); const transcript = document.querySelector('#transcript');
const connectButton = document.querySelector('#connect'); const disconnectButton = document.querySelector('#disconnect'); const orb = document.querySelector('#orb');
let room;
const line=(who,text)=>{ const p=document.createElement('p'); p.innerHTML=`<strong>${who}:</strong> ${text}`; transcript.append(p); transcript.scrollTop=transcript.scrollHeight; };
function state(value){status.textContent=value; orb.dataset.state=value.toLowerCase();}

connectButton.onclick = async () => {
  try {
    state('Connecting…'); connectButton.disabled=true;
    const response=await fetch('/token',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({participant_name:'Web guest'})});
    if(!response.ok) throw new Error((await response.json()).detail || 'Token request failed');
    const {server_url,participant_token}=await response.json();
    room=new Room({adaptiveStream:true,dynacast:true});
    room.on(RoomEvent.TrackSubscribed,(track)=>{if(track.kind===Track.Kind.Audio) document.body.append(track.attach());});
    room.on(RoomEvent.TranscriptionReceived,(segments,participant)=>segments.forEach(s=>{if(s.final) line(participant?.isAgent?'Luma':'You',s.text);}));
    room.on(RoomEvent.ConnectionStateChanged,(s)=>state(s === 'connected' ? 'Listening' : s));
    room.on(RoomEvent.Disconnected,()=>{state('Call ended');connectButton.disabled=false;disconnectButton.disabled=true;});
    await room.connect(server_url,participant_token);
    await room.localParticipant.setMicrophoneEnabled(true);
    disconnectButton.disabled=false; state('Listening'); line('System','Connected to Luma.');
  } catch (error) { state(`Could not connect: ${error.message}`); connectButton.disabled=false; }
};
disconnectButton.onclick=()=>room?.disconnect();

const result=document.querySelector('#result'); const scenarios=document.querySelector('#scenarios');
const request=async(path, options={})=>{const r=await fetch(path,options); const body=await r.json(); return {method:options.method||'GET',path,status:r.status,body};};
const json=(body,headers={})=>({method:'POST',headers:{'content-type':'application/json',...headers},body:JSON.stringify(body)});
const create=(key,body)=>request('/reservations',json(body,{'Idempotency-Key':key}));
const reset=()=>request('/admin/reset',{method:'POST'});
const cases={
  T1:async()=>[await reset(),await request('/availability?date=2026-08-14&time=18:00&party_size=4'),await create('play-t1',{name:'Jordan Lee',phone:'310-555-0199',date:'2026-08-14',time:'18:00',party_size:4,notes:null})],
  T2:async()=>[await reset(),await request('/availability?date=2026-08-14&time=18:30&party_size=4'),await create('play-t2',{name:'Taylor Kim',phone:'424-555-0188',date:'2026-08-14',time:'19:30',party_size:4})],
  T3:async()=>[await reset(),await request('/availability?date=2026-08-15&time=18:30&party_size=4'),await create('play-t3',{name:'Casey Brown',phone:'213-555-0114',date:'2026-08-15',time:'18:30',party_size:4})],
  T4:async()=>{const out=[await reset(),await request('/reservations/search?confirmation_code=LUMA-4821')]; const id=out[1].body.results[0].reservation_id; out.push(await request('/reservations/'+id,{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({time:'19:30',party_size:4})}));return out;},
  T5:async()=>[await reset(),await request('/reservations/search?confirmation_code=LUMA-4821'),await request('/reservations/res_existing_4821/cancel',{method:'POST'})],
  T6:async()=>[await reset(),await request('/availability?date=2026-08-16&time=18:00&party_size=2'),await request('/availability?date=2026-08-16&time=18:00&party_size=2')],
  T7:async()=>{const body={name:'Morgan Reed',phone:'310-555-0166',date:'2026-08-14',time:'20:00',party_size:2};return[await reset(),await create('play-same-key',body),await create('play-same-key',body)];}
};
Object.keys(cases).forEach(id=>{const b=document.createElement('button');b.className='scenario';b.textContent=id;b.title='Run '+id;b.onclick=async()=>{result.textContent='Running '+id+'…';try{const calls=await cases[id]();const pass=calls.every(c=>c.status<500)&& (id!=='T6'||calls[1].status===503&&calls[2].status===200);result.textContent=(pass?'PASS ':'CHECK ')+id+'\n\n'+JSON.stringify(calls,null,2);}catch(error){result.textContent='ERROR '+error.message;}};scenarios.append(b);});
document.querySelector('#reset').onclick=async()=>{const r=await reset();result.textContent='Mock data reset\n\n'+JSON.stringify(r,null,2);};
