"""Task 1.5a acceptance: "Chunker passes every row of the table above" plus the streaming
feed()/flush() contract and the word caps."""

from __future__ import annotations

import pytest

from services.realtime.app.tts.chunker import (
    CHUNK_MAX_WORDS,
    FIRST_CHUNK_MAX_WORDS,
    SentenceChunker,
    chunk_text,
)

# ── The exact table from docs/phase-1-BUILD.md TASK 1.5a ───────────────────────────────────
TABLE = [
    ("Dr. Smith joined in 2019.", 1),
    ("We hit 99.9% uptime. Then it broke.", 2),
    ("So, tell me about it.", 1),
    ('He said "yes." Then he left.', 2),
    ("Running v1.2.3 in prod.", 1),
    ("e.g. Kafka, Redis, and Postgres.", 1),
    ("Well... I think so.", 1),
]


@pytest.mark.parametrize(("text", "expected_n"), TABLE)
def test_table_row(text: str, expected_n: int) -> None:
    chunks = chunk_text(text)
    assert len(chunks) == expected_n, f"{text!r} -> {chunks!r}"


def test_quote_row_splits_after_closing_quote() -> None:
    chunks = chunk_text('He said "yes." Then he left.')
    assert chunks == ['He said "yes."', "Then he left."]


def test_leading_short_clause_merges() -> None:
    assert chunk_text("So, tell me about it.") == ["So, tell me about it."]


def test_force_split_at_word_cap_with_no_punctuation() -> None:
    words = [f"word{i}" for i in range(45)]
    text = " ".join(words)
    chunker = SentenceChunker()
    chunker.feed("Hi there.")  # consumes the "first chunk" slot with a trivial sentence
    chunks = chunker.feed(text)
    chunks.extend(chunker.flush())

    assert len(chunks) == 2
    assert len(chunks[0].split()) == CHUNK_MAX_WORDS
    assert len(chunks[1].split()) == 45 - CHUNK_MAX_WORDS


def test_first_chunk_capped_shorter_than_general_chunks() -> None:
    words = [f"word{i}" for i in range(20)]
    text = " ".join(words)
    chunks = chunk_text(text)
    assert len(chunks[0].split()) == FIRST_CHUNK_MAX_WORDS


def test_never_emits_an_empty_chunk() -> None:
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert chunk_text(". . .") != [""]  # even odd punctuation-only input has no empty entries
    for c in chunk_text(". . ."):
        assert c != ""


def test_streaming_feed_across_multiple_deltas_matches_batch() -> None:
    text = "So last quarter I rebuilt the pipeline. It backed up under load before that."
    batch = chunk_text(text)

    chunker = SentenceChunker()
    streamed: list[str] = []
    for word in text.split(" "):
        streamed.extend(chunker.feed(word + " "))
    streamed.extend(chunker.flush())

    assert "".join(streamed).replace(" ", "") == "".join(batch).replace(" ", "")


def test_flush_forces_out_a_remainder_with_no_terminal_punctuation() -> None:
    chunker = SentenceChunker()
    assert chunker.feed("and then we just kept going") == []
    remainder = chunker.flush()
    assert remainder == ["and then we just kept going"]


def test_contraction_apostrophe_does_not_toggle_quote_state() -> None:
    chunks = chunk_text("I don't think that's right. It just wasn't working.")
    assert len(chunks) == 2


def test_semicolon_is_a_clause_boundary_once_three_words_precede_it() -> None:
    chunks = chunk_text("We tried three things; none of them worked. So we escalated it.")
    # "We tried three" is already 3 words at the semicolon -> it splits there too
    assert chunks == ["We tried three things;", "none of them worked.", "So we escalated it."]


def test_colon_below_three_words_does_not_split() -> None:
    chunks = chunk_text("Note: it worked in the end.")
    assert chunks == ["Note: it worked in the end."]


def test_single_word_reply_is_one_chunk_no_clipping() -> None:
    assert chunk_text("Sure.") == ["Sure."]
