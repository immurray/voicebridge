// VoiceBridge Frontend — Web Audio API + WebSocket

// ============ State ============
let ws = null;
let audioContext = null;
let mediaStream = null;
let sourceNode = null;
let processorNode = null;
let isMicOn = false;
let isSpeakerOn = true;
let sessionId = null;
let peerId = null;
let myLanguage = null;
let remoteLanguage = null;

// Audio config
const SAMPLE_RATE = 16000;
const CHUNK_MS = 200;          // Send audio every 200ms
const VAD_SILENCE_MS = 500;    // VAD silence threshold

// ============ Session Management ============

async function createSession() {
    const lang = document.getElementById('create-lang').value;

    try {
        const resp = await fetch('/api/session/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language: lang }),
        });
        const data = await resp.json();

        if (data.error) {
            alert('创建失败: ' + data.error);
            return;
        }

        const resultEl = document.getElementById('create-result');
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = `
            <strong>会话已创建!</strong><br>
            ID: <code>${data.session_id}</code><br>
            <a href="${data.share_link}">打开对话页面 →</a>
        `;

        // Auto-redirect to session
        window.location.href = data.share_link;
    } catch (e) {
        alert('网络错误: ' + e.message);
    }
}

async function joinSession() {
    const sessionId = document.getElementById('join-session-id').value.trim();
    const lang = document.getElementById('join-lang').value;

    if (!sessionId) {
        alert('请输入会话 ID');
        return;
    }

    try {
        const resp = await fetch(`/api/session/join/${sessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language: lang }),
        });
        const data = await resp.json();

        if (data.error) {
            alert('加入失败: ' + data.error);
            return;
        }

        window.location.href = `/session.html?sid=${sessionId}&pid=${data.peer_id}&lang=${data.language}`;
    } catch (e) {
        alert('网络错误: ' + e.message);
    }
}

// ============ Session Init ============

async function initSession(sid) {
    sessionId = sid;
    peerId = new URLSearchParams(window.location.search).get('pid') ||
              'peer_' + Math.random().toString(36).slice(2, 8);
    myLanguage = new URLSearchParams(window.location.search).get('lang') || 'zh';
    remoteLanguage = myLanguage === 'zh' ? 'en' : 'zh';

    document.getElementById('local-lang').textContent =
        myLanguage === 'zh' ? '中文' : 'English';
    document.getElementById('remote-lang').textContent =
        remoteLanguage === 'zh' ? '中文' : 'English';

    // Connect WebSocket
    await connectWebSocket();

    // Request microphone on mic button click
    document.getElementById('mic-btn').addEventListener('click', toggleMic);
}

// ============ WebSocket ============

async function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${sessionId}/${peerId}`;

    ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        setConnectionStatus(true);
        console.log('[WS] Connected');
    };

    ws.onmessage = async (event) => {
        if (event.data instanceof ArrayBuffer) {
            // Received translated audio — play it
            await playAudio(event.data);
        } else {
            // Text message (VAD events, etc.)
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'vad_event') {
                    updateRemoteSpeaking(msg.speaking);
                }
            } catch (e) { /* ignore */ }
        }
    };

    ws.onclose = () => {
        setConnectionStatus(false);
        console.log('[WS] Disconnected — reconnecting in 2s...');
        setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (e) => {
        console.error('[WS] Error:', e);
    };
}

function setConnectionStatus(connected) {
    const dot = document.getElementById('connection-status');
    if (dot) {
        dot.className = 'dot ' + (connected ? 'online' : 'offline');
    }
}

// ============ Audio Capture ============

async function startMic() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: SAMPLE_RATE,
        });
    }

    mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
            channelCount: 1,
            sampleRate: SAMPLE_RATE,
            echoCancellation: true,
            noiseSuppression: true,
        },
    });

    sourceNode = audioContext.createMediaStreamSource(mediaStream);

    // ScriptProcessor for raw PCM access
    processorNode = audioContext.createScriptProcessor(4096, 1, 1);

    let audioBuffer = [];
    let isSpeaking = false;
    let silenceTimer = null;

    processorNode.onaudioprocess = (event) => {
        if (!isMicOn || ws?.readyState !== WebSocket.OPEN) return;

        const input = event.inputBuffer.getChannelData(0);

        // Convert Float32 to Int16 PCM
        const pcmData = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
            pcmData[i] = Math.max(-32768, Math.min(32767, input[i] * 32768));
        }

        // VAD: check if audio level exceeds threshold
        const rms = Math.sqrt(pcmData.reduce((sum, v) => sum + v * v, 0) / pcmData.length);

        if (rms > 500) {  // Speech detected
            isSpeaking = true;
            updateLocalSpeaking(true);
            clearTimeout(silenceTimer);

            // Send VAD event
            ws.send(JSON.stringify({
                type: 'vad_event',
                speaking: true,
            }));
        } else if (isSpeaking) {
            // Start silence timer
            if (!silenceTimer) {
                silenceTimer = setTimeout(() => {
                    isSpeaking = false;
                    updateLocalSpeaking(false);
                    ws.send(JSON.stringify({
                        type: 'vad_event',
                        speaking: false,
                    }));
                    silenceTimer = null;
                }, VAD_SILENCE_MS);
            }
        }

        // Send audio chunk
        if (isSpeaking || audioBuffer.length > 0) {
            audioBuffer.push(...pcmData);

            // Send every CHUNK_MS worth of audio
            const samplesPerChunk = (SAMPLE_RATE * CHUNK_MS) / 1000;
            while (audioBuffer.length >= samplesPerChunk) {
                const chunk = audioBuffer.splice(0, samplesPerChunk);
                const chunkBuffer = new Int16Array(chunk).buffer;
                if (ws?.readyState === WebSocket.OPEN) {
                    ws.send(chunkBuffer);
                }
            }
        }
    };

    sourceNode.connect(processorNode);
    processorNode.connect(audioContext.destination);

    // Visualizer
    startVisualizer();

    isMicOn = true;
    document.getElementById('mic-btn').textContent = '🔴 通话中...';
    document.getElementById('mic-btn').style.background = 'var(--danger)';
}

