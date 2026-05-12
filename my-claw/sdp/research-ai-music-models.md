# Research Prompt: AI Models for CypherClaw Musical Intelligence

CypherClaw is an AI art installation that composes and performs music in real-time through SuperCollider. It needs LLM assistance for musical decision-making: generating musical intentions, critiquing its own output, evaluating melodic fragments, and suggesting harmonic directions.

## Hardware
Dell OptiPlex 7090, 62GB RAM, NVIDIA T1000 8GB GPU, Ollama installed. Models must run locally for real-time use (1-5s response time).

## Research these categories

### 1. Music-specialized LLMs
Are there fine-tuned models for music composition, theory, or critique? Models that understand terms like "chromatic passing tone," "secondary dominant," "syncopation," "modal interchange." Check Hugging Face, Ollama library, and recent papers.

### 2. Music representation models
Models that understand ABC notation, MusicXML, MIDI token sequences, or piano roll representations. Could we feed our note sequences in a structured format and get musical analysis back?

### 3. Small but capable general models
For a T1000 8GB GPU, what's the best general-purpose model (not music-specialized) that fits in VRAM and can handle music critique prompts? Compare: Qwen 3.5 9b, Phi-4, Gemma 3 9b, Llama 3.3 8b, Mistral 7b v0.4. Which gives the most nuanced responses for creative/artistic judgment?

### 4. Audio understanding models
Are there models that can analyze audio waveforms directly? We could feed recordings of what CypherClaw played and get critique based on the actual sound, not just note data.

### 5. Multi-modal music models
Models that bridge text and music (like MusicLM, MusicGen, but for understanding/critique rather than generation).

## For each model found, report
- Name, size (GB), Ollama availability
- Whether it fits in 8GB VRAM (or needs CPU offload)
- Estimated response time on T1000
- What it's good at (theory, generation, critique, audio analysis)
- How to install/run

## Current findings
- qwen3.5:4b with think:false — 2s response, good musical vocabulary, fits in VRAM
- qwen3.5:9b — 5-10s warm, better quality, fits in VRAM
- qwen3.5:27b — available but too slow for real-time (needs CPU offload)

## Priority
We need one model running TODAY for real-time musical guidance during composition. The 4b is working but we should verify there isn't something better available.
