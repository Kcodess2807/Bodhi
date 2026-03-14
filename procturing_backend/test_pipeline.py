"""
test_pipeline.py

Simulates the frontend WebSocket flow:
  1. Captures a reference photo from your webcam
  2. Connects to the proctoring WebSocket
  3. Enrolls the reference image
  4. Sends live frames every 3 seconds
  5. Prints all responses (violations, analysis, etc.)
  6. Shows a live camera window with violation overlays

Run this while the FastAPI server is running:
  Terminal 1: uvicorn main:app --reload
  Terminal 2: python test_pipeline.py

Requirements: server must be running on localhost:8000
"""

import asyncio
import websockets
import cv2
import base64
import json
import uuid
import time
import threading
from datetime import datetime


# ── Config ────────────────────────────────────────────────────────────────────
SERVER_URL = "ws://localhost:8000/proctoring/ws"
SESSION_ID = f"test-session-{uuid.uuid4().hex[:8]}"
CANDIDATE_ID = f"test-candidate-{uuid.uuid4().hex[:8]}"
FRAME_INTERVAL = 3
TEST_DURATION = 60
CAMERA_INDEX = 0

# ── Shared state between camera thread and websocket ─────────────────────────
latest_violations = []
latest_analysis = {}
session_flagged = False
violations_lock = threading.Lock()


# ── Camera window (runs in a separate thread) ─────────────────────────────────

