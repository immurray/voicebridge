// VoiceBridge v2 — Solo Translation
const WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/translate`;

let ws = null;
let stream = null;
let audioCtx = null;
let isRunning = false;
let isBusy = false;  // Don't overwrite status during translation
let history = [];
let useSpeaker = true;
let sentChunks = 0;
let srvChunks = 0;
let srvTrans = 0;
let micLevel = 0;

// DOM
const startBtn = document.getElementById('startBtn');
const statusEl = document.getElementById('status');
const currentCard = document.getElementById('currentCard');
const currentOriginal = document.getElementById('currentOriginal');
const currentTranslated = document.getElementById('currentTranslated');
const historyList = document.getElementById('historyList');
const outputToggle = document.getElementById('outputToggle');
const sourceLang = document.getElementById('sourceLang');
const targetLang = document.getElementById('targetLang');

// Fetch version on load
fetch('/version')
    .then(r => r.json())
    .then(v => {
        document.getElementById('buildVersion').textContent = `v${v.version} (${v.build.slice(0, 7)})`;
    })
    .catch(() => {});

startBtn.addEventListener('click', () => isRunning ? stop() : start());

outputToggle.addEventListener('click', () => {
    useSpeaker = !useSpeaker;
    outputToggle.textContent = useSpeaker ? '🔊 扬声器' : '🎧 耳机';
});

async function start() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
        alert('需要麦克风权限');
        return;
    }

    setStatus('connecting', '● 连接中...');
    ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        updateDiag();
        ws.send(JSON.stringify({ type: 'config', source_lang: sourceLang.value, target_lang: targetLang.value }));
    };

    ws.onmessage = (event) => {
        if (typeof event.data !== 'string') return;
        const msg = JSON.parse(event.data);

        if (msg.type === 'result') {
            isBusy = true;
            setStatus('playing', `🔊 "${msg.translated.slice(0, 30)}"`);
            showResult(msg.original, msg.translated);
            addHistory(msg.original, msg.translated);
            playAudio(msg.audio).then(() => {
                isBusy = false;
                updateDiag();
            }).catch(() => {
                isBusy = false;
                setStatus('listening', `🎙 播放失败 | mic:${micLevel.toFixed(2)} 发:${sentChunks}`);
            });
        } else if (msg.type === 'status' && msg.state === 'recognized') {
            isBusy = true;
            setStatus('recognized', `🎯 识别: "${msg.text.slice(0, 30)}"`);
        }
    };

    ws.onclose = () => { if (isRunning) setStatus('error', '⚠ 连接断开'); };
    ws.onerror = () => { setStatus('error', '⚠ 连接失败'); };

    // Audio capture
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    if (audioCtx.state === 'suspended') await audioCtx.resume();

    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    const zeroGain = audioCtx.createGain();
    zeroGain.gain.value = 0;
    source.connect(processor);
    processor.connect(zeroGain);
    zeroGain.connect(audioCtx.destination);

    sentChunks = 0;
    srvChunks = 0;
    srvTrans = 0;
    isBusy = false;

    processor.onaudioprocess = (e) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        micLevel = Math.sqrt(input.reduce((sum, v) => sum + v * v, 0) / input.length);
        if (micLevel < 0.0005) return;
        sentChunks++;
        ws.send(float32ToPCM16(input).buffer);
    };

    isRunning = true;
    startBtn.textContent = '⏹ 停止';
    startBtn.classList.add('active');

    // Diagnostic — only update when idle
    const diagTimer = setInterval(() => {
        if (!isRunning) { clearInterval(diagTimer); return; }
        if (!isBusy) updateDiag();
    }, 2000);
}

async function updateDiag() {
    try {
        const r = await fetch('/debug/status');
        const d = await r.json();
        srvChunks = d.audio_chunks_received || 0;
        srvTrans = d.transcripts_detected || 0;
    } catch(e) {}
    setStatus('listening', `🎙 mic:${micLevel.toFixed(2)} | 发:${sentChunks} | 收:${srvChunks} | 识:${srvTrans}`);
}

function stop() {
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    if (audioCtx) { audioCtx.close(); audioCtx = null; }
    if (ws) { ws.close(); ws = null; }
    isRunning = false;
    startBtn.textContent = '🎤 开始翻译';
    startBtn.classList.remove('active');
    setStatus('idle', '○ 已就绪');
}

function setStatus(state, text) {
    statusEl.className = `status ${state}`;
    statusEl.textContent = text;
}

function showResult(original, translated) {
    currentCard.classList.remove('hidden');
    currentOriginal.textContent = original;
    currentTranslated.textContent = translated;
}

async function playAudio(base64Audio) {
    const binary = atob(base64Audio);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: 'audio/mp3' });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    await new Promise((resolve, reject) => {
        audio.oncanplaythrough = resolve;
        audio.onerror = reject;
        setTimeout(() => reject(new Error('timeout')), 3000);
    });
    await audio.play();
    await new Promise(resolve => { audio.onended = resolve; });
    URL.revokeObjectURL(url);
}

function addHistory(original, translated) {
    history.unshift({ original, translated });
    if (history.length > 20) history.pop();
    historyList.innerHTML = history.map(h =>
        `<div class="history-item"><div class="hi-original">${h.original}</div><div class="hi-translated">${h.translated}</div></div>`
    ).join('');
}

function float32ToPCM16(f32) {
    const pcm = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
        const s = Math.max(-1, Math.min(1, f32[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return new Uint8Array(pcm.buffer);
}
