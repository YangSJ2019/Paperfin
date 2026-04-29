"""LLM-based paper quality scoring.

A paper's "quality" is a fuzzy concept — we decompose it into four axes and
ask the LLM to score each on a 0–10 scale, then linearly combine them into a
single 0–100 headline score.

The four axes:

* **innovation (创新性)** – how novel are the ideas vs. prior work?
* **rigor (严谨性)** – experimental design, ablations, statistical care, reproducibility
* **clarity (清晰度)** – how well is the contribution explained, is the writing crisp?
* **significance (重要性)** – likely impact on the field, generality of the ideas

Weights mirror what most reading-group reviewers implicitly care about:

    score_llm = 10 × (0.30·innovation + 0.30·rigor + 0.15·clarity + 0.25·significance)

So the LLM's raw per-axis score is in [0,10], and the final value we persist
on ``Paper.score_llm`` lives in [0,100].

For now the headline ``Paper.score`` is just ``score_llm`` — we'll mix in
institution / venue / h-index scores in a later milestone (see M3 in the plan).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.services.llm import chat_json

log = logging.getLogger(__name__)


# Cap on the prompt text. The abstract + first pages are more than enough
# signal for scoring; don't pay tokens for everything.
MAX_INPUT_CHARS = 14000


class LLMRubricScore(BaseModel):
    """Per-axis rubric scores (0-10 integers) plus a one-liner justification."""

    innovation: int = Field(..., ge=0, le=10, description="0-10 创新性评分")
    rigor: int = Field(..., ge=0, le=10, description="0-10 方法严谨性评分")
    clarity: int = Field(..., ge=0, le=10, description="0-10 表达清晰度评分")
    significance: int = Field(..., ge=0, le=10, description="0-10 重要性/影响力评分")
    reasoning: str = Field(
        ...,
        description=(
            "用 2-4 句中文说明为什么打这些分。要具体,最好能指出一两个"
            "具体的亮点或不足。"
        ),
    )


@dataclass
class QualityScore:
    """Final scoring breakdown persisted on the Paper row."""

    score: float                # composite 0-100
    score_llm: float            # LLM subscore 0-100 (today, same as `score`)
    score_affiliation: float    # placeholder for M3
    score_author_fame: float    # placeholder for M3
    score_venue: float          # placeholder for M3
    rubric: LLMRubricScore


# Weights across the four axes. They sum to 1.0. Tuneable later.
_INNOVATION_W = 0.30
_RIGOR_W = 0.30
_CLARITY_W = 0.15
_SIGNIFICANCE_W = 0.25


SYSTEM_PROMPT = (
    "你是一名经验丰富的论文评审人,正在按照四个维度对一篇论文打分。"
    "你的任务是阅读论文文本(通常包含标题、作者、摘要、方法、实验等节选),"
    "然后根据评审标准用 0-10 的整数给四个维度打分:\n\n"
    "1. innovation (创新性):想法的新颖程度、相对于已有工作的进步幅度。\n"
    "   - 10 = 开创性、改变领域的工作;\n"
    "   - 7-8 = 明确超越已有 SOTA 或提出了新颖框架;\n"
    "   - 4-6 = 在已有框架上做有意义的改进;\n"
    "   - 1-3 = 增量式微调或重复工作;\n"
    "   - 0  = 几乎没有新意。\n\n"
    "2. rigor (严谨性):实验设计、消融、统计、可复现性、基线对比是否充分。\n"
    "   - 10 = 非常完备,多数据集、多基线、多种消融;\n"
    "   - 5-7 = 主要对比齐全但消融偏少或指标有限;\n"
    "   - 1-4 = 有明显遗漏,例如缺少重要基线或数据集。\n\n"
    "3. clarity (清晰度):写作、图表与结构;一位同领域研究者能否轻松读懂。\n\n"
    "4. significance (重要性):对社区/工业界的实际影响力、思想的通用性。\n\n"
    "严格要求:\n"
    "- 四个分数必须是 0-10 的整数。避免一律给 7-8 的'安全分',要有区分度。\n"
    "- 如果论文文本不足以判断某一维度,给一个保守的中间值(5)并在"
    "  reasoning 里明说信息不足。\n"
    "- reasoning 用 2-4 句中文,具体指出亮点或不足,不要空话。\n"
    "- 只返回 JSON,不要任何额外文字。"
)


def _build_user_prompt(text: str, *, title: str | None) -> str:
    trimmed = text[:MAX_INPUT_CHARS]
    header = f"论文标题: {title}\n\n" if title else ""
    return (
        f"{header}"
        "请根据以下论文文本给出 4 个维度 (innovation, rigor, clarity, "
        "significance) 的 0-10 整数评分和一段简短的中文 reasoning。\n\n"
        "--- PAPER TEXT START ---\n"
        f"{trimmed}\n"
        "--- PAPER TEXT END ---"
    )


def score_paper(text: str, *, title: str | None = None) -> QualityScore:
    """Run the LLM rubric and compose the final score.

    Returns a :class:`QualityScore` whose `.score` and `.score_llm` fields
    populate the identically-named columns on ``Paper``. Affiliation / fame /
    venue are left at 0 until we add those signals.
    """
    rubric = chat_json(
        system=SYSTEM_PROMPT,
        user=_build_user_prompt(text, title=title),
        schema=LLMRubricScore,
        max_tokens=800,
    )

    weighted_raw = (
        _INNOVATION_W * rubric.innovation
        + _RIGOR_W * rubric.rigor
        + _CLARITY_W * rubric.clarity
        + _SIGNIFICANCE_W * rubric.significance
    )
    # 10× scales 0-10 → 0-100 for nicer UX (matches how it's displayed).
    score_llm = round(weighted_raw * 10, 1)

    log.info(
        "Scored paper '%s': innovation=%d rigor=%d clarity=%d significance=%d -> score_llm=%.1f",
        title or "?",
        rubric.innovation,
        rubric.rigor,
        rubric.clarity,
        rubric.significance,
        score_llm,
    )

    return QualityScore(
        score=score_llm,
        score_llm=score_llm,
        score_affiliation=0.0,
        score_author_fame=0.0,
        score_venue=0.0,
        rubric=rubric,
    )