function stopMic() {
    if (processorNode) {
        processorNode.disconnect();
        processorNode = null;
    }
    if (sourceNode) {
        sourceNode.disconnect();
        sourceNode = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    isMicOn = false;
    updateLocalSpeaking(false);
    document.getElementById('mic-btn').textContent = '🎤 开始通话';
    document.getElementById('mic-btn').style.background = 'var(--primary)';
    stopVisualizer();
}

async function toggleMic() {
    if (isMicOn) {
        stopMic();
    } else {
        try {
            await startMic();
        } catch (e) {
            alert('无法访问麦克风: ' + e.message);
        }
    }
}

// ============ Audio Playback ============

async function playAudio(audioData) {
    if (!isSpeakerOn) return;

    // audioData is raw PCM Int16 — convert to AudioBuffer and play
    const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SAMPLE_RATE });
    const pcm = new Int16Array(audioData);
    const floatData = new Float32Array(pcm.length);

    for (let i = 0; i < pcm.length; i++) {
        floatData[i] = pcm[i] / 32768;
    }

    const audioBuffer = ctx.createBuffer(1, floatData.length, SAMPLE_RATE);
    audioBuffer.getChannelData(0).set(floatData);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    source.start(0);

    // Auto-close context after playback
    source.onended = () => {
        setTimeout(() => ctx.close(), 1000);
    };
}

// ============ Visualizer ============

let visualizerInterval = null;

function startVisualizer() {
    const canvas = document.getElementById('visualizer-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    visualizerInterval = setInterval(() => {
        ctx.fillStyle = '#1a1d27';
        ctx.fillRect(0, 0, width, height);

        if (isMicOn && audioContext) {
            // Simple animated bars when mic is active
            const barCount = 20;
            const barWidth = (width / barCount) - 2;

            for (let i = 0; i < barCount; i++) {
                const barHeight = Math.random() * height * 0.8 * (isMicOn ? 1 : 0.3);
                ctx.fillStyle = '#4f8cff';
                ctx.fillRect(
                    i * (barWidth + 2),
                    height - barHeight,
                    barWidth,
                    barHeight
                );
            }
        }
    }, 100);
}

function stopVisualizer() {
    if (visualizerInterval) {
        clearInterval(visualizerInterval);
        visualizerInterval = null;
    }
}

// ============ VAD Indicators ============

function updateLocalSpeaking(speaking) {
    const el = document.getElementById('local-speaking');
    if (el) {
        el.className = 'speaking-indicator' + (speaking ? ' active' : '');
        el.textContent = speaking ? '🔊' : '🔇';
    }
}

function updateRemoteSpeaking(speaking) {
    const el = document.getElementById('remote-speaking');
    if (el) {
        el.className = 'speaking-indicator' + (speaking ? ' active' : '');
        el.textContent = speaking ? '🔊' : '🔇';
    }
}

// ============ Speaker Toggle ============

function toggleSpeaker() {
    isSpeakerOn = !isSpeakerOn;
    document.getElementById('mute-speaker-btn').textContent = isSpeakerOn ? '🔊' : '🔇';
}

// ============ Transcript ============

function addTranscript(speaker, text, originalText) {
    const container = document.getElementById('transcript');
    if (!container) return;

    // Remove empty state
    const empty = container.querySelector('.transcript-empty');
    if (empty) empty.remove();

    const entry = document.createElement('div');
    entry.className = 'transcript-entry';
    entry.innerHTML = `
        <div class="speaker">${speaker}</div>
        <div>${text}</div>
        ${originalText ? `<div class="original">原文: ${originalText}</div>` : ''}
    `;

    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}
