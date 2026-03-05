#!/usr/bin/env python3
"""Test Oracle OCI authentication and Generative AI access."""

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    CohereChatRequest,
    OnDemandServingMode,
    ChatDetails
)

print("Testing Oracle OCI connection...")
print("=" * 60)

try:
    # Load config
    config = oci.config.from_file("C:\\Users\\Sean\\.oci\\config", "DEFAULT")
    print("[OK] Config loaded")
    print(f"  User: {config['user'][:50]}...")
    print(f"  Region: {config['region']}")
    print(f"  Key file: {config['key_file']}")

    # Test authentication by listing available models
    endpoint = "https://inference.generativeai.us-phoenix-1.oci.oraclecloud.com"
    compartment_id = config["tenancy"]  # Use tenancy as compartment for free tier

    print(f"\n[*] Connecting to: {endpoint}")
    client = GenerativeAiInferenceClient(config=config, service_endpoint=endpoint)
    print("[OK] Client created")

    # Try different model IDs
    models_to_try = [
        "cohere.command-r-plus",
        "cohere.command-r",
        "cohere.command",
        "meta.llama-3-70b-instruct"
    ]

    response = None
    for model_id in models_to_try:
        try:
            print(f"\n[*] Trying model: {model_id}")
            chat_request = CohereChatRequest(
                message="Say 'hello' in one word",
                max_tokens=10,
                temperature=0.5
            )

            chat_details = ChatDetails(
                compartment_id=compartment_id,
                serving_mode=OnDemandServingMode(model_id=model_id),
                chat_request=chat_request
            )

            response = client.chat(chat_details)
            print(f"[OK] Model {model_id} works!")
            break
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                print(f"  [--] Model not found")
            else:
                print(f"  [FAIL] Error {e.status}: {e.message}")

    if not response:
        raise Exception("No working models found")

    print("[OK] SUCCESS! Oracle OCI is working!")
    print(f"\nResponse: {response.data.chat_response.text}")
    print("\n" + "=" * 60)
    print("Oracle is ready to be your primary bridge processor!")

except oci.exceptions.ServiceError as e:
    print(f"\n[FAIL] Service Error:")
    print(f"  Status: {e.status}")
    print(f"  Code: {e.code}")
    print(f"  Message: {e.message}")

except Exception as e:
    print(f"\n[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()
