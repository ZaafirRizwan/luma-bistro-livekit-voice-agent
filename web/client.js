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