def run_camera_window(cap: cv2.VideoCapture, stop_event: threading.Event):
    """
    Runs in a background thread.
    Shows a live camera feed with real-time violation overlays.
    """
    # Colors (BGR)
    GREEN  = (0, 220, 0)
    RED    = (0, 0, 220)
    YELLOW = (0, 200, 220)
    WHITE  = (255, 255, 255)
    BLACK  = (0, 0, 0)
    ORANGE = (0, 140, 255)

    severity_colors = {
        "high":   RED,
        "medium": ORANGE,
        "low":    YELLOW,
    }

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]

        # ── Dark overlay bar at top ───────────────────────────
        cv2.rectangle(frame, (0, 0), (w, 40), BLACK, -1)
        cv2.putText(frame, f"PROCTORING ACTIVE  |  Session: {SESSION_ID}",
                    (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1)

        # ── Analysis overlay (bottom left) ────────────────────
        with violations_lock:
            analysis = latest_analysis.copy()
            violations = latest_violations.copy()
            flagged = session_flagged

        if analysis:
            face = analysis.get("face", {})
            gaze = analysis.get("gaze", {})

            # Face status
            face_color = GREEN if face.get("has_face") and face.get("is_centered") else RED
            face_text = f"Face: {'OK' if face.get('has_face') else 'NOT DETECTED'}  Count: {face.get('face_count', 0)}"
            cv2.putText(frame, face_text, (10, h - 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, face_color, 1)

            # Gaze status
            gaze_color = GREEN if gaze.get("is_looking_at_screen") else YELLOW
            gaze_text = f"Gaze: {gaze.get('gaze_direction', 'unknown').upper()}  Attention: {gaze.get('attention_score', 0):.2f}"
            cv2.putText(frame, gaze_text, (10, h - 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, gaze_color, 1)

            # Head pose
            pose = gaze.get("head_pose")
            if pose:
                pose_text = f"Pose  P:{pose[0]:.1f}  Y:{pose[1]:.1f}  R:{pose[2]:.1f}"
                cv2.putText(frame, pose_text, (10, h - 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)

        # ── Violation banners ─────────────────────────────────
        if violations:
            for i, v in enumerate(violations[:3]):   # Show max 3 at once
                severity = v.get("severity", "low")
                color = severity_colors.get(severity, YELLOW)
                msg = v.get("message", "")
                banner_y = 55 + i * 35

                # Semi-transparent banner background
                overlay = frame.copy()
                cv2.rectangle(overlay, (0, banner_y - 20), (w, banner_y + 12), color, -1)
                cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

                cv2.putText(frame, f"⚠  [{severity.upper()}] {msg}",
                            (10, banner_y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, BLACK, 1)

        # ── Session flagged warning ───────────────────────────
        if flagged:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), RED, -1)
            cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
            cv2.putText(frame, "SESSION FLAGGED FOR REVIEW",
                        (w // 2 - 170, h // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.9, RED, 2)

        # ── Frame send indicator (top right) ──────────────────
        ts = datetime.now().strftime("%H:%M:%S")
        cv2.putText(frame, ts, (w - 90, 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1)

        cv2.imshow("Proctoring Monitor", frame)

        # Press Q to quit early
        if cv2.waitKey(1) & 0xFF == ord('q'):
            stop_event.set()
            break

    cv2.destroyAllWindows()


# ── Helpers ───────────────────────────────────────────────────────────────────

def capture_frame(cap: cv2.VideoCapture) -> str:
    ret, frame = cap.read()
    if not ret:
        raise RuntimeError("Failed to capture frame from webcam.")
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buffer).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def print_response(response: dict):
    msg_type = response.get("type", "unknown")
    ts = datetime.now().strftime("%H:%M:%S")

    print(f"\n[{ts}] ← {msg_type.upper()}")

    if msg_type == "enrolled":
        success = response.get("success")
        msg = response.get("message")
        print(f"  {'✅' if success else '❌'} {msg}")

    elif msg_type == "frame_result":
        global session_flagged
        frame_id = response.get("frame_id")
        has_violations = response.get("has_violations")
        processing_time = response.get("processing_time_ms")
        violations = response.get("violations", [])
        analysis = response.get("analysis", {})

        print(f"  Frame: {frame_id}  |  {processing_time}ms  |  Violations: {'⚠️  YES' if has_violations else '✅ NO'}")

        if violations:
            for v in violations:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(v["severity"], "⚪")
                print(f"    {icon} [{v['severity'].upper()}] {v['violation_type']}: {v['message']}")

        if analysis and not analysis.get("error"):
            face = analysis.get("face", {})
            gaze = analysis.get("gaze", {})
            print(f"  Face: has={face.get('has_face')} centered={face.get('is_centered')} conf={face.get('confidence')}")
            print(f"  Gaze: screen={gaze.get('is_looking_at_screen')} dir={gaze.get('gaze_direction')} attn={gaze.get('attention_score')}")

        # Update shared state for camera overlay
        with violations_lock:
            latest_violations.clear()
            latest_violations.extend(violations)
            latest_analysis.update(analysis or {})
            if response.get("session_flagged"):
                session_flagged = True

    elif msg_type == "session_flagged":
        print(f"  🚨 SESSION FLAGGED")

    elif msg_type == "session_summary":
        summary = response.get("summary", {})
        print(f"\n{'='*60}")
        print(f"  FINAL SUMMARY")
        print(f"  Total violations : {summary.get('total_violations')}")
        print(f"  Breakdown        : {summary.get('violation_breakdown')}")
        print(f"  Flagged          : {summary.get('is_flagged')}")
        print(f"{'='*60}")

    elif msg_type == "error":
        print(f"  ❌ ERROR: {response.get('message')}")


# ── Main test flow ────────────────────────────────────────────────────────────

async def run_test():
    print("=" * 60)
    print("  Proctoring Pipeline Test")
    print("=" * 60)
    print(f"  Session  : {SESSION_ID}")
    print(f"  Candidate: {CANDIDATE_ID}")
    print(f"  Duration : {TEST_DURATION}s  |  Frame interval: {FRAME_INTERVAL}s")
    print("=" * 60)

    print("\n📷 Opening webcam...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("❌ Could not open webcam.")
        return

    for _ in range(10):
        cap.read()
    time.sleep(1)
    print("   Webcam ready.")

    # Start camera window in background thread
    stop_event = threading.Event()
    camera_thread = threading.Thread(
        target=run_camera_window, args=(cap, stop_event), daemon=True
    )
    camera_thread.start()
    print("   Camera window opened. Press Q in the window to quit early.\n")

    print("📸 Capturing reference photo (look at the camera)...")
    time.sleep(1)
    reference_image_b64 = capture_frame(cap)
    print("   Reference photo captured.\n")

    ws_url = f"{SERVER_URL}/{SESSION_ID}"
    print(f"🔌 Connecting to {ws_url}...")

    try:
        async with websockets.connect(ws_url) as ws:
            print("   Connected.\n")

            # Enroll
            print("📤 Enrolling reference image...")
            await ws.send(json.dumps({
                "type": "enroll",
                "session_id": SESSION_ID,
                "candidate_id": CANDIDATE_ID,
                "image": reference_image_b64,
            }))

            enroll_resp = json.loads(await ws.recv())
            print_response(enroll_resp)

            if not enroll_resp.get("success"):
                print("\n❌ Enrollment failed.")
                stop_event.set()
                cap.release()
                return

            print(f"\n🎬 Sending frames for {TEST_DURATION}s...")
            print("   Try: looking away, picking up your phone, covering your face...")
            print("-" * 60)

            start_time = time.time()
            frame_count = 0

            async def send_frames():
                nonlocal frame_count
                while time.time() - start_time < TEST_DURATION and not stop_event.is_set():
                    frame_count += 1
                    fid = f"frame-{frame_count}"
                    fb64 = capture_frame(cap)
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] → FRAME #{frame_count}")
                    await ws.send(json.dumps({
                        "type": "frame",
                        "frame_id": fid,
                        "frame": fb64,
                    }))
                    await asyncio.sleep(FRAME_INTERVAL)

                await ws.send(json.dumps({"type": "end_session"}))

            async def receive_messages():
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=FRAME_INTERVAL + 10)
                        response = json.loads(raw)
                        print_response(response)
                        if response.get("type") == "session_summary":
                            break
                    except asyncio.TimeoutError:
                        print("\n⏱  Timeout waiting for response.")
                        break
                    except websockets.exceptions.ConnectionClosed:
                        break

            await asyncio.gather(send_frames(), receive_messages())

            print(f"\n✅ Test complete. {frame_count} frames sent.")

    except ConnectionRefusedError:
        print("❌ Cannot connect. Is the server running?")
        print("   Run: uvicorn main:app --reload")

    finally:
        stop_event.set()
        camera_thread.join(timeout=2)
        cap.release()
        print("📷 Webcam released.")


if __name__ == "__main__":
    asyncio.run(run_test())

