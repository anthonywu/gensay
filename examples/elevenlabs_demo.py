#!/usr/bin/env python3
"""Demo script for ElevenLabs provider in gensay."""

import os
import sys

from dotenv import load_dotenv

from gensay import AudioFormat, ElevenLabsProvider, TTSConfig


def main():
    # Load environment variables from .env file
    load_dotenv()

    # Check for API key
    if not os.getenv("ELEVENLABS_API_KEY"):
        print("Error: Please set ELEVENLABS_API_KEY environment variable")
        print("Get your API key from https://elevenlabs.io")
        sys.exit(1)

    print("=== ElevenLabs Provider Demo ===\n")

    # Create provider
    config = TTSConfig(format=AudioFormat.MP3, extra={"show_progress": True})

    try:
        provider = ElevenLabsProvider(config)
        print("✓ Connected to ElevenLabs API\n")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    # List available voices
    print("Available voices:")
    voices = provider.list_voices()
    for i, voice in enumerate(voices[:5]):  # Show first 5
        print(f"  {i + 1}. {voice['name']} ({voice['id'][:8]}...)")
        if voice.get("description"):
            print(f"     {voice['description']}")
    print(f"  ... and {len(voices) - 5} more voices\n")

    # Example usage
    demo_text = "Hello! This is a demonstration of the ElevenLabs text-to-speech provider."

    # 1. Speak with default voice
    print("1. Speaking with default voice (Rachel)...")
    provider.speak(demo_text)

    # 2. Save to file
    print("\n2. Saving to file...")
    output_path = provider.save_to_file(
        demo_text, "elevenlabs_demo.mp3", voice="Rachel", format=AudioFormat.MP3
    )
    print(f"   Saved to: {output_path}")

    # 3. Try different rates (via stability)
    print("\n3. Testing different speech rates...")
    slow_config = TTSConfig(rate=100)  # Slow speech
    slow_provider = ElevenLabsProvider(slow_config)
    print("   Slow speech (100 WPM)...")
    slow_provider.speak("This is slow speech.")

    fast_config = TTSConfig(rate=200)  # Fast speech
    fast_provider = ElevenLabsProvider(fast_config)
    print("   Fast speech (200 WPM)...")
    fast_provider.speak("This is fast speech.")

    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
