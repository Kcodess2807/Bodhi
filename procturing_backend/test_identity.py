"""
test_identity.py

  1. Prompts you to enter the path to your reference photo
  2. Opens live webcam feed
  3. Every 3 seconds compares live frame against reference
  4. Shows result overlaid on the camera window

Usage:
    python test_identity.py
    # or pass photo directly:
    python test_identity.py --photo /path/to/photo.jpg
"""

import cv2
import numpy as np
import time
import threading
import argparse
import os
from deepface import DeepFace


# ── Config ────────────────────────────────────────────────────────────────────
MODEL_NAME      = "Facenet512"
THRESHOLD       = 0.40
VERIFY_INTERVAL = 3
CAMERA_INDEX    = 0


# ── Shared state ──────────────────────────────────────────────────────────────
class State:
    def __init__(self):
        self.verified    = None
        self.distance    = None
        self.confidence  = None
        self.error       = None
        self.last_check  = 0.0
        self.is_checking = False
        self.lock        = threading.Lock()

state = State()


# ── Ask for photo path in terminal ────────────────────────────────────────────

def get_reference_photo() -> np.ndarray:
    while True:
        print("\nEnter the full path to your reference photo:")
        print("(tip: drag and drop the file into this terminal to get the path)")
        path = input(">>> ").strip().strip("'\"")  # strip quotes if dragged in

        if not path:
            print("No path entered. Try again.")
            continue

        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue

        image = cv2.imread(path)
        if image is None:
            print(f"Could not decode image: {path}")
            continue

        print(f"Loaded: {path}  ({image.shape[1]}x{image.shape[0]}px)")
        return image


# ── Background verification ───────────────────────────────────────────────────

def run_verify(reference: np.ndarray, live: np.ndarray):
    with state.lock:
        state.is_checking = True

    try:
        result = DeepFace.verify(
            img1_path=reference,
            img2_path=live,
            model_name=MODEL_NAME,
            detector_backend="opencv",
            enforce_detection=False,
            align=True,
        )
        distance   = float(result["distance"])
        verified   = distance <= THRESHOLD
        confidence = max(0.0, min(1.0, 1.0 - (distance / (THRESHOLD * 2))))

        with state.lock:
            state.verified   = verified
            state.distance   = round(distance, 4)
            state.confidence = round(confidence, 3)
            state.error      = None

    except Exception as e:
        with state.lock:
            state.verified = False
            state.error    = str(e)[:80]
    finally:
        with state.lock:
            state.is_checking = False
            state.last_check  = time.time()


# ── Overlay ───────────────────────────────────────────────────────────────────

def draw_overlay(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]

    GREEN  = (0, 200, 0)
    RED    = (0, 0, 220)
    YELLOW = (0, 200, 220)
    WHITE  = (255, 255, 255)
    BLACK  = (0, 0, 0)
    GREY   = (150, 150, 150)

    cv2.rectangle(frame, (0, 0), (w, 40), BLACK, -1)
    cv2.putText(frame, f"Model: {MODEL_NAME}   Threshold: {THRESHOLD}   Press Q to quit",
                (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1)

    with state.lock:
        verified   = state.verified
        distance   = state.distance
        confidence = state.confidence
        error      = state.error
        checking   = state.is_checking
        last_check = state.last_check

    cv2.rectangle(frame, (0, h - 100), (w, h), BLACK, -1)

    if checking:
        cv2.putText(frame, "Verifying...",
                    (10, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, YELLOW, 2)

    elif verified is None:
        cv2.putText(frame, "Waiting for first check...",
                    (10, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.75, GREY, 1)

    elif error:
        cv2.putText(frame, f"Error: {error}",
                    (10, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, RED, 1)

    else:
        color = GREEN if verified else RED
        label = "VERIFIED  Same Person" if verified else "FAILED  Different Person"
        cv2.putText(frame, label,
                    (10, h - 65), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        cv2.putText(frame, f"Distance: {distance}    Confidence: {confidence}",
                    (10, h - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.58, WHITE, 1)

        elapsed    = time.time() - last_check
        next_check = max(0, VERIFY_INTERVAL - elapsed)
        cv2.putText(frame, f"Next check in {next_check:.1f}s",
                    (10, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.48, GREY, 1)

        progress = min(1.0, elapsed / VERIFY_INTERVAL)
        cv2.rectangle(frame, (0, h - 102), (int(w * progress), h - 98), YELLOW, -1)

    return frame


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global THRESHOLD, VERIFY_INTERVAL

    parser = argparse.ArgumentParser()
    parser.add_argument("--photo", help="Path to reference photo (skips the prompt)")
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--interval",  type=int,   default=VERIFY_INTERVAL)
    args = parser.parse_args()

    THRESHOLD       = args.threshold
    VERIFY_INTERVAL = args.interval

    print("=" * 50)
    print("  Identity Verification Test")
    print("=" * 50)

    # Get reference photo — either from arg or prompt
    if args.photo:
        reference = cv2.imread(args.photo)
        if reference is None:
            print(f"Could not load: {args.photo}")
            return
        print(f"Reference photo: {args.photo}")
    else:
        reference = get_reference_photo()
        if reference is None:
            return

    # Warm up model
    print(f"\nLoading {MODEL_NAME} model (first run ~10s)...")
    try:
        DeepFace.represent(img_path=reference, model_name=MODEL_NAME, enforce_detection=False)
        print("Model ready.\n")
    except Exception as e:
        print(f"Note: {e}\n")

    # Open webcam
    print("Opening webcam...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("Could not open webcam.")
        return

    for _ in range(5):
        cap.read()

    print(f"Webcam ready. Comparing every {VERIFY_INTERVAL}s — press Q in window to quit.\n")

    # Live loop
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        with state.lock:
            since_last = time.time() - state.last_check
            checking   = state.is_checking

        if since_last >= VERIFY_INTERVAL and not checking:
            threading.Thread(
                target=run_verify,
                args=(reference, frame.copy()),
                daemon=True,
            ).start()

        cv2.imshow("Identity Verification", draw_overlay(frame.copy()))

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    with state.lock:
        if state.distance is not None:
            print(f"\nLast result  : {'Verified' if state.verified else 'Failed'}")
            print(f"Last distance: {state.distance}")
            print(f"Threshold    : {THRESHOLD}")
            print("\nTip: adjust THRESHOLD at top of script based on distances you observe.")


if __name__ == "__main__":
    main()