"""The sentence chunker (Task 1.5a). A pure function over accumulated text — no model, no I/O.
Consumes a token stream (via repeated `feed()` calls) and yields chunks ready for synthesis.

Design notes worth knowing before touching this file:

- **Abbreviations don't count toward the clause-split word minimum.** `"e.g. Kafka, Redis, and
  Postgres."` must stay one chunk (Task 1.5a's own test table). If "e.g." counted as an
  ordinary word, the comma after "Redis" would cross the 3-word minimum and split there. An
  abbreviation isn't semantically "a word" for pacing purposes, so it's excluded from the
  count — this is what makes that row (and no other) come out to one chunk.
- **A `.!?` immediately followed by closing quotes/brackets is absorbed into the same split** —
  `He said "yes." Then he left.` splits *after* the closing quote, not before it, so a chunk
  never ends on a dangling unmatched quote mark.
- **Only one open-quote/bracket is tracked at a time** (no nested-same-type quoting). Real
  spoken turns don't nest quotes; this is a deliberate scope limit, not an oversight.
"""

from __future__ import annotations

ABBREVIATIONS = frozenset({"dr.", "mr.", "mrs.", "ms.", "e.g.", "i.e.", "etc.", "vs.", "approx."})
OPEN_BRACKETS = "([{"
CLOSE_BRACKETS = ")]}"
_BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}

FIRST_CHUNK_MAX_WORDS = 12
CHUNK_MAX_WORDS = 40
MIN_WORDS_FOR_CLAUSE_SPLIT = 3


def _is_abbreviation_token(token: str) -> bool:
    return token.lower() in ABBREVIATIONS


def _is_quote_apostrophe(buffer: str, i: int) -> bool:
    """Distinguishes a dialogue-quoting apostrophe from a contraction's ("don't", "it's") —
    a contraction always has letters on both sides."""
    prev_alpha = i > 0 and buffer[i - 1].isalpha()
    next_alpha = i + 1 < len(buffer) and buffer[i + 1].isalpha()
    return not (prev_alpha and next_alpha)


def _in_ellipsis(buffer: str, i: int) -> bool:
    left = i > 0 and buffer[i - 1] == "."
    right = i + 1 < len(buffer) and buffer[i + 1] == "."
    return left or right


def _skip_ellipsis(buffer: str, i: int) -> int:
    j = i
    while j < len(buffer) and buffer[j] == ".":
        j += 1
    return j


def _find_split(buffer: str, *, max_words: int) -> int | None:
    """Returns the exclusive end index of the first valid split in `buffer`, or None if the
    whole buffer should keep accumulating."""
    n = len(buffer)
    i = 0
    open_quote: str | None = None
    bracket_stack: list[str] = []
    word_count = 0
    in_word = False
    current_token_is_abbrev = False

    while i < n:
        c = buffer[i]

        if c.isspace():
            in_word = False
            current_token_is_abbrev = False
        elif not in_word:
            in_word = True
            token_end = i
            while token_end < n and not buffer[token_end].isspace():
                token_end += 1
            current_token_is_abbrev = _is_abbreviation_token(buffer[i:token_end])
            if not current_token_is_abbrev:
                word_count += 1
                if word_count > max_words:
                    return i  # force-split before this over-cap word begins

        if c in OPEN_BRACKETS:
            bracket_stack.append(_BRACKET_PAIRS[c])
        elif c in CLOSE_BRACKETS:
            if bracket_stack and bracket_stack[-1] == c:
                bracket_stack.pop()
        elif c == '"':
            open_quote = None if open_quote == '"' else '"'
        elif c == "'" and _is_quote_apostrophe(buffer, i):
            open_quote = None if open_quote == "'" else "'"

        if c in ".!?":
            if current_token_is_abbrev:
                i += 1
                continue
            if c == "." and _in_ellipsis(buffer, i):
                i = _skip_ellipsis(buffer, i)
                continue
            if (
                c == "."
                and i > 0
                and buffer[i - 1].isdigit()
                and i + 1 < n
                and buffer[i + 1].isdigit()
            ):
                i += 1  # decimal or version-string dot (e.g. 99.9, v1.2.3)
                continue

            k = i + 1
            while k < n and (buffer[k] == '"' or buffer[k] in CLOSE_BRACKETS):
                if buffer[k] == '"':
                    open_quote = None if open_quote == '"' else open_quote
                elif bracket_stack and bracket_stack[-1] == buffer[k]:
                    bracket_stack.pop()
                k += 1
            if open_quote is None and not bracket_stack:
                return k
            i = k
            continue
        elif c in ",;:":
            if (
                word_count >= MIN_WORDS_FOR_CLAUSE_SPLIT
                and open_quote is None
                and not bracket_stack
            ):
                return i + 1

        i += 1
    return None


class SentenceChunker:
    """Streaming wrapper: `feed()` with each new text delta, `flush()` once the token stream
    ends to force-emit whatever remains (Task 1.5a's last rule)."""

    def __init__(self) -> None:
        self._buffer = ""
        self._emitted_first = False

    def feed(self, text_delta: str) -> list[str]:
        self._buffer += text_delta
        chunks: list[str] = []
        while True:
            max_words = FIRST_CHUNK_MAX_WORDS if not self._emitted_first else CHUNK_MAX_WORDS
            split_at = _find_split(self._buffer, max_words=max_words)
            if split_at is None:
                break
            chunk = self._buffer[:split_at].strip()
            self._buffer = self._buffer[split_at:].lstrip()
            if chunk:
                chunks.append(chunk)
                self._emitted_first = True
        return chunks

    def flush(self) -> list[str]:
        remainder = self._buffer.strip()
        self._buffer = ""
        if not remainder:
            return []
        self._emitted_first = True
        return [remainder]


def chunk_text(text: str) -> list[str]:
    """Convenience for tests and any non-streaming caller: chunk a complete string in one call."""
    chunker = SentenceChunker()
    chunks = chunker.feed(text)
    chunks.extend(chunker.flush())
    return chunks
