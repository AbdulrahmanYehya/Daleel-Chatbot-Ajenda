const API_KEY = 'replace_with_your_api_key';
const sendBtn = document.getElementById('send');
const msgInput = document.getElementById('msg');
const messages = document.getElementById('messages');
const recordBtn = document.getElementById('record');
const imgFile = document.getElementById('imgfile');
let mediaRecorder, audioChunks = [];
function addMessage(text, cls){ const d=document.createElement('div'); d.className='msg '+cls; d.innerText=text; messages.appendChild(d); messages.scrollTop=messages.scrollHeight; }
sendBtn.onclick = async () => {
  const txt = msgInput.value.trim(); if(!txt) return;
  addMessage(txt, 'user'); msgInput.value='';
  const res = await fetch('http://localhost:8000/chat', {
    method:'POST', headers: {'Content-Type':'application/json', 'x-api-key': API_KEY},
    body: JSON.stringify({ user_id: 'localuser', text: txt })
  });
  const j = await res.json();
  if(j.reply) addMessage(j.reply, 'bot'); else addMessage(JSON.stringify(j), 'bot');
}
recordBtn.onclick = async () => {
  if(!mediaRecorder || mediaRecorder.state === 'inactive') {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      const fd = new FormData();
      fd.append('file', blob, 'record.webm');
      const res = await fetch('http://localhost:8000/upload_audio', { method:'POST', headers:{ 'x-api-key': API_KEY }, body: fd });
      const j = await res.json();
      addMessage('Transcription: ' + j.transcript, 'bot');
    };
    mediaRecorder.start();
    recordBtn.innerText = 'Stop Recording';
  } else {
    mediaRecorder.stop();
    recordBtn.innerText = 'Record Voice';
  }
};
document.getElementById('sendImg').onclick = async () => {
  if(!imgFile.files[0]) { alert('Choose image'); return; }
  const fd = new FormData();
  fd.append('file', imgFile.files[0]);
  const res = await fetch('http://localhost:8000/upload_image', { method:'POST', headers:{ 'x-api-key': API_KEY }, body: fd });
  const j = await res.json();
  addMessage('OCR: ' + j.text, 'bot');
}
