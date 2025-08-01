#!/usr/bin/env python3
"""
Demonstration of the improved text chunking system.

This example shows how to use the text chunker for various use cases,
particularly for TTS applications.
"""

from gensay.text_chunker import (
    ChunkingConfig,
    ChunkingStrategy,
    TextChunker,
    smart_chunk_for_tts,
)


def demo_basic_chunking():
    """Demonstrate basic text chunking."""
    print("=== Basic Text Chunking Demo ===\n")

    text = """
    The quick brown fox jumps over the lazy dog. This pangram sentence contains
    every letter of the alphabet! It's commonly used for testing fonts and
    keyboard layouts.

    In the field of natural language processing, text chunking is an essential
    preprocessing step. It helps break down large texts into manageable pieces
    while preserving semantic boundaries.
    """

    # Create chunker with default settings
    chunker = TextChunker()
    chunks = chunker.chunk_text(text)

    print(f"Original text length: {len(text)} characters")
    print(f"Number of chunks: {len(chunks)}")
    print("\nChunks:")
    for i, chunk in enumerate(chunks, 1):
        print(f"\nChunk {i} ({len(chunk)} chars):")
        print(f"  {chunk[:50]}..." if len(chunk) > 50 else f"  {chunk}")


def demo_tts_chunking():
    """Demonstrate TTS-optimized chunking."""
    print("\n\n=== TTS-Optimized Chunking Demo ===\n")

    text = """
    Welcome to the future of voice synthesis! With advanced text-to-speech
    technology, you can create natural-sounding voices. The system handles
    long texts by intelligently splitting them into chunks. Each chunk is
    processed separately, then seamlessly combined.

    This approach ensures optimal quality: no cutoffs mid-word, natural pauses
    at sentence boundaries, and consistent voice characteristics throughout.
    """

    # Use TTS-optimized chunking
    chunks, config = smart_chunk_for_tts(text, max_size=100, silence_duration=0.5)

    print("TTS Configuration:")
    print(f"  Max chunk size: {config.max_chunk_size}")
    print(f"  Silence duration: {config.silence_duration}s")
    print(f"  Strategy: {config.strategy.value}")
    print(f"\nNumber of chunks: {len(chunks)}")

    for i, chunk in enumerate(chunks, 1):
        print(f"\nChunk {i}:")
        print(f"  {chunk}")


def demo_different_strategies():
    """Demonstrate different chunking strategies."""
    print("\n\n=== Different Chunking Strategies Demo ===\n")

    text = """First paragraph talks about one topic.

Second paragraph discusses another topic entirely.

Third paragraph concludes the discussion."""

    strategies = [
        ChunkingStrategy.SENTENCE,
        ChunkingStrategy.PARAGRAPH,
        ChunkingStrategy.WORD,
        ChunkingStrategy.CHARACTER,
    ]

    for strategy in strategies:
        config = ChunkingConfig(max_chunk_size=40, strategy=strategy)
        chunker = TextChunker(config)
        chunks = chunker.chunk_text(text)

        print(f"\nStrategy: {strategy.value}")
        print(f"Number of chunks: {len(chunks)}")
        print(
            "Chunks:",
            [chunk[:20] + "..." if len(chunk) > 20 else chunk for chunk in chunks],
        )


def demo_advanced_configuration():
    """Demonstrate advanced configuration options."""
    print("\n\n=== Advanced Configuration Demo ===\n")

    text = "This is a test. Another sentence here! Question? More text follows, with various punctuation; including semicolons: and colons."

    # Custom configuration
    config = ChunkingConfig(
        max_chunk_size=50,
        min_chunk_size=20,
        overlap_size=10,  # 10 character overlap
        preserve_sentences=True,
        sentence_terminators=r"[.!?]",
        sub_sentence_separators=r"[,;:]",
    )

    chunker = TextChunker(config)
    chunks = chunker.chunk_text(text)

    print("Configuration:")
    print(f"  Max size: {config.max_chunk_size}")
    print(f"  Min size: {config.min_chunk_size}")
    print(f"  Overlap: {config.overlap_size}")
    print("\nChunks with overlap:")

    for i, chunk in enumerate(chunks, 1):
        print(f"\nChunk {i}: '{chunk}'")


def demo_chunk_info():
    """Demonstrate getting detailed chunk information."""
    print("\n\n=== Chunk Information Demo ===\n")

    text = "Short sentence. Medium length sentence here. This is a much longer sentence that might need to be split."

    config = ChunkingConfig(max_chunk_size=30)
    chunker = TextChunker(config)

    chunk_info = chunker.get_chunk_info(text)

    print("Detailed chunk information:")
    print(f"Original text: '{text}'")
    print("\nChunks with positions:")

    for i, (start, end, chunk) in enumerate(chunk_info, 1):
        print(f"\nChunk {i}:")
        print(f"  Position: [{start}:{end}]")
        print(f"  Text: '{chunk}'")
        print(f"  Original: '{text[start:end]}'")


def demo_real_world_example():
    """Demonstrate with a real-world example."""
    print("\n\n=== Real-World Example: Article Chunking ===\n")

    article = """
    Artificial Intelligence in Healthcare: A Revolution in Progress

    The integration of artificial intelligence (AI) into healthcare systems
    represents one of the most significant technological advances of our time.
    From diagnostic imaging to drug discovery, AI is transforming how medical
    professionals approach patient care.

    One of the most promising applications is in radiology. Machine learning
    algorithms can now detect certain cancers with accuracy matching or
    exceeding that of experienced radiologists. This doesn't replace doctors;
    rather, it augments their capabilities, allowing them to focus on complex
    cases and patient interaction.

    However, challenges remain. Data privacy, algorithm bias, and the need for
    explainable AI are critical concerns that must be addressed. As we move
    forward, collaboration between technologists, healthcare providers, and
    policymakers will be essential to realize AI's full potential while
    maintaining ethical standards.
    """

    # Configure for article processing
    config = ChunkingConfig(
        max_chunk_size=200, strategy=ChunkingStrategy.PARAGRAPH, preserve_sentences=True
    )

    chunker = TextChunker(config)
    chunks = chunker.chunk_text(article)

    print(f"Article length: {len(article)} characters")
    print(f"Number of chunks: {len(chunks)}")
    print(f"Estimated chunks: {chunker.estimate_chunks(article)}")

    for i, chunk in enumerate(chunks, 1):
        print(f"\n--- Chunk {i} ---")
        print(chunk.strip())


if __name__ == "__main__":
    # Run all demonstrations
    demo_basic_chunking()
    demo_tts_chunking()
    demo_different_strategies()
    demo_advanced_configuration()
    demo_chunk_info()
    demo_real_world_example()

    print("\n\n=== Demo Complete ===")
    print("The text chunking system provides flexible, maintainable text splitting")
    print("with support for various strategies and use cases.")
