"""Step 5 of the cascade, for real (Task 1.3b) — one binary question to `MODEL_ENDPOINTER`.
`cascade.resolve_endpoint` owns the 80ms timeout; this module only builds the prompt and
parses the answer, so it stays a plain injectable `SemanticChecker` callable at the call site.

Verified live against the actually-configured `MODEL_ENDPOINTER`
(`ollama/qwen2.5:0.5b-instruct`, .env.example): a zero-shot version of this prompt got a
plainly complete sentence ("That's the whole story.") wrong. The four-example few-shot prompt
below fixes that specific case but the model is still not perfectly reliable at 0.5B params —
it is genuinely fast (the entire point of choosing a model this small for an 80ms budget), not
genuinely accurate. That is why this step is designed to be cuttable and to fail toward END on
any doubt (docs/phase-1-BUILD.md Task 1.3c): the architecture assumes this model will sometimes
be wrong, rather than engineering the prompt until it never is.
"""

from __future__ import annotations

import litellm

_SYSTEM_PROMPT = """You judge whether a spoken sentence fragment is a complete thought or \
clearly cut off mid-sentence. Reply with exactly one word: COMPLETE or INCOMPLETE.

Examples:
Fragment: That is the whole story.
Answer: COMPLETE

Fragment: and then we handed it off to the
Answer: INCOMPLETE

Fragment: so I was thinking, um
Answer: INCOMPLETE

Fragment: We shipped it the following week.
Answer: COMPLETE"""


async def check_semantic_completeness(model: str, transcript_tail: str) -> bool:
    """Returns True if the fragment reads as a complete thought. An empty tail (nothing
    transcribed yet) is treated as complete — there's nothing to hold on."""
    if not transcript_tail.strip():
        return True

    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Fragment: {transcript_tail}\nAnswer:"},
        ],
        max_tokens=4,
        temperature=0,
    )
    content = response.choices[0].message.content or ""
    return content.strip().upper().startswith("COMPLETE")
