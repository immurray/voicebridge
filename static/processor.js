// VoiceBridge AudioWorklet Processor
// Runs in dedicated audio thread — zero main-thread jank
class VoiceProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = new Int16Array(4096);  // Accumulate 4096 samples = 256ms @ 16kHz
        this.bufferIdx = 0;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        const channel = input[0];  // Channel 0, Float32Array, usually 128 samples

        if (!channel || channel.length === 0) return true;

        // Float32 → Int16 PCM, accumulate
        for (let i = 0; i < channel.length; i++) {
            const s = Math.max(-1, Math.min(1, channel[i]));
            const sample = s < 0 ? s * 0x8000 : s * 0x7FFF;
            this.buffer[this.bufferIdx++] = sample;

            if (this.bufferIdx >= this.buffer.length) {
                // Flush to main thread
                const chunk = new Uint8Array(this.buffer.buffer.slice(0, this.bufferIdx * 2));
                this.port.postMessage(chunk.buffer, [chunk.buffer]);
                this.bufferIdx = 0;
            }
        }

        // Output silence (user hears translated audio separately, via WebSocket → playAudio)

        return true;  // Keep processor alive
    }
}

registerProcessor('voice-processor', VoiceProcessor);
