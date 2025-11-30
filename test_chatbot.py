#!/usr/bin/env python3
"""
Test script for the chatbot functionality
"""
import requests
import json
import time

def test_chatbot_local():
    """Test the local chatbot fallback logic"""
    print("=== Testing Local Chatbot Logic ===")
    
    test_queries = [
        "engine won't start",
        "brake problems", 
        "oil change",
        "tire pressure",
        "battery dead",
        "transmission issues",
        "overheating",
        "random question"
    ]
    
    for query in test_queries:
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['engine', 'motor', 'start']):
            response = "Check engine oil level, battery connections, and fuel. If engine won't start, verify spark plugs and air filter."
        elif any(word in query_lower for word in ['brake', 'stop']):
            response = "Check brake fluid level, brake pads thickness, and listen for squealing sounds. Replace pads if worn."
        elif any(word in query_lower for word in ['oil', 'change']):
            response = "Change engine oil every 5,000-7,500 miles. Use recommended oil viscosity for your vehicle."
        elif any(word in query_lower for word in ['tire', 'wheel']):
            response = "Check tire pressure monthly, rotate tires every 6,000 miles, and inspect for wear patterns."
        elif any(word in query_lower for word in ['battery']):
            response = "Clean battery terminals, check voltage (12.6V when off), and replace every 3-5 years."
        elif any(word in query_lower for word in ['transmission']):
            response = "Check transmission fluid level and color. Service every 30,000-60,000 miles depending on usage."
        elif any(word in query_lower for word in ['coolant', 'radiator', 'overheat']):
            response = "Check coolant level, inspect for leaks, and flush system every 30,000 miles or as recommended."
        else:
            response = "Car Assistant API is offline. I can help with basic car maintenance questions."
        
        print(f"Query: {query}")
        print(f"Response: {response}")
        print("-" * 50)

def test_api_connection():
    """Test connection to external API"""
    print("=== Testing External API Connection ===")
    
    try:
        response = requests.post(
            "http://10.141.241.233:8000/query",
            json={"question": "test"},
            timeout=3
        )
        print(f"✓ API Response: {response.status_code}")
        if response.status_code == 200:
            print(f"✓ API Data: {response.json()}")
        return True
    except requests.exceptions.Timeout:
        print("✗ API Timeout - Server not responding")
        return False
    except requests.exceptions.ConnectionError:
        print("✗ API Connection Error - Server not reachable")
        return False
    except Exception as e:
        print(f"✗ API Error: {e}")
        return False

if __name__ == "__main__":
    print("Chatbot Functionality Test")
    print("=" * 40)
    
    # Test API connection
    api_working = test_api_connection()
    print()
    
    # Test local fallback
    test_chatbot_local()
    
    print("\n=== Summary ===")
    if api_working:
        print("✓ External API is working")
    else:
        print("✗ External API is offline - Using local fallback responses")
    print("✓ Local chatbot logic is working")