"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Models are served from /models/ (copied there by `npm run copy-models`).
// Override via NEXT_PUBLIC_FACEAPI_MODEL_URL for self-hosted production.
const MODEL_URL =
  process.env.NEXT_PUBLIC_FACEAPI_MODEL_URL ?? "/models";

export interface FaceVerificationConfig {
  /** How often to run a verification check (ms). Default: 20 000 */
  checkIntervalMs?: number;
  /** Euclidean distance threshold — lower = stricter. Default: 0.6 */
  similarityThreshold?: number;
  /** Consecutive mismatches before `onFlag` fires. Default: 3 */
  maxConsecutiveViolations?: number;
  /** Called on every mismatch / no-face event. */
  onViolation?: (
    type: "identity_mismatch" | "no_face_detected",
    confidenceScore: number
  ) => void;
  /** Called when consecutive violations exceed `maxConsecutiveViolations`. */
  onFlag?: () => void;
}

export interface FaceVerificationReturn {
  modelsLoading: boolean;
  modelsLoaded: boolean;
  loadModels: () => Promise<void>;
  /** Validate a file and store its descriptor as the reference. */
  setReferenceFromFile: (
    file: File
  ) => Promise<{ success: boolean; error?: string }>;
  /** Capture current video frame and store its descriptor as the reference. */
  setReferenceFromWebcam: () => Promise<{ success: boolean; error?: string }>;
  hasReference: boolean;
  startVerification: () => void;
  stopVerification: () => void;
  isActive: boolean;
  consecutiveMismatches: number;
  lastScore: number | null;
}

