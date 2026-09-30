"""Unit tests for the LightRAG retrieval result formatter."""

from deerflow.community.lightrag.formatting import (
    _chunks,
    _reference_file_paths,
    _truncate,
    format_retrieval_result,
)

# ── _truncate ──────────────────────────────────────────────────────────────


class TestTruncate:
    def test_short_string_unchanged(self):
        assert _truncate("hello", 100) == "hello"

    def test_exact_max_chars(self):
        assert _truncate("hello", 5) == "hello"

    def test_long_string_truncated_with_marker(self):
        result = _truncate("hello world", 8)
        assert result == "hello w…"
        assert len(result) == 8

    def test_marker_longer_than_max_chars(self):
        assert _truncate("hello", 1, marker="---") == "-"
        assert _truncate("hello", 2, marker="---") == "--"

    def test_marker_exactly_max_chars(self):
        assert _truncate("hello", 3, marker="---") == "---"

    def test_marker_zero_max_chars(self):
        assert _truncate("hello", 0, marker="…") == ""

    def test_custom_marker(self):
        result = _truncate("hello world", 10, marker="[...]")
        assert result == "hello[...]"
        assert len(result) == 10

    def test_empty_string_unchanged(self):
        assert _truncate("", 100) == ""

    def test_whitespace_only_stripped_to_marker(self):
        # _truncate rstrips the prefix, so whitespace-only content truncates to just the marker
        assert _truncate("   ", 2) == "…"


# ── _chunks ────────────────────────────────────────────────────────────────


class TestChunks:
    def test_non_list_returns_empty(self):
        assert _chunks("not a list") == []
        assert _chunks(None) == []
        assert _chunks(42) == []

    def test_empty_list(self):
        assert _chunks([]) == []

    def test_all_valid_chunks(self):
        result = _chunks([{"content": "a"}, {"content": "b"}])
        assert len(result) == 2

    def test_filters_non_mapping_items(self):
        result = _chunks([{"content": "a"}, "string", None, 42, {"content": "b"}])
        assert len(result) == 2
        assert result[0] == {"content": "a"}
        assert result[1] == {"content": "b"}

    def test_all_invalid_items(self):
        assert _chunks(["a", "b", None]) == []


# ── _reference_file_paths ──────────────────────────────────────────────────


class TestReferenceFilePaths:
    def test_non_list_returns_empty(self):
        assert _reference_file_paths("not a list") == {}
        assert _reference_file_paths(None) == {}

    def test_empty_list(self):
        assert _reference_file_paths([]) == {}

    def test_builds_file_path_map(self):
        refs = [
            {"reference_id": "1", "file_path": "documents/a.md"},
            {"reference_id": "2", "file_path": "documents/b.md"},
        ]
        assert _reference_file_paths(refs) == {
            "1": "documents/a.md",
            "2": "documents/b.md",
        }

    def test_skips_entries_without_reference_id(self):
        refs = [
            {"reference_id": "1", "file_path": "documents/a.md"},
            {"file_path": "documents/b.md"},
            {"reference_id": "3", "file_path": "documents/c.md"},
        ]
        assert _reference_file_paths(refs) == {
            "1": "documents/a.md",
            "3": "documents/c.md",
        }

    def test_skips_entries_without_file_path(self):
        refs = [
            {"reference_id": "1", "file_path": "documents/a.md"},
            {"reference_id": "2"},
            {"reference_id": "3", "file_path": "documents/c.md"},
        ]
        assert _reference_file_paths(refs) == {
            "1": "documents/a.md",
            "3": "documents/c.md",
        }

    def test_skips_empty_file_path(self):
        refs = [
            {"reference_id": "1", "file_path": ""},
            {"reference_id": "2", "file_path": "documents/b.md"},
        ]
        assert _reference_file_paths(refs) == {
            "2": "documents/b.md",
        }

    def test_skips_whitespace_only_file_path(self):
        refs = [
            {"reference_id": "1", "file_path": "   "},
            {"reference_id": "2", "file_path": "documents/b.md"},
        ]
        assert _reference_file_paths(refs) == {
            "2": "documents/b.md",
        }

    def test_first_file_path_wins_on_duplicate_reference_id(self):
        refs = [
            {"reference_id": "1", "file_path": "documents/a.md"},
            {"reference_id": "1", "file_path": "documents/a-override.md"},
        ]
        assert _reference_file_paths(refs) == {
            "1": "documents/a.md",
        }

    def test_filters_non_mapping_items(self):
        refs = [{"reference_id": "1", "file_path": "documents/a.md"}, "string", None]
        assert _reference_file_paths(refs) == {
            "1": "documents/a.md",
        }

    def test_non_string_reference_id(self):
        refs = [
            {"reference_id": 1, "file_path": "documents/a.md"},
            {"reference_id": "2", "file_path": "documents/b.md"},
        ]
        assert _reference_file_paths(refs) == {
            "2": "documents/b.md",
        }


