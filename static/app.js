// VoiceBridge v2 — Solo Translation
const WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/translate`;

let ws = null;
let stream = null;
let audioCtx = null;
let isRunning = false;
let history = [];
let useSpeaker = true;

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

// Start/Stop
startBtn.addEventListener('click', () => {
    if (isRunning) {
        stop();
    } else {
        start();
    }
});

// Audio output toggle
outputToggle.addEventListener('click', () => {
    useSpeaker = !useSpeaker;
    outputToggle.textContent = useSpeaker ? '🔊 扬声器' : '🎧 耳机';
});

async function start() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
        alert('需要麦克风权限才能使用翻译功能');
        return;
    }

    // WebSocket
    ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        setStatus('listening', '● 正在听...');
        ws.send(JSON.stringify({
            type: 'config',
            source_lang: sourceLang.value,
            target_lang: targetLang.value,
        }));
    };

    ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
            const msg = JSON.parse(event.data);
            if (msg.type === 'result') {
                showResult(msg.original, msg.translated);
                playAudio(msg.audio);
                addHistory(msg.original, msg.translated);
            } else if (msg.type === 'pong') {
                // heartbeat
            }
        }
    };

    ws.onclose = () => {
        if (isRunning) setStatus('idle', '○ 连接断开，点击重试');
    };

    ws.onerror = () => {
        setStatus('idle', '○ 连接失败');
    };

    // Audio capture
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);

    source.connect(processor);
    processor.connect(audioCtx.destination);

    processor.onaudioprocess = (e) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        const pcm = float32ToPCM16(input);
        ws.send(pcm.buffer);
    };

    isRunning = true;
    startBtn.textContent = '⏹ 停止';
    startBtn.classList.add('active');
}

function stop() {
    if (stream) {
        stream.getTracks().forEach(t => t.stop());
        stream = null;
    }
    if (audioCtx) {
        audioCtx.close();
        audioCtx = null;
    }
    if (ws) {
        ws.close();
        ws = null;
    }
    isRunning = false;
    startBtn.textContent = '🎤 开始翻译';
    startBtn.classList.remove('active');
    setStatus('idle', '○ 已就绪');
    currentCard.classList.add('hidden');
}

function setStatus(state, text) {
    statusEl.className = `status ${state}`;
    statusEl.textContent = text;
}

function showResult(original, translated) {
    currentCard.classList.remove('hidden');
    currentOriginal.textContent = original;
    currentTranslated.textContent = translated;
    setStatus('translating', '● 翻译完成');
    setTimeout(() => {
        if (isRunning) setStatus('listening', '● 正在听...');
    }, 1500);
}

function playAudio(base64Audio) {
    try {
        const binary = atob(base64Audio);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

        const blob = new Blob([bytes], { type: 'audio/mp3' });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);

        if (!useSpeaker) {
            // @ts-ignore — setSinkId may not be in all browsers
            if (audio.setSinkId) {
                audio.setSinkId('none').catch(() => {});
            }
        }

        audio.play().catch(() => {});
        audio.onended = () => URL.revokeObjectURL(url);
    } catch (e) {
        console.error('Audio playback error:', e);
    }
}

function addHistory(original, translated) {
    history.unshift({ original, translated, time: new Date() });
    if (history.length > 20) history.pop();

    historyList.innerHTML = history.map(h =>
        `<div class="history-item">
            <div class="hi-original">${escapeHtml(h.original)}</div>
            <div class="hi-translated">${escapeHtml(h.translated)}</div>
        </div>`
    ).join('');
}

function float32ToPCM16(float32) {
    const pcm = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
        const s = Math.max(-1, Math.min(1, float32[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return new Uint8Array(pcm.buffer);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