export function useFaceVerification(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  config: FaceVerificationConfig = {}
): FaceVerificationReturn {
  const {
    checkIntervalMs = 20_000,
    similarityThreshold = 0.6,
    maxConsecutiveViolations = 3,
    onViolation,
    onFlag,
  } = config;

  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [hasReference, setHasReference] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [consecutiveMismatches, setConsecutiveMismatches] = useState(0);
  const [lastScore, setLastScore] = useState<number | null>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const faceApiRef = useRef<any>(null);
  const descriptorRef = useRef<Float32Array | null>(null);
  const consecutiveRef = useRef(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onViolationRef = useRef(onViolation);
  const onFlagRef = useRef(onFlag);

  useEffect(() => { onViolationRef.current = onViolation; }, [onViolation]);
  useEffect(() => { onFlagRef.current = onFlag; }, [onFlag]);

  const loadModels = useCallback(async () => {
    if (modelsLoaded || modelsLoading) return;
    setModelsLoading(true);
    try {
      const faceApi = await import("@vladmandic/face-api");
      faceApiRef.current = faceApi;
      await Promise.all([
        faceApi.nets.ssdMobilenetv1.loadFromUri(MODEL_URL),
        faceApi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
        faceApi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
      ]);
      setModelsLoaded(true);
    } catch (err) {
      console.error("[FaceVerification] Model load failed:", err);
    } finally {
      setModelsLoading(false);
    }
  }, [modelsLoaded, modelsLoading]);

  // ── Extract a single face descriptor from any image-like element ──────────

  const extractDescriptor = useCallback(
    async (
      input: HTMLVideoElement | HTMLImageElement | HTMLCanvasElement
    ): Promise<Float32Array | null> => {
      const fa = faceApiRef.current;
      if (!fa || !modelsLoaded) return null;
      const det = await fa
        .detectSingleFace(input, new fa.SsdMobilenetv1Options({ minConfidence: 0.5 }))
        .withFaceLandmarks()
        .withFaceDescriptor();
      return det?.descriptor ?? null;
    },
    [modelsLoaded]
  );

  // ── Reference setters ─────────────────────────────────────────────────────

  const setReferenceFromFile = useCallback(
    async (file: File): Promise<{ success: boolean; error?: string }> => {
      const fa = faceApiRef.current;
      if (!fa || !modelsLoaded) return { success: false, error: "Models not loaded yet." };
      if (file.size > 5 * 1024 * 1024)
        return { success: false, error: "File too large (max 5 MB)." };
      if (!["image/jpeg", "image/png", "image/webp"].includes(file.type))
        return { success: false, error: "Unsupported format. Use JPG, PNG, or WebP." };

      return new Promise((resolve) => {
        const img = new Image();
        const url = URL.createObjectURL(file);
        img.onload = async () => {
          try {
            const dets = await fa
              .detectAllFaces(img, new fa.SsdMobilenetv1Options({ minConfidence: 0.5 }))
              .withFaceLandmarks()
              .withFaceDescriptors();
            URL.revokeObjectURL(url);
            if (dets.length === 0)
              return resolve({ success: false, error: "No face detected. Use a clear, front-facing photo." });
            if (dets.length > 1)
              return resolve({ success: false, error: "Multiple faces detected. Upload a solo photo." });
            descriptorRef.current = dets[0].descriptor;
            setHasReference(true);
            resolve({ success: true });
          } catch {
            URL.revokeObjectURL(url);
            resolve({ success: false, error: "Could not analyze photo." });
          }
        };
        img.onerror = () => {
          URL.revokeObjectURL(url);
          resolve({ success: false, error: "Failed to load image." });
        };
        img.src = url;
      });
    },
    [modelsLoaded]
  );

  const setReferenceFromWebcam = useCallback(async (): Promise<{
    success: boolean;
    error?: string;
  }> => {
    const video = videoRef.current;
    if (!video || video.readyState < 2)
      return { success: false, error: "Camera not ready." };
    const descriptor = await extractDescriptor(video);
    if (!descriptor)
      return { success: false, error: "No face detected. Ensure your face is clearly visible." };
    descriptorRef.current = descriptor;
    setHasReference(true);
    return { success: true };
  }, [videoRef, extractDescriptor]);

  // ── Periodic verification ─────────────────────────────────────────────────

  const runCheck = useCallback(async () => {
    const fa = faceApiRef.current;
    const video = videoRef.current;
    const ref = descriptorRef.current;
    if (!fa || !modelsLoaded || !video || !ref || video.readyState < 2) return;

    const det = await fa
      .detectSingleFace(video, new fa.SsdMobilenetv1Options({ minConfidence: 0.5 }))
      .withFaceLandmarks()
      .withFaceDescriptor();

    if (!det) {
      consecutiveRef.current += 1;
      setConsecutiveMismatches(consecutiveRef.current);
      setLastScore(0);
      onViolationRef.current?.("no_face_detected", 0);
      if (consecutiveRef.current >= maxConsecutiveViolations) onFlagRef.current?.();
      return;
    }

    const distance: number = fa.euclideanDistance(ref, det.descriptor);
    const score = Math.max(0, 1 - distance);
    setLastScore(score);

    if (distance > similarityThreshold) {
      consecutiveRef.current += 1;
      setConsecutiveMismatches(consecutiveRef.current);
      onViolationRef.current?.("identity_mismatch", score);
      if (consecutiveRef.current >= maxConsecutiveViolations) onFlagRef.current?.();
    } else {
      consecutiveRef.current = 0;
      setConsecutiveMismatches(0);
    }
  }, [modelsLoaded, videoRef, similarityThreshold, maxConsecutiveViolations]);

  const startVerification = useCallback(() => {
    if (!descriptorRef.current || !modelsLoaded) return;
    if (intervalRef.current) clearInterval(intervalRef.current);
    consecutiveRef.current = 0;
    setConsecutiveMismatches(0);
    setIsActive(true);
    // Run once immediately, then on interval
    runCheck();
    intervalRef.current = setInterval(runCheck, checkIntervalMs);
  }, [modelsLoaded, checkIntervalMs, runCheck]);

  const stopVerification = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsActive(false);
  }, []);

  useEffect(() => () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
  }, []);

  return {
    modelsLoading,
    modelsLoaded,
    loadModels,
    setReferenceFromFile,
    setReferenceFromWebcam,
    hasReference,
    startVerification,
    stopVerification,
    isActive,
    consecutiveMismatches,
    lastScore,
  };
}
