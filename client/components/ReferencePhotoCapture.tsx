"use client";

import { useRef, useState } from "react";

interface ReferencePhotoCaptureProps {
  /** Called when a valid reference is set. Passes base64 JPEG (no prefix) for backend enrollment. */
  onReady: (imageB64: string) => void;
  /** Whether face-api.js models are still loading */
  modelsLoading: boolean;
  modelsLoaded: boolean;
  /** Validates an uploaded file and sets the internal descriptor */
  setReferenceFromFile: (file: File) => Promise<{ success: boolean; error?: string }>;
  /** Captures from the live video and sets the internal descriptor */
  setReferenceFromWebcam: () => Promise<{ success: boolean; error?: string }>;
  /** Ref to the live camera video element (already initialized) */
  videoRef: React.RefObject<HTMLVideoElement | null>;
}

export function ReferencePhotoCapture({
  onReady,
  modelsLoading,
  modelsLoaded,
  setReferenceFromFile,
  setReferenceFromWebcam,
  videoRef,
}: ReferencePhotoCaptureProps) {
  const [tab, setTab] = useState<"upload" | "camera">("camera");
  const [status, setStatus] = useState<"idle" | "processing" | "ok" | "error">("idle");
  const [message, setMessage] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement>(null);

  const extractBase64FromVideo = (): string | null => {
    const video = videoRef.current;
    const canvas = captureCanvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0);
    return canvas.toDataURL("image/jpeg", 0.9).split(",")[1];
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("processing");
    setMessage("Detecting face…");

    const result = await setReferenceFromFile(file);
    if (!result.success) {
      setStatus("error");
      setMessage(result.error ?? "Unknown error.");
      return;
    }

    // Also extract base64 for backend DeepFace enrollment
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = (reader.result as string).split(",")[1];
      setStatus("ok");
      setMessage("Face detected — reference set.");
      onReady(b64);
    };
    reader.readAsDataURL(file);
  };

  const handleCapture = async () => {
    setStatus("processing");
    setMessage("Detecting face…");

    const result = await setReferenceFromWebcam();
    if (!result.success) {
      setStatus("error");
      setMessage(result.error ?? "Unknown error.");
      return;
    }

    const b64 = extractBase64FromVideo();
    if (!b64) {
      setStatus("error");
      setMessage("Could not read frame from camera.");
      return;
    }

    setStatus("ok");
    setMessage("Face detected — reference set.");
    onReady(b64);
  };

  const inputCls =
    "rounded border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm w-full";

  const busy = modelsLoading || status === "processing";

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4 space-y-3">
      {/* Hidden canvas for frame extraction */}
      <canvas ref={captureCanvasRef} className="hidden" />

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-200">Reference Photo</h3>
        {modelsLoading && (
          <span className="text-[10px] text-zinc-500 animate-pulse">
            Loading face models…
          </span>
        )}
        {modelsLoaded && status !== "ok" && (
          <span className="text-[10px] text-green-500">Models ready</span>
        )}
        {status === "ok" && (
          <span className="text-[10px] text-green-400">✓ Reference set</span>
        )}
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 rounded border border-[var(--border)] p-0.5 text-xs">
        {(["camera", "upload"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => { setTab(t); setStatus("idle"); setMessage(""); }}
            className={`flex-1 rounded py-1 transition ${
              tab === t
                ? "bg-white text-black font-medium"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            {t === "camera" ? "Use Camera" : "Upload Photo"}
          </button>
        ))}
      </div>

      {tab === "camera" && (
        <div className="space-y-2">
          <p className="text-xs text-zinc-500">
            Look directly at the camera, then click Capture.
          </p>
          <button
            type="button"
            onClick={handleCapture}
            disabled={busy || !modelsLoaded}
            className="w-full rounded border border-[var(--border)] py-2 text-xs font-medium text-zinc-200 transition hover:bg-white hover:text-black disabled:opacity-40"
          >
            {status === "processing" ? "Detecting…" : "Capture Reference Photo"}
          </button>
        </div>
      )}

      {tab === "upload" && (
        <div className="space-y-2">
          <p className="text-xs text-zinc-500">
            Upload a clear, front-facing photo (JPG / PNG, max 5 MB).
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleFileChange}
            disabled={busy || !modelsLoaded}
            className={`${inputCls} file:mr-3 file:rounded file:border-0 file:bg-white file:px-2 file:py-1 file:text-xs file:font-medium file:text-black hover:file:bg-zinc-200 disabled:opacity-40`}
          />
        </div>
      )}

      {/* Status feedback */}
      {message && (
        <p
          className={`text-xs ${
            status === "ok"
              ? "text-green-400"
              : status === "error"
              ? "text-red-400"
              : "text-zinc-400 animate-pulse"
          }`}
        >
          {message}
        </p>
      )}

      {status !== "ok" && (
        <p className="text-[10px] text-zinc-600 leading-relaxed">
          Only one face must be visible. The photo is analyzed locally — no image
          data is stored permanently.
        </p>
      )}
    </div>
  );
}
