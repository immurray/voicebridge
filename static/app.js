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

// Fetch version on load
fetch('/version')
    .then(r => r.json())
    .then(v => {
        document.getElementById('buildVersion').textContent = `v${v.version} (${v.build.slice(0, 7)})`;
    })
    .catch(() => {});

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
    setStatus('connecting', '● 连接中...');
    ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        setStatus('listening', '🎙 正在听...（请说话）');
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
                setStatus('playing', '🔊 播放中...');
                showResult(msg.original, msg.translated);
                playAudio(msg.audio).then(() => {
                    if (isRunning) setStatus('listening', '🎙 正在听...（请说话）');
                }).catch((e) => {
                    console.error('Playback failed:', e);
                    if (isRunning) setStatus('listening', '🎙 正在听...（⚠ 播放失败）');
                });
                addHistory(msg.original, msg.translated);
            } else if (msg.type === 'status' && msg.state === 'recognized') {
                setStatus('recognized', `🎯 识别到: "${msg.text}" → 翻译中...`);
            } else if (msg.type === 'pong') {
                // heartbeat
            }
        }
    };

    ws.onclose = () => {
        if (isRunning) setStatus('error', '⚠ 连接断开，点击重试');
    };

    ws.onerror = () => {
        setStatus('error', '⚠ 连接失败，检查网络');
    };

    // Audio capture
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });

    // CRITICAL: Resume AudioContext (browsers suspend it until user gesture)
    if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
    }

    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);

    source.connect(processor);
    // Do NOT connect to destination — prevents echo/feedback

    let sentChunks = 0;
    processor.onaudioprocess = (e) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        // Check if there's actual audio (not silence)
        const rms = Math.sqrt(input.reduce((sum, v) => sum + v * v, 0) / input.length);
        if (rms < 0.005) return; // Skip silence
        sentChunks++;
        const pcm = float32ToPCM16(input);
        ws.send(pcm.buffer);
    };

    isRunning = true;
    startBtn.textContent = '⏹ 停止';
    startBtn.classList.add('active');

    // Diagnostic: show audio data flow every 3s
    const diagTimer = setInterval(() => {
        if (!isRunning) { clearInterval(diagTimer); return; }
        if (sentChunks === 0) return;
        fetch('/debug/status').then(r => r.json()).then(d => {
            if (d.audio_chunks_received > 0) {
                setStatus('listening', `🎙 正在听... 发送${sentChunks}块 → 服务器收到${d.audio_chunks_received}块 → 识别${d.transcripts_detected}次`);
            }
        }).catch(() => {});
        sentChunks = 0;
    }, 3000);
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

    // Wait for audio to be playable
    await new Promise((resolve, reject) => {
        audio.oncanplaythrough = resolve;
        audio.onerror = reject;
        // Timeout after 3 seconds
        setTimeout(() => reject(new Error('Audio load timeout')), 3000);
    });

    await audio.play();
    await new Promise(resolve => { audio.onended = resolve; });
    URL.revokeObjectURL(url);
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
