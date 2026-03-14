import { useCallback, useRef, useState } from "react"
import { encodeWav } from "@/lib/wav"

const SILENCE_THRESHOLD = 0.015
const SILENCE_DURATION_MS = 1500
const SPEECH_CONFIRM_FRAMES = 5
const MIN_RECORD_MS = 500

export function useInterviewAudio() {
  const [level, setLevel] = useState(0)
  
  const audioCtxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const workletRef = useRef<ScriptProcessorNode | null>(null)
  const samplesRef = useRef<Float32Array[]>([])
  const silenceStartRef = useRef(0)
  const speechFramesRef = useRef(0)
  const isRecordingRef = useRef(false)
  const recordStartRef = useRef(0)
  const rafRef = useRef(0)
  const isListeningRef = useRef(false)

  const initMic = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 },
    })
    const ctx = new AudioContext({ sampleRate: 16000 })
    const source = ctx.createMediaStreamSource(stream)
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 512
    source.connect(analyser)

    const processor = ctx.createScriptProcessor(4096, 1, 1)
    source.connect(processor)
    processor.connect(ctx.destination)

    processor.onaudioprocess = (e) => {
      if (!isRecordingRef.current) return
      samplesRef.current.push(new Float32Array(e.inputBuffer.getChannelData(0)))
    }

    audioCtxRef.current = ctx
    streamRef.current = stream
    analyserRef.current = analyser
    workletRef.current = processor
  }, [])

  const cleanup = useCallback(() => {
    cancelAnimationFrame(rafRef.current)
    isListeningRef.current = false
    workletRef.current?.disconnect()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    audioCtxRef.current?.close()
    audioCtxRef.current = null
    streamRef.current = null
    analyserRef.current = null
    workletRef.current = null
  }, [])

  const startListening = useCallback(
    (onListening: () => void, onRecording: () => void, onFinish: () => void) => {
      isListeningRef.current = true
      isRecordingRef.current = false
      samplesRef.current = []
      silenceStartRef.current = 0
      speechFramesRef.current = 0
      onListening()

      const analyser = analyserRef.current
      if (!analyser) return
      const buf = new Float32Array(analyser.fftSize)

      const tick = () => {
        if (!isListeningRef.current) return
        
        analyser.getFloatTimeDomainData(buf)
        let sum = 0
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
        const rms = Math.sqrt(sum / buf.length)
        setLevel(rms)

        const now = Date.now()
        const isSpeech = rms > SILENCE_THRESHOLD

        if (!isRecordingRef.current) {
          if (isSpeech) {
            speechFramesRef.current++
            if (speechFramesRef.current >= SPEECH_CONFIRM_FRAMES) {
              isRecordingRef.current = true
              recordStartRef.current = now
              samplesRef.current = []
              onRecording()
            }
          } else {
            speechFramesRef.current = 0
          }
        } else {
          if (!isSpeech) {
            if (silenceStartRef.current === 0) silenceStartRef.current = now
            else if (
              now - silenceStartRef.current >= SILENCE_DURATION_MS &&
              now - recordStartRef.current >= MIN_RECORD_MS
            ) {
              isRecordingRef.current = false
              isListeningRef.current = false
              onFinish()
              return
            }
          } else {
            silenceStartRef.current = 0
          }
        }
        rafRef.current = requestAnimationFrame(tick)
      }
      rafRef.current = requestAnimationFrame(tick)
    },
    []
  )

  const stopListening = useCallback(() => {
    isListeningRef.current = false
    isRecordingRef.current = false
    cancelAnimationFrame(rafRef.current)
  }, [])

  const getRecordedAudio = useCallback((): Blob | null => {
    const chunks = samplesRef.current
    if (chunks.length === 0) return null

    const totalLen = chunks.reduce((a, c) => a + c.length, 0)
    const merged = new Float32Array(totalLen)
    let offset = 0
    for (const c of chunks) {
      merged.set(c, offset)
      offset += c.length
    }
    samplesRef.current = []

    const ctx = audioCtxRef.current
    return encodeWav(merged, ctx?.sampleRate ?? 16000)
  }, [])

  const playStreamingAudio = useCallback(
    (response: Response): Promise<void> => {
      return new Promise(async (resolve) => {
        const reader = response.body?.getReader()
        if (!reader) {
          resolve()
          return
        }

        const BATCH_SIZE = 25
        const audioQueue: HTMLAudioElement[] = []
        let currentAudio: HTMLAudioElement | null = null
        let streamDone = false
        let resolved = false

        const playNext = () => {
          if (resolved) return
          if (audioQueue.length === 0) {
            if (streamDone) {
              resolved = true
              resolve()
            }
            return
          }

          currentAudio = audioQueue.shift()!
          currentAudio.onended = () => {
            URL.revokeObjectURL(currentAudio!.src)
            playNext()
          }
          currentAudio.onerror = () => {
            URL.revokeObjectURL(currentAudio!.src)
            playNext()
          }
          currentAudio.play().catch(() => {
            URL.revokeObjectURL(currentAudio!.src)
            playNext()
          })
        }

        let batch: Uint8Array[] = []
        let firstBatchPlayed = false

        const flushBatch = () => {
          if (batch.length === 0) return
          const blob = new Blob(batch as BlobPart[], { type: "audio/mpeg" })
          batch = []

          const url = URL.createObjectURL(blob)
          const audio = new Audio(url)
          audio.preload = "auto"
          audio.load()

          if (!firstBatchPlayed) {
            firstBatchPlayed = true
            currentAudio = audio
            currentAudio.onended = () => {
              URL.revokeObjectURL(currentAudio!.src)
              playNext()
            }
            currentAudio.onerror = () => {
              URL.revokeObjectURL(currentAudio!.src)
              playNext()
            }
            currentAudio.play().catch(() => {
              URL.revokeObjectURL(currentAudio!.src)
              playNext()
            })
          } else {
            audioQueue.push(audio)
            if (!currentAudio || currentAudio.ended) {
              playNext()
            }
          }
        }

        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            if (value) {
              batch.push(value as Uint8Array)
              if (batch.length >= BATCH_SIZE) {
                flushBatch()
              }
            }
          }
        } catch (err) {
          console.error("Stream read error:", err)
        }

        streamDone = true
        flushBatch()

        if (!firstBatchPlayed) {
          resolved = true
          resolve()
        } else if (audioQueue.length === 0 && currentAudio && currentAudio.ended) {
          if (!resolved) {
            resolved = true
            resolve()
          }
        }
      })
    },
    []
  )

  return {
    level,
    setLevel,
    initMic,
    cleanup,
    startListening,
    stopListening,
    getRecordedAudio,
    playStreamingAudio,
  }
}
