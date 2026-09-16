"""docs/phase-5-BUILD.md TASK 5.4b / docs/phase-5-LEARN.md §2: the v1 scorer — DeBERTa-v3-base,
`[question] [SEP] [answer]`, one lightweight regression head per criterion on a shared encoder,
auxiliary numeric features (duration, word count) concatenated before the heads.
"""

from __future__ import annotations

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer

BASE_MODEL = "microsoft/deberta-v3-base"
MAX_LENGTH = 512
N_AUX_FEATURES = 2  # duration_ms (log-scaled), word_count (log-scaled)


class MultiCriterionScorer(nn.Module):
    """Shared encoder (docs/phase-5-LEARN.md §2: "They share most of the signal and the dataset
    is small; separate models would overfit") + one linear regression head per criterion,
    sigmoid-mapped onto the 1-5 rubric scale. Aux features are concatenated onto the pooled
    [CLS] representation before every head, not just one — duration/length affect every
    criterion's judgement to some degree (concision most directly, but structure and confidence
    both correlate with pacing too).
    """

    def __init__(self, criteria: list[str], *, base_model: str = BASE_MODEL) -> None:
        super().__init__()
        self.criteria = criteria
        self.encoder = AutoModel.from_pretrained(base_model)
        hidden_size = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.heads = nn.ModuleDict(
            {criterion: nn.Linear(hidden_size + N_AUX_FEATURES, 1) for criterion in criteria}
        )

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor, aux_features: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        encoded = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        # DeBERTa-v3 has no pooler head by design; mean-pool the last hidden state over real
        # (non-padding) tokens, which is the standard substitute.
        last_hidden = encoded.last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(last_hidden.dtype)
        pooled = (last_hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-6)
        pooled = self.dropout(pooled)
        combined = torch.cat([pooled, aux_features], dim=-1)

        outputs: dict[str, torch.Tensor] = {}
        for criterion, head in self.heads.items():
            raw = head(combined).squeeze(-1)
            # sigmoid -> [0,1] -> [1,5], "Regression with a sigmoid mapped to the scale"
            # (docs/phase-5-LEARN.md §2's design-decisions table).
            outputs[criterion] = torch.sigmoid(raw) * 4.0 + 1.0
        return outputs


def make_aux_features(duration_ms: int, word_count: int) -> list[float]:
    """log1p keeps a 3-minute outlier answer from dominating the feature's scale the way a raw
    millisecond count would."""
    import math

    return [math.log1p(max(duration_ms, 0)), math.log1p(max(word_count, 0))]


def load_tokenizer(base_model: str = BASE_MODEL) -> AutoTokenizer:
    return AutoTokenizer.from_pretrained(base_model)


def soft_ordinal_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """docs/phase-5-LEARN.md §2: "MSE on the normalised scale plus an auxiliary soft ordinal
    term." The ordinal term is a normalized absolute-distance penalty (0 at exact agreement, 1
    at the scale's maximum possible miss of 4 points) — added to MSE so a prediction is
    penalised both for missing (MSE, dominant) and for missing far (this term, a gentle
    additional nudge toward ordinal-correct rounding). MSE alone already captures most of the
    ordinal structure quadratically; this term exists mainly to keep the loss well-behaved when
    predictions land exactly between two integers.
    """
    normalized_distance = (pred - target).abs() / 4.0
    return normalized_distance.mean()
