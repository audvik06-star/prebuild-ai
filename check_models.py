import os
from dotenv import load_dotenv
from google import genai

# 1. Load your GEMINI_API_KEY from the .env file
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ ERROR: GEMINI_API_KEY not found in .env file!")
else:
    print("✅ API Key loaded. Fetching available Gemini models...\n")
    
    # 2. Connect to the Gemini API using the official google-genai SDK
    client = genai.Client(api_key=api_key)
    
    # 3. List all models your key can access
    for model in client.models.list():
        if "gemini" in model.name.lower():
            print(model.name)