// VoiceBridge v2.1 — Streaming ASR + AudioWorklet
const WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/translate`;

let ws = null;
let stream = null;
let audioCtx = null;
let isRunning = false;
let useSpeaker = true;
let sentChunks = 0;
let micLevel = 0;
let micGain = 2.0;  // Mic gain multiplier

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
    const constraints = {
        audio: {
            sampleRate: 16000,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
        }
    };
    try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (e) {
        alert('需要麦克风权限: ' + e.message);
        return;
    }

    setStatus('connecting', '● 连接中...');
    ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'config', source_lang: sourceLang.value, target_lang: targetLang.value }));
    };

    ws.onmessage = (event) => {
        if (typeof event.data !== 'string') return;
        const msg = JSON.parse(event.data);

        if (msg.type === 'interim') {
            // Real-time streaming transcript
            setStatus('interim', `🎯 "${msg.text.slice(0, 30)}"`);
        } else if (msg.type === 'recognized') {
            setStatus('recognized', `🎯 识别: "${msg.text.slice(0, 30)}"`);
        } else if (msg.type === 'result') {
            setStatus('playing', `🔊 "${msg.translated.slice(0, 30)}"`);
            showResult(msg.original, msg.translated);
            addHistory(msg.original, msg.translated);
            if (msg.audio) {
                playAudio(msg.audio);
            }
        }
    };

    ws.onclose = () => { if (isRunning) setStatus('error', '⚠ 连接断开'); };
    ws.onerror = () => { setStatus('error', '⚠ 连接失败'); };

    // Audio processing — use AudioWorklet if available, fallback to ScriptProcessorNode
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    if (audioCtx.state === 'suspended') await audioCtx.resume();

    const source = audioCtx.createMediaStreamSource(stream);
    const gainNode = audioCtx.createGain();
    gainNode.gain.value = micGain;
    source.connect(gainNode);

    sentChunks = 0;

    if (audioCtx.audioWorklet) {
        // Modern AudioWorklet path
        try {
            await audioCtx.audioWorklet.addModule('/processor.js');
            const workletNode = new AudioWorkletNode(audioCtx, 'voice-processor');
            workletNode.port.onmessage = (e) => {
                if (!ws || ws.readyState !== WebSocket.OPEN) return;
                const pcm = e.data;
                if (pcm.byteLength < 100) return;
                sentChunks++;
                ws.send(pcm);
            };
            gainNode.connect(workletNode);
            // Mute passthrough — user should NOT hear their own voice
            const muteGain = audioCtx.createGain();
            muteGain.gain.value = 0;
            workletNode.connect(muteGain);
            muteGain.connect(audioCtx.destination);
        } catch (e) {
            console.warn('AudioWorklet failed, using ScriptProcessorNode fallback:', e.message);
            setupScriptProcessor(gainNode);
        }
    } else {
        setupScriptProcessor(gainNode);
    }

    isRunning = true;
    startBtn.textContent = '⏹ 停止';
    startBtn.classList.add('active');

    // Diagnostic update
    const diagTimer = setInterval(() => {
        if (!isRunning) { clearInterval(diagTimer); return; }
        fetch('/debug/status').then(r => r.json()).then(d => {
            setStatus('listening', `🎙 发:${sentChunks} | 收:${d.audio_chunks_received} | 识:${d.transcripts_detected}`);
        }).catch(() => {});
    }, 3000);
}

function setupScriptProcessor(sourceNode) {
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    const zeroGain = audioCtx.createGain();
    zeroGain.gain.value = 0;
    sourceNode.connect(processor);
    processor.connect(zeroGain);
    zeroGain.connect(audioCtx.destination);

    processor.onaudioprocess = (e) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);

        // RMS (root mean square) for diagnostic display only
        micLevel = Math.sqrt(input.reduce((sum, v) => sum + v * v, 0) / input.length);

        // Send ALL audio to server — let Deepgram handle silence detection
        sentChunks++;
        ws.send(float32ToPCM16(input).buffer);
    };
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
    if (!base64Audio) return;
    try {
        const binary = atob(base64Audio);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], { type: 'audio/mp3' });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        await audio.play();
        await new Promise(resolve => { audio.onended = resolve; });
        URL.revokeObjectURL(url);
    } catch (e) {
        // Audio playback failed — result already shown as text
    }
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
