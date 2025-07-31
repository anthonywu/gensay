"""Tests for the text chunking module."""

from gensay.text_chunker import (
    ChunkingConfig,
    ChunkingStrategy,
    TextChunker,
    chunk_text,
    smart_chunk_for_tts,
)


class TestTextChunker:
    """Test cases for TextChunker class."""

    def test_empty_text(self):
        """Test handling of empty text."""
        chunker = TextChunker()
        assert chunker.chunk_text("") == []
        assert chunker.chunk_text("   ") == []
        assert chunker.chunk_text(None) == []

    def test_short_text(self):
        """Test text shorter than max chunk size."""
        config = ChunkingConfig(max_chunk_size=100)
        chunker = TextChunker(config)

        text = "This is a short text."
        chunks = chunker.chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_sentence_chunking(self):
        """Test chunking at sentence boundaries."""
        config = ChunkingConfig(max_chunk_size=50, strategy=ChunkingStrategy.SENTENCE)
        chunker = TextChunker(config)

        text = (
            "This is the first sentence. This is the second sentence. This is the third sentence."
        )
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 3
        assert "first sentence" in chunks[0]
        assert "second sentence" in chunks[1]
        assert "third sentence" in chunks[2]

    def test_long_sentence_splitting(self):
        """Test splitting of sentences longer than max chunk size."""
        config = ChunkingConfig(max_chunk_size=50, strategy=ChunkingStrategy.SENTENCE)
        chunker = TextChunker(config)

        text = "This is a very long sentence that contains many words and will definitely exceed the maximum chunk size limit that we have configured for our test."
        chunks = chunker.chunk_text(text)

        assert len(chunks) > 1
        assert all(len(chunk) <= 50 for chunk in chunks)

    def test_paragraph_chunking(self):
        """Test chunking at paragraph boundaries."""
        config = ChunkingConfig(max_chunk_size=100, strategy=ChunkingStrategy.PARAGRAPH)
        chunker = TextChunker(config)

        text = """First paragraph here.

Second paragraph here.

Third paragraph here."""

        chunks = chunker.chunk_text(text)
        assert len(chunks) == 3
        assert "First paragraph" in chunks[0]
        assert "Second paragraph" in chunks[1]
        assert "Third paragraph" in chunks[2]

    def test_word_chunking(self):
        """Test chunking at word boundaries."""
        config = ChunkingConfig(max_chunk_size=20, strategy=ChunkingStrategy.WORD)
        chunker = TextChunker(config)

        text = "This is a test of word based chunking strategy"
        chunks = chunker.chunk_text(text)

        assert len(chunks) > 1
        assert all(len(chunk) <= 20 for chunk in chunks)
        # Verify no words are split
        for chunk in chunks:
            words = chunk.split()
            assert all(" " not in word for word in words)

    def test_character_chunking(self):
        """Test chunking at character boundaries."""
        config = ChunkingConfig(max_chunk_size=10, strategy=ChunkingStrategy.CHARACTER)
        chunker = TextChunker(config)

        text = "1234567890abcdefghij"
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 2
        assert chunks[0] == "1234567890"
        assert chunks[1] == "abcdefghij"

    def test_overlap_functionality(self):
        """Test chunk overlap feature."""
        config = ChunkingConfig(
            max_chunk_size=20, overlap_size=5, strategy=ChunkingStrategy.CHARACTER
        )
        chunker = TextChunker(config)

        text = "1234567890abcdefghijklmnop"
        chunks = chunker.chunk_text(text)

        # With overlap, chunks should share some characters
        assert len(chunks) == 2
        assert chunks[0] == "1234567890abcdefghij"
        assert chunks[1] == "klmnop"

    def test_punctuation_handling(self):
        """Test handling of various punctuation marks."""
        config = ChunkingConfig(max_chunk_size=50)
        chunker = TextChunker(config)

        text = "Question? Exclamation! Statement. Another one; with semicolon: and colon."
        chunks = chunker.chunk_text(text)

        # Should split at sentence terminators
        assert any("Question?" in chunk for chunk in chunks)
        assert any("Exclamation!" in chunk for chunk in chunks)
        assert any("Statement." in chunk for chunk in chunks)

    def test_whitespace_stripping(self):
        """Test whitespace stripping configuration."""
        config = ChunkingConfig(max_chunk_size=50, strip_whitespace=True)
        chunker = TextChunker(config)

        text = "  Text with spaces.  Another sentence.  "
        chunks = chunker.chunk_text(text)

        # Check that chunks don't have leading/trailing whitespace
        for chunk in chunks:
            assert chunk == chunk.strip()

    def test_estimate_chunks(self):
        """Test chunk estimation functionality."""
        config = ChunkingConfig(max_chunk_size=10)
        chunker = TextChunker(config)

        assert chunker.estimate_chunks("") == 0
        assert chunker.estimate_chunks("12345") == 1
        assert chunker.estimate_chunks("1234567890123") >= 2

    def test_get_chunk_info(self):
        """Test getting detailed chunk information."""
        config = ChunkingConfig(max_chunk_size=20, strategy=ChunkingStrategy.WORD)
        chunker = TextChunker(config)

        text = "This is a test text for chunk info"
        chunk_info = chunker.get_chunk_info(text)

        assert len(chunk_info) > 0
        for start, end, chunk in chunk_info:
            assert start >= 0
            assert end > start
            assert chunk.strip() in text

    def test_complex_text(self):
        """Test with complex, real-world text."""
        config = ChunkingConfig(max_chunk_size=150)
        chunker = TextChunker(config)

        text = """The quick brown fox jumps over the lazy dog. This pangram sentence contains every letter of the alphabet!

        In the second paragraph, we have more text. It includes various punctuation: commas, semicolons; and even dashes - like this one.

        Questions? Of course! Exclamations too! And regular statements."""

        chunks = chunker.chunk_text(text)

        # Verify all text is preserved
        combined = " ".join(chunks)
        assert "quick brown fox" in combined
        assert "second paragraph" in combined
        assert "Questions?" in combined

    def test_unicode_handling(self):
        """Test handling of unicode characters."""
        config = ChunkingConfig(max_chunk_size=50)
        chunker = TextChunker(config)

        text = "Hello 世界! This is mixed text. 这是中文。Another sentence."
        chunks = chunker.chunk_text(text)

        assert len(chunks) > 0
        # Verify unicode is preserved
        combined = " ".join(chunks)
        assert "世界" in combined
        assert "这是中文" in combined


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_chunk_text_function(self):
        """Test the chunk_text convenience function."""
        text = "Short sentence. Another one. And a third."
        chunks = chunk_text(text, max_size=20)

        assert len(chunks) > 1
        assert all(len(chunk) <= 20 for chunk in chunks)

    def test_chunk_text_with_strategy(self):
        """Test chunk_text with different strategies."""
        text = "Test text for chunking"

        # Test with string strategy
        chunks1 = chunk_text(text, max_size=10, strategy="word")
        assert len(chunks1) > 1

        # Test with enum strategy
        chunks2 = chunk_text(text, max_size=10, strategy=ChunkingStrategy.WORD)
        assert chunks1 == chunks2

    def test_smart_chunk_for_tts(self):
        """Test TTS-optimized chunking."""
        text = "This is text for TTS. It should be chunked appropriately."
        chunks, config = smart_chunk_for_tts(text, max_size=30)

        assert len(chunks) > 1
        assert config.silence_duration == 0.3
        assert config.strategy == ChunkingStrategy.SENTENCE
        assert all(len(chunk) <= 30 for chunk in chunks)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_single_long_word(self):
        """Test handling of single word longer than max size."""
        config = ChunkingConfig(max_chunk_size=5, strategy=ChunkingStrategy.WORD)
        chunker = TextChunker(config)

        text = "supercalifragilisticexpialidocious"
        chunks = chunker.chunk_text(text)

        # Word should be split at character level
        assert len(chunks) > 1
        assert all(len(chunk) <= 5 for chunk in chunks)

    def test_only_punctuation(self):
        """Test text containing only punctuation."""
        chunker = TextChunker()

        text = "...!!!???"
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_mixed_line_endings(self):
        """Test handling of different line ending styles."""
        config = ChunkingConfig(max_chunk_size=50)
        chunker = TextChunker(config)

        text = "Line 1\nLine 2\r\nLine 3\rLine 4"
        chunks = chunker.chunk_text(text)

        assert len(chunks) > 0
        combined = " ".join(chunks)
        assert "Line 1" in combined
        assert "Line 4" in combined

    def test_repeated_separators(self):
        """Test handling of repeated separators."""
        config = ChunkingConfig(max_chunk_size=50)
        chunker = TextChunker(config)

        text = "Sentence...   Another???   And more!!!"
        chunks = chunker.chunk_text(text)

        assert len(chunks) > 0
        assert any("Sentence" in chunk for chunk in chunks)
        assert any("Another" in chunk for chunk in chunks)
