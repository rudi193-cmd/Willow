#!/usr/bin/env python3
"""Test Oracle OCI with actual available models (Gemini/Grok)."""

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    ChatDetails,
    OnDemandServingMode,
    GenericChatRequest,
    CohereMessage,
    ChatContent
)

print("Testing Oracle OCI with real models...")
print("=" * 60)

try:
    # Load config
    config = oci.config.from_file("C:\\Users\\Sean\\.oci\\config", "DEFAULT")
    print("[OK] Config loaded")

    # Setup client
    endpoint = "https://inference.generativeai.us-phoenix-1.oci.oraclecloud.com"
    compartment_id = config["tenancy"]

    client = GenerativeAiInferenceClient(config=config, service_endpoint=endpoint)
    print("[OK] Client created")

    # Try Gemini model
    model_id = "google.gemini-2.5-flash"
    print(f"\n[*] Testing model: {model_id}")

    # For non-Cohere models, use GenericChatRequest
    chat_request = GenericChatRequest(
        messages=[{
            "role": "user",
            "content": "Say 'hello' in one word"
        }],
        max_tokens=10,
        temperature=0.5
    )

    chat_details = ChatDetails(
        compartment_id=compartment_id,
        serving_mode=OnDemandServingMode(model_id=model_id),
        chat_request=chat_request
    )

    response = client.chat(chat_details)

    print("[OK] SUCCESS! Oracle OCI Gemini is working!")
    print(f"\nResponse: {response.data.chat_response.text}")
    print("\n" + "=" * 60)
    print("Oracle Gemini ready for bridge ring processing!")
    print("No rate limits, no local CPU usage!")

except Exception as e:
    print(f"\n[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()
