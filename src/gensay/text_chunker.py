"""
Text chunking utilities for splitting long text into manageable chunks.

This module provides a flexible text chunking system that can split text
intelligently at natural boundaries while respecting size constraints.
"""

import re
from dataclasses import dataclass
from enum import Enum


class ChunkingStrategy(Enum):
    """Different strategies for splitting text."""

    SENTENCE = "sentence"  # Split at sentence boundaries
    PARAGRAPH = "paragraph"  # Split at paragraph boundaries
    WORD = "word"  # Split at word boundaries
    CHARACTER = "character"  # Split at character boundaries


@dataclass
class ChunkingConfig:
    """Configuration for text chunking behavior."""

    max_chunk_size: int = 250
    min_chunk_size: int = 50
    overlap_size: int = 0  # Characters to overlap between chunks
    preserve_sentences: bool = True
    preserve_words: bool = True
    sentence_terminators: str = r"[.!?]"
    sub_sentence_separators: str = r"[,;:]"
    paragraph_separator: str = "\n\n"
    silence_duration: float = 0.3  # Seconds between chunks
    strip_whitespace: bool = True
    strategy: ChunkingStrategy = ChunkingStrategy.SENTENCE


class TextChunker:
    """
    A flexible text chunking system that splits text intelligently.

    This class provides various strategies for splitting text into chunks
    while preserving natural boundaries and maintaining readability.
    """

    def __init__(self, config: ChunkingConfig | None = None):
        """Initialize the chunker with configuration."""
        self.config = config or ChunkingConfig()

        # Compile regex patterns for efficiency
        self._sentence_pattern = re.compile(rf"(?<={self.config.sentence_terminators})\s+")
        self._sub_sentence_pattern = re.compile(rf"(?<={self.config.sub_sentence_separators})\s+")

    def chunk_text(self, text: str) -> list[str]:
        """
        Split text into chunks based on the configured strategy.

        Args:
            text: The text to split into chunks

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        # Choose chunking strategy
        if self.config.strategy == ChunkingStrategy.PARAGRAPH:
            return self._chunk_by_paragraphs(text)
        elif self.config.strategy == ChunkingStrategy.WORD:
            return self._chunk_by_words(text)
        elif self.config.strategy == ChunkingStrategy.CHARACTER:
            return self._chunk_by_characters(text)
        else:  # Default to sentence strategy
            return self._chunk_by_sentences(text)

    def _chunk_by_sentences(self, text: str) -> list[str]:
        """Split text at sentence boundaries."""
        # First, handle paragraphs if they exist
        paragraphs = text.split(self.config.paragraph_separator)
        chunks = []

        for paragraph in paragraphs:
            if not paragraph.strip():
                continue

            # Split into sentences
            sentences = self._sentence_pattern.split(paragraph)

            # Process sentences
            current_chunk = ""

            for sentence in sentences:
                sentence = sentence.strip() if self.config.strip_whitespace else sentence
                if not sentence:
                    continue

                # Check if sentence itself is too long
                if len(sentence) > self.config.max_chunk_size:
                    # Flush current chunk if any
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = ""

                    # Split long sentence
                    sentence_chunks = self._split_long_sentence(sentence)
                    chunks.extend(sentence_chunks)
                else:
                    # Try to add sentence to current chunk
                    test_chunk = f"{current_chunk} {sentence}" if current_chunk else sentence

                    if len(test_chunk) <= self.config.max_chunk_size:
                        current_chunk = test_chunk
                    else:
                        # Current chunk is full, start new one
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sentence

            # Add any remaining chunk
            if current_chunk:
                chunks.append(current_chunk)

        return self._apply_overlap(chunks)

    def _chunk_by_paragraphs(self, text: str) -> list[str]:
        """Split text at paragraph boundaries."""
        paragraphs = text.split(self.config.paragraph_separator)
        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            paragraph = paragraph.strip() if self.config.strip_whitespace else paragraph
            if not paragraph:
                continue

            # Check if paragraph itself is too long
            if len(paragraph) > self.config.max_chunk_size:
                # Flush current chunk
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                # Use sentence chunking for long paragraph
                para_chunks = self._chunk_by_sentences(paragraph)
                chunks.extend(para_chunks)
            else:
                # Try to add paragraph to current chunk
                test_chunk = f"{current_chunk}\n\n{paragraph}" if current_chunk else paragraph

                if len(test_chunk) <= self.config.max_chunk_size:
                    current_chunk = test_chunk
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = paragraph

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _chunk_by_words(self, text: str) -> list[str]:
        """Split text at word boundaries."""
        words = text.split()
        chunks = []
        current_chunk = ""

        for word in words:
            test_chunk = f"{current_chunk} {word}" if current_chunk else word

            if len(test_chunk) <= self.config.max_chunk_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                # Handle case where single word exceeds max size
                if len(word) > self.config.max_chunk_size:
                    for i in range(0, len(word), self.config.max_chunk_size):
                        chunks.append(word[i : i + self.config.max_chunk_size])
                    current_chunk = ""
                else:
                    current_chunk = word

        if current_chunk:
            chunks.append(current_chunk)

        return self._apply_overlap(chunks)

    def _chunk_by_characters(self, text: str) -> list[str]:
        """Split text at character boundaries (simplest method)."""
        chunks = []
        for i in range(0, len(text), self.config.max_chunk_size - self.config.overlap_size):
            chunk = text[i : i + self.config.max_chunk_size]
            if chunk:
                chunks.append(chunk)
        return chunks

    def _split_long_sentence(self, sentence: str) -> list[str]:
        """Split a long sentence using sub-sentence separators or words."""
        # First try splitting by sub-sentence separators
        parts = self._sub_sentence_pattern.split(sentence)

        if len(parts) > 1:
            # Use sub-sentence chunking
            chunks = []
            current_chunk = ""

            for part in parts:
                part = part.strip() if self.config.strip_whitespace else part
                if not part:
                    continue

                if len(part) > self.config.max_chunk_size:
                    # Part is still too long, split by words
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = ""

                    word_chunks = self._split_by_words(part)
                    chunks.extend(word_chunks)
                else:
                    test_chunk = f"{current_chunk}, {part}" if current_chunk else part

                    if len(test_chunk) <= self.config.max_chunk_size:
                        current_chunk = test_chunk
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = part

            if current_chunk:
                chunks.append(current_chunk)

            return chunks
        else:
            # No sub-sentence separators, split by words
            return self._split_by_words(sentence)

    def _split_by_words(self, text: str) -> list[str]:
        """Split text by words as a last resort."""
        words = text.split()
        chunks = []
        current_chunk = ""

        for word in words:
            test_chunk = f"{current_chunk} {word}" if current_chunk else word

            if len(test_chunk) <= self.config.max_chunk_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                # Handle case where single word exceeds max size
                if len(word) > self.config.max_chunk_size:
                    # Split the word itself
                    for i in range(0, len(word), self.config.max_chunk_size):
                        chunks.append(word[i : i + self.config.max_chunk_size])
                    current_chunk = ""
                else:
                    current_chunk = word

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """Apply overlap between chunks if configured."""
        if self.config.overlap_size <= 0 or len(chunks) <= 1:
            return chunks

        overlapped_chunks = [chunks[0]]

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]

            # Extract overlap from end of previous chunk
            if len(prev_chunk) >= self.config.overlap_size:
                overlap = prev_chunk[-self.config.overlap_size :]
                # Prepend overlap to current chunk if it doesn't already start with it
                if not curr_chunk.startswith(overlap):
                    curr_chunk = f"{overlap} {curr_chunk}"

            overlapped_chunks.append(curr_chunk)

        return overlapped_chunks

    def estimate_chunks(self, text: str) -> int:
        """Estimate the number of chunks that will be created."""
        if not text:
            return 0
        step = self.config.max_chunk_size - self.config.overlap_size
        # Ceiling division: -(-a // b)
        return max(1, -(-len(text) // step))

    def get_chunk_info(self, text: str) -> list[tuple[int, int, str]]:
        """
        Get detailed information about chunks including positions.

        Returns:
            List of tuples (start_pos, end_pos, chunk_text)
        """
        chunks = self.chunk_text(text)
        chunk_info = []
        current_pos = 0

        for chunk in chunks:
            # Find the chunk in the original text
            chunk_start = text.find(chunk.strip(), current_pos)
            if chunk_start == -1:
                # Fallback if exact match not found
                chunk_start = current_pos

            chunk_end = chunk_start + len(chunk)
            chunk_info.append((chunk_start, chunk_end, chunk))
            current_pos = chunk_end

        return chunk_info


# Convenience functions
def chunk_text(
    text: str,
    max_size: int = 250,
    strategy: str | ChunkingStrategy = ChunkingStrategy.SENTENCE,
) -> list[str]:
    """
    Convenience function to chunk text with default settings.

    Args:
        text: Text to chunk
        max_size: Maximum chunk size
        strategy: Chunking strategy to use

    Returns:
        List of text chunks
    """
    if isinstance(strategy, str):
        strategy = ChunkingStrategy(strategy)

    config = ChunkingConfig(max_chunk_size=max_size, strategy=strategy)
    chunker = TextChunker(config)
    return chunker.chunk_text(text)


def smart_chunk_for_tts(
    text: str, max_size: int = 250, silence_duration: float = 0.3
) -> tuple[list[str], ChunkingConfig]:
    """
    Chunk text specifically optimized for TTS applications.

    Args:
        text: Text to chunk
        max_size: Maximum chunk size
        silence_duration: Duration of silence between chunks

    Returns:
        Tuple of (chunks, config used)
    """
    config = ChunkingConfig(
        max_chunk_size=max_size,
        min_chunk_size=50,
        preserve_sentences=True,
        preserve_words=True,
        strip_whitespace=True,
        silence_duration=silence_duration,
        strategy=ChunkingStrategy.SENTENCE,
    )

    chunker = TextChunker(config)
    chunks = chunker.chunk_text(text)

    return chunks, config


def chunk_text_for_tts(
    text: str, max_chunk_size: int = 500, strategy: str = "sentence"
) -> list[str]:
    """Convenience function for TTS-optimized text chunking.

    Args:
        text: Text to chunk
        max_chunk_size: Maximum size of each chunk
        strategy: Chunking strategy to use

    Returns:
        List of text chunks
    """
    # Convert string strategy to enum if needed
    if isinstance(strategy, str):
        strategy = ChunkingStrategy(strategy)

    config = ChunkingConfig(
        max_chunk_size=max_chunk_size,
        strategy=strategy,
        sentence_terminators=r"[.!?。！？]",
        sub_sentence_separators=r"[,;:、；：]",
        strip_whitespace=True,
        silence_duration=0.3,
    )
    chunker = TextChunker(config)
    return chunker.chunk_text(text)
