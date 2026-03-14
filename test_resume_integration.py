#!/usr/bin/env python3
"""Test script for resume-based interview integration."""

import requests
import json
import os

BASE_URL = os.getenv("API_URL", "http://localhost:8000")

def test_resume_upload():
    """Test resume upload endpoint."""
    print("Testing resume upload...")
    
    # Create a simple test resume file
    test_resume = """
    John Doe
    john.doe@example.com | +1-234-567-8900
    
    SUMMARY
    Experienced Software Engineer with 5 years in full-stack development.
    
    SKILLS
    Python, JavaScript, React, Node.js, PostgreSQL, Docker
    
    EXPERIENCE
    Senior Software Engineer | Tech Corp | 2021-Present
    - Led development of microservices architecture
    - Improved system performance by 40%
    
    Software Engineer | StartupXYZ | 2019-2021
    - Built RESTful APIs using Python and FastAPI
    - Implemented CI/CD pipelines
    
    EDUCATION
    B.S. Computer Science | University of Technology | 2019
    
    PROJECTS
    E-commerce Platform
    Built a scalable e-commerce platform using React and Node.js
    Technologies: React, Node.js, MongoDB, Redis
    """
    
    # Save to temp file
    with open("/tmp/test_resume.txt", "w") as f:
        f.write(test_resume)
    
    # Upload
    with open("/tmp/test_resume.txt", "rb") as f:
        files = {"file": ("resume.txt", f, "text/plain")}
        response = requests.post(f"{BASE_URL}/api/resumes/upload", files=files)
    
    if response.status_code == 201:
        data = response.json()
        print(f"✓ Resume uploaded successfully")
        print(f"  User ID: {data['user_id']}")
        print(f"  Name: {data['profile']['name']}")
        print(f"  Skills: {', '.join(data['profile']['skills'][:5])}")
        return data['user_id']
    else:
        print(f"✗ Upload failed: {response.status_code}")
        print(f"  {response.text}")
        return None

def test_get_profile(user_id):
    """Test getting a profile."""
    print(f"\nTesting profile retrieval for {user_id}...")
    
    response = requests.get(f"{BASE_URL}/api/resumes/{user_id}")
    
    if response.status_code == 200:
        profile = response.json()
        print(f"✓ Profile retrieved successfully")
        print(f"  Name: {profile['name']}")
        print(f"  Experience entries: {len(profile['experience'])}")
        return True
    else:
        print(f"✗ Retrieval failed: {response.status_code}")
        return False

def test_option_a_interview(user_id):
    """Test option_a (resume-based) interview."""
    print(f"\nTesting option_a interview for {user_id}...")
    
    payload = {
        "mode": "option_a",
        "user_id": user_id,
        "candidate_name": "John Doe",
        "company": "TechCorp",
        "role": "Software Engineer"
    }
    
    response = requests.post(f"{BASE_URL}/api/interviews", json=payload)
    
    if response.status_code == 201:
        data = response.json()
        print(f"✓ Interview started successfully")
        print(f"  Session ID: {data['session_id']}")
        print(f"  Greeting: {data['greeting_text'][:100]}...")
        return data['session_id']
    else:
        print(f"✗ Interview start failed: {response.status_code}")
        print(f"  {response.text}")
        return None

def test_option_b_interview(user_id):
    """Test option_b (JD-targeted) interview."""
    print(f"\nTesting option_b interview for {user_id}...")
    
    jd_text = """
    Senior Software Engineer - Backend
    
    We are looking for an experienced backend engineer to join our team.
    
    Requirements:
    - 5+ years of Python development
    - Experience with microservices architecture
    - Strong knowledge of PostgreSQL and Redis
    - Experience with Docker and Kubernetes
    - Excellent problem-solving skills
    
    Nice to have:
    - Experience with GraphQL
    - Knowledge of AWS services
    - Contributions to open source
    """
    
    payload = {
        "mode": "option_b",
        "user_id": user_id,
        "jd_text": jd_text,
        "candidate_name": "John Doe",
        "company": "TechCorp",
        "role": "Senior Software Engineer"
    }
    
    response = requests.post(f"{BASE_URL}/api/interviews", json=payload)
    
    if response.status_code == 201:
        data = response.json()
        print(f"✓ JD-targeted interview started successfully")
        print(f"  Session ID: {data['session_id']}")
        print(f"  Greeting: {data['greeting_text'][:100]}...")
        return data['session_id']
    else:
        print(f"✗ Interview start failed: {response.status_code}")
        print(f"  {response.text}")
        return None

def main():
    print("=" * 60)
    print("Resume-Based Interview Integration Test")
    print("=" * 60)
    
    # Test 1: Upload resume
    user_id = test_resume_upload()
    if not user_id:
        print("\n✗ Test suite failed at resume upload")
        return
    
    # Test 2: Get profile
    if not test_get_profile(user_id):
        print("\n✗ Test suite failed at profile retrieval")
        return
    
    # Test 3: Option A interview
    session_a = test_option_a_interview(user_id)
    if not session_a:
        print("\n✗ Test suite failed at option_a interview")
        return
    
    # Test 4: Option B interview
    session_b = test_option_b_interview(user_id)
    if not session_b:
        print("\n✗ Test suite failed at option_b interview")
        return
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    print(f"\nTest Results:")
    print(f"  User ID: {user_id}")
    print(f"  Option A Session: {session_a}")
    print(f"  Option B Session: {session_b}")

if __name__ == "__main__":
    main()
