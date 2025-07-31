"""Tests for CLI interface."""

from unittest.mock import MagicMock, patch

from gensay.main import create_parser, get_text_input


def test_parser_creation():
    """Test argument parser creation."""
    parser = create_parser()
    assert parser.prog == "gensay"


def test_text_input_from_message():
    """Test getting text from command line message."""
    args = MagicMock()
    args.message = ["Hello", "world"]
    args.file = None

    text = get_text_input(args)
    assert text == "Hello world"


def test_text_input_from_file(tmp_path):
    """Test getting text from file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Text from file")

    args = MagicMock()
    args.message = None
    args.file = str(test_file)

    text = get_text_input(args)
    assert text == "Text from file"


def test_text_input_from_stdin():
    """Test getting text from stdin."""
    args = MagicMock()
    args.message = None
    args.file = "-"

    with patch("sys.stdin.read", return_value="Text from stdin\n"):
        text = get_text_input(args)
        assert text == "Text from stdin"


def test_parser_voice_listing():
    """Test voice listing argument."""
    parser = create_parser()
    args = parser.parse_args(["-v", "?"])
    assert args.voice == "?"


def test_parser_output_format():
    """Test output format arguments."""
    parser = create_parser()
    args = parser.parse_args(["-o", "output.m4a", "--format", "wav", "Hello"])
    assert args.output == "output.m4a"
    assert args.format == "wav"


def test_parser_provider_selection():
    """Test provider selection."""
    parser = create_parser()
    args = parser.parse_args(["--provider", "mock", "Test"])
    assert args.provider == "mock"
