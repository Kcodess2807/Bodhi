"""
Test script for Bodhi Proctoring API endpoints.

Usage:
    python test_proctoring.py

Make sure the Bodhi API server is running:
    uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
"""

import requests
import json
import base64
import cv2
import numpy as np
from pathlib import Path
import time

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api"


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_response(response: requests.Response):
    """Pretty print API response."""
    print(f"Status: {response.status_code}")
    try:
        data = response.json()
        print(json.dumps(data, indent=2))
    except:
        print(response.text)
    print()


def create_test_image(text: str = "TEST", size: tuple = (640, 480)) -> np.ndarray:
    """Create a simple test image with text."""
    img = np.ones((size[1], size[0], 3), dtype=np.uint8) * 200
    cv2.putText(img, text, (50, size[1]//2), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
    return img


def image_to_base64(image: np.ndarray) -> str:
    """Convert numpy image to base64 string."""
    _, buffer = cv2.imencode('.jpg', image)
    return base64.b64encode(buffer).decode('utf-8')


def test_health_check():
    """Test 1: Health check endpoint."""
    print_section("Test 1: Health Check")
    
    response = requests.get(f"{API_BASE}/health")
    print_response(response)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("proctoring_enabled"):
            print("✓ Proctoring is enabled and ready")
        else:
            print("⚠ Proctoring models not loaded - check server logs")
    
    return response.status_code == 200


def test_enroll_photo():
    """Test 2: Enroll a reference photo."""
    print_section("Test 2: Enroll Reference Photo")
    
    # Create a test image
    test_img = create_test_image("REFERENCE", (640, 480))
    
    # Save to temporary file
    temp_path = Path("temp_reference.jpg")
    cv2.imwrite(str(temp_path), test_img)
    
    try:
        with open(temp_path, 'rb') as f:
            files = {'file': ('reference.jpg', f, 'image/jpeg')}
            data = {'candidate_id': 'test-candidate-001'}
            
            response = requests.post(
                f"{API_BASE}/proctoring/enroll-photo",
                files=files,
                data=data
            )
            
        print_response(response)
        
        if response.status_code == 200:
            result = response.json()
            candidate_id = result.get('candidate_id')
            print(f"✓ Photo enrolled successfully")
            print(f"  Candidate ID: {candidate_id}")
            return candidate_id
        else:
            print("✗ Enrollment failed")
            return None
            
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_verify_photo(candidate_id: str):
    """Test 3: Verify a live photo against reference."""
    print_section("Test 3: Verify Live Photo")
    
    if not candidate_id:
        print("⚠ Skipping - no candidate_id from enrollment")
        return
    
    # Create a slightly different test image
    test_img = create_test_image("LIVE", (640, 480))
    
    # Save to temporary file
    temp_path = Path("temp_live.jpg")
    cv2.imwrite(str(temp_path), test_img)
    
    try:
        with open(temp_path, 'rb') as f:
            files = {'file': ('live.jpg', f, 'image/jpeg')}
            data = {'candidate_id': candidate_id}
            
            response = requests.post(
                f"{API_BASE}/proctoring/verify-photo",
                files=files,
                data=data
            )
            
        print_response(response)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Verification complete")
            print(f"  Verified: {result.get('verified')}")
            print(f"  Confidence: {result.get('confidence')}")
            print(f"  Distance: {result.get('distance')}")
            
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_list_enrolled():
    """Test 4: List enrolled candidates."""
    print_section("Test 4: List Enrolled Candidates")
    
    response = requests.get(f"{API_BASE}/proctoring/enrolled-candidates")
    print_response(response)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Found {result.get('count')} enrolled candidate(s)")


def test_active_sessions():
    """Test 5: Get active proctoring sessions."""
    print_section("Test 5: Active Proctoring Sessions")
    
    response = requests.get(f"{API_BASE}/proctoring/active-sessions")
    print_response(response)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Found {result.get('active_session_count')} active session(s)")


def test_websocket_info():
    """Test 6: Display WebSocket connection info."""
    print_section("Test 6: WebSocket Connection Info")
    
    print("To test the WebSocket proctoring pipeline:")
    print()
    print("1. Use a WebSocket client (e.g., wscat, Postman, or custom frontend)")
    print(f"2. Connect to: ws://localhost:8000/api/proctoring/ws/{{session_id}}")
    print()
    print("3. Send enroll message:")
    print(json.dumps({
        "type": "enroll",
        "candidate_id": "test-candidate-001",
        "image": "<base64_encoded_image>"
    }, indent=2))
    print()
    print("4. Send frame messages:")
    print(json.dumps({
        "type": "frame",
        "frame_id": "frame_001",
        "frame": "<base64_encoded_frame>"
    }, indent=2))
    print()
    print("5. Send client violations:")
    print(json.dumps({
        "type": "client_violation",
        "violation_type": "tab_switch"
    }, indent=2))
    print()
    print("6. End session:")
    print(json.dumps({"type": "end_session"}, indent=2))
    print()


def test_cleanup(candidate_id: str):
    """Test 7: Clean up test data."""
    print_section("Test 7: Cleanup")
    
    if not candidate_id:
        print("⚠ No candidate to clean up")
        return
    
    response = requests.delete(
        f"{API_BASE}/proctoring/enrolled-candidates/{candidate_id}"
    )
    print_response(response)
    
    if response.status_code == 200:
        print(f"✓ Candidate {candidate_id} removed")


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("  BODHI PROCTORING API TEST SUITE")
    print("=" * 80)
    print()
    print("Make sure the Bodhi API server is running:")
    print("  uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000")
    print()
    input("Press Enter to start tests...")
    
    candidate_id = None
    
    try:
        # Run tests
        if test_health_check():
            candidate_id = test_enroll_photo()
            time.sleep(1)
            
            test_verify_photo(candidate_id)
            time.sleep(1)
            
            test_list_enrolled()
            time.sleep(1)
            
            test_active_sessions()
            time.sleep(1)
            
            test_websocket_info()
            
    finally:
        # Cleanup
        if candidate_id:
            test_cleanup(candidate_id)
    
    print_section("Test Suite Complete")
    print("✓ All REST endpoint tests completed")
    print()
    print("Next steps:")
    print("  1. Test WebSocket connection with a client")
    print("  2. Integrate proctoring with interview sessions")
    print("  3. Build frontend UI for proctoring")
    print()


if __name__ == "__main__":
    main()