# ── format_retrieval_result ────────────────────────────────────────────────


class TestFormatRetrievalResult:
    def test_no_chunks_returns_explicit_message(self):
        result = format_retrieval_result({"chunks": []})
        assert result == "No relevant content found."

    def test_missing_chunks_key(self):
        result = format_retrieval_result({})
        assert result == "No relevant content found."

    def test_single_chunk(self):
        result = format_retrieval_result(
            {
                "chunks": [{"content": "Policy content.", "file_path": "docs/policy.md"}],
                "references": [{"reference_id": "1", "file_path": "docs/policy.md"}],
            },
        )
        assert "[1] docs/policy.md\nPolicy content." in result
        assert "Matched documents: docs/policy.md (1 chunk)" in result

    def test_multiple_chunks_same_document(self):
        result = format_retrieval_result(
            {
                "chunks": [
                    {"content": "Chunk A.", "file_path": "docs/handbook.md"},
                    {"content": "Chunk B.", "file_path": "docs/handbook.md"},
                ],
                "references": [{"reference_id": "1", "file_path": "docs/handbook.md"}],
            },
        )
        assert "[1] docs/handbook.md\nChunk A." in result
        assert "[2] docs/handbook.md\nChunk B." in result
        assert "Matched documents: docs/handbook.md (2 chunks)" in result

    def test_chunks_from_different_documents(self):
        result = format_retrieval_result(
            {
                "chunks": [
                    {"content": "A.", "file_path": "docs/doc1.md"},
                    {"content": "B.", "file_path": "docs/doc2.md"},
                ],
                "references": [],
            },
        )
        assert "Matched documents: docs/doc1.md (1 chunk), docs/doc2.md (1 chunk)" in result

    def test_total_response_truncation(self):
        """Response longer than max_total_chars gets truncated."""
        entries = [{"content": "Content " * 20, "file_path": f"documents/doc-{i}.md"} for i in range(5)]
        result = format_retrieval_result(
            {"chunks": entries, "references": []},
            max_chars_per_chunk=100,
            max_total_chars=150,
        )
        assert len(result) <= 150
        assert result.endswith("… (response truncated)")

    def test_degenerate_max_total_chars(self):
        """When max_total_chars is shorter than the truncation marker itself."""
        result = format_retrieval_result(
            {
                "chunks": [{"content": "A" * 1000, "file_path": "docs/big.md"}],
                "references": [],
            },
            max_chars_per_chunk=1000,
            max_total_chars=5,
        )
        assert len(result) == 5
        assert result == "… (re"  # truncated marker at 5

    def test_chunk_content_with_missing_file_path(self):
        result = format_retrieval_result(
            {
                "chunks": [{"content": "Orphan content.", "chunk_id": "abc"}],
                "references": [],
            },
        )
        assert "[1] Unknown document\nOrphan content." in result

    def test_chunk_content_with_empty_file_path(self):
        result = format_retrieval_result(
            {
                "chunks": [{"content": "Empty path.", "file_path": ""}],
                "references": [],
            },
        )
        assert "[1] Unknown document\nEmpty path." in result

    def test_pre_v149_flat_chunks_are_processed(self):
        """v1.4.8 returns flat {entities, relationships, chunks, metadata}."""
        result = format_retrieval_result(
            {
                "chunks": [{"content": "Flat chunk."}],
                "references": [],
                "entities": [{"entity_name": "LightRAG"}],
                "relationships": [],
            },
        )
        assert "[1] Unknown document\nFlat chunk." in result

    def test_content_truncation_at_chunk_level(self):
        result = format_retrieval_result(
            {
                "chunks": [{"content": "A" * 100, "file_path": "docs/big.md"}],
                "references": [],
            },
            max_chars_per_chunk=10,
            max_total_chars=1000,
        )
        # "AAAAAAAAAA" (10 chars) → "AAAAAAAAA…" (11 chars) = 10 chars + marker
        assert "…" in result
        assert "AAAA" * 25 not in result
