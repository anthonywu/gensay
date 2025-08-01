#!/usr/bin/env python3
"""Demo script for gensay library."""

from gensay import AudioFormat, MockProvider, TTSConfig, chunk_text_for_tts


def progress_callback(progress: float, message: str):
    """Custom progress callback."""
    bar_length = 40
    filled = int(bar_length * progress)
    bar = "█" * filled + "░" * (bar_length - filled)
    print(f"\r[{bar}] {int(progress * 100)}% - {message}", end="", flush=True)
    if progress >= 1.0:
        print()  # New line when complete


def main():
    print("=== gensay Demo ===\n")

    # Example 1: Basic text-to-speech
    print("1. Basic TTS with MockProvider:")
    provider = MockProvider()
    provider.speak("Hello, this is a test of the gensay library!")

    # Example 2: Custom configuration
    print("\n2. Custom voice and rate:")
    config = TTSConfig(voice="mock-voice-2", rate=180, progress_callback=progress_callback)
    provider = MockProvider(config)
    provider.speak("Speaking with a different voice at a custom rate.")

    # Example 3: Save to file
    print("\n3. Save audio to file:")
    output_path = provider.save_to_file(
        "This audio is being saved to a file.", "output.m4a", format=AudioFormat.M4A
    )
    print(f"   Saved to: {output_path}")

    # Example 4: List voices
    print("\n4. Available voices:")
    voices = provider.list_voices()
    for voice in voices:
        print(f"   - {voice['id']}: {voice['name']} ({voice['language']})")

    # Example 5: Text chunking
    print("\n5. Text chunking for long content:")
    long_text = """
    This is a longer piece of text that demonstrates how the text chunking
    functionality works. When processing long documents, it's important to
    break them into manageable chunks that fit within the TTS engine's
    limitations while preserving natural speech boundaries.

    The chunking algorithm intelligently splits text at sentence boundaries
    when possible, ensuring that the resulting audio sounds natural and
    continuous.
    """

    chunks = chunk_text_for_tts(long_text, max_chunk_size=100)
    print(f"   Split into {len(chunks)} chunks:")
    for i, chunk in enumerate(chunks, 1):
        print(f"   Chunk {i}: {chunk[:50]}...")

    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
