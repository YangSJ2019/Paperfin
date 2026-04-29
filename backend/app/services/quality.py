"""LLM-based paper quality scoring.

A paper's "quality" is a fuzzy concept — we decompose it into four axes and
ask the LLM to score each on a 0–10 scale, then linearly combine them into a
single 0–100 headline score.

The four axes:

* **innovation** – how novel are the ideas vs. prior work?
* **rigor** – experimental design, ablations, statistical care, reproducibility
* **clarity** – how well is the contribution explained, is the writing crisp?
* **significance** – likely impact on the field, generality of the ideas

Weights mirror what most reading-group reviewers implicitly care about:

    score_llm = 10 × (0.30·innovation + 0.30·rigor + 0.15·clarity + 0.25·significance)

So the LLM's raw per-axis score is in [0,10], and the final value we persist
on ``Paper.score_llm`` lives in [0,100].

For now the headline ``Paper.score`` is just ``score_llm`` — we'll mix in
institution / venue / h-index scores in a later milestone (see M3 in the plan).

The written rationale follows ``Settings.summary_language``; numerical scores
are language-independent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.llm import chat_json

log = logging.getLogger(__name__)


# Cap on the prompt text. The abstract + first pages are more than enough
# signal for scoring; don't pay tokens for everything.
MAX_INPUT_CHARS = 14000


class LLMRubricScore(BaseModel):
    """Per-axis rubric scores (0-10 integers) plus a one-liner justification."""

    innovation: int = Field(..., ge=0, le=10, description="0-10 innovation score")
    rigor: int = Field(..., ge=0, le=10, description="0-10 methodological rigor score")
    clarity: int = Field(..., ge=0, le=10, description="0-10 clarity score")
    significance: int = Field(..., ge=0, le=10, description="0-10 significance score")
    reasoning: str = Field(
        ...,
        description=(
            "2-4 sentences explaining the scores. Should call out at least one "
            "concrete strength or weakness."
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


# -- Per-language prompt templates -------------------------------------------
#
# The rubric itself (axes, weights, score ranges) is language-independent.
# Only the wording of the system prompt and the target language of the
# ``reasoning`` field change.


_SYSTEM_EN = (
    "You are an experienced paper reviewer scoring a submission across four "
    "axes. Read the paper text (typically title, authors, abstract, methods, "
    "and experiments) and assign an integer 0-10 score on each axis:\n\n"
    "1. innovation — how novel are the ideas vs. prior work?\n"
    "   - 10 = paradigm-shifting, field-changing work\n"
    "   - 7-8 = clearly beats SOTA, or proposes a genuinely new framework\n"
    "   - 4-6 = meaningful improvement on an existing framework\n"
    "   - 1-3 = incremental tweaks or near-duplicate work\n"
    "   - 0   = essentially nothing new\n\n"
    "2. rigor — experimental design, ablations, statistical care, "
    "reproducibility, baseline coverage.\n"
    "   - 10 = very thorough: multiple datasets, multiple baselines, many "
    "ablations\n"
    "   - 5-7 = main comparisons present but ablations or metrics are limited\n"
    "   - 1-4 = clear gaps (missing important baselines or datasets)\n\n"
    "3. clarity — writing, figures, structure; could a peer in the field read "
    "this easily?\n\n"
    "4. significance — likely impact on the community/industry; generality of "
    "the ideas.\n\n"
    "Strict requirements:\n"
    "- All four scores must be integers in [0, 10]. Avoid flat 7-8 'safe "
    "scores' — differentiate.\n"
    "- If the paper text isn't enough to judge an axis, give a conservative 5 "
    "and say 'insufficient information' in reasoning.\n"
    "- Write reasoning in 2-4 English sentences, pointing at a concrete "
    "strength or weakness. No fluff.\n"
    "- Return ONLY a JSON object."
)


_SYSTEM_ZH = (
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


def _user_en(text: str, title: str | None) -> str:
    header = f"Paper title: {title}\n\n" if title else ""
    return (
        f"{header}"
        "Score the following paper across the four axes (innovation, rigor, "
        "clarity, significance) as integers 0-10 and provide a short "
        "English reasoning.\n\n"
        "--- PAPER TEXT START ---\n"
        f"{text}\n"
        "--- PAPER TEXT END ---"
    )


def _user_zh(text: str, title: str | None) -> str:
    header = f"论文标题: {title}\n\n" if title else ""
    return (
        f"{header}"
        "请根据以下论文文本给出 4 个维度 (innovation, rigor, clarity, "
        "significance) 的 0-10 整数评分和一段简短的中文 reasoning。\n\n"
        "--- PAPER TEXT START ---\n"
        f"{text}\n"
        "--- PAPER TEXT END ---"
    )


_PROMPTS: dict[str, dict] = {
    "en": {"system": _SYSTEM_EN, "user": _user_en},
    "zh": {"system": _SYSTEM_ZH, "user": _user_zh},
}


def score_paper(text: str, *, title: str | None = None) -> QualityScore:
    """Run the LLM rubric and compose the final score.

    Returns a :class:`QualityScore` whose `.score` and `.score_llm` fields
    populate the identically-named columns on ``Paper``. Affiliation / fame /
    venue are left at 0 until we add those signals.

    Language of the rubric's reasoning text follows
    ``Settings.summary_language``; the numeric scores themselves are
    language-independent.
    """
    trimmed = text[:MAX_INPUT_CHARS]
    lang = get_settings().summary_language.lower()
    prompt = _PROMPTS.get(lang, _PROMPTS["en"])

    rubric = chat_json(
        system=prompt["system"],
        user=prompt["user"](trimmed, title),
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
