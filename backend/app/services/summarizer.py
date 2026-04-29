"""LLM-backed paper summarization.

Given the text of a paper (abstract + optional intro/conclusion excerpts), ask
the LLM to produce a compact, structured summary that feeds the detail page.

The summary is three short paragraphs (contribution / method / result) plus a
small tag list. Keeping it structured lets the frontend render consistent
cards.

Output language is controlled by ``Settings.summary_language`` — English by
default, Simplified Chinese when set to ``"zh"``. Adding more languages means
adding one more prompt block in :data:`_PROMPTS`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.llm import chat_json

# Upper bound for prompt text. Most papers have enough signal in abstract + first
# ~12k chars to summarize well, without blowing past context windows on smaller models.
MAX_INPUT_CHARS = 12000


class PaperSummary(BaseModel):
    """Structured summary attached to each Paper."""

    contribution: str = Field(
        ...,
        description="Core contribution: 3-6 sentences, specific, no hype.",
    )
    method: str = Field(
        ...,
        description="Technical approach or experimental setup: 4-8 sentences.",
    )
    result: str = Field(
        ...,
        description="Key findings and their significance: 3-6 sentences.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="3-7 short topical tags.",
    )


# -- Per-language prompt templates -------------------------------------------
#
# Each entry provides the system prompt and a function that builds the user
# prompt. Output format (the JSON schema) is language-agnostic — we only vary
# the instructions and the target writing language.


def _user_en(text: str, title: str | None) -> str:
    header = f"Paper title: {title}\n\n" if title else ""
    return (
        f"{header}"
        "Read the paper text below carefully and return a JSON object with "
        "keys: contribution, method, result, tags. Write each field in "
        "English at the length suggested by the schema.\n\n"
        "--- PAPER TEXT START ---\n"
        f"{text}\n"
        "--- PAPER TEXT END ---"
    )


def _user_zh(text: str, title: str | None) -> str:
    header = f"论文标题: {title}\n\n" if title else ""
    return (
        f"{header}"
        "请仔细阅读以下论文文本,返回 JSON 对象,字段: contribution, method, "
        "result, tags。所有字段必须用简体中文书写,篇幅参考 schema 描述。\n\n"
        "--- PAPER TEXT START ---\n"
        f"{text}\n"
        "--- PAPER TEXT END ---"
    )


_PROMPTS: dict[str, dict] = {
    "en": {
        "system": (
            "You are a senior ML/CS researcher writing a deep reading-group "
            "digest of a paper. Given the paper's text, produce a structured "
            "summary with three substantive paragraphs (contribution, method, "
            "result) and a short list of topical tags.\n\n"
            "Strict requirements:\n"
            "- Write every field in English.\n"
            "- Each paragraph should be concrete and technically specific. "
            "  Prefer exact numbers, dataset names, baseline names, and "
            "  architecture details over vague summary sentences like "
            "  'achieves significant improvements'.\n"
            "- No hype, no marketing voice. Write the way you would explain "
            "  the paper to a fellow researcher.\n"
            "- Tags are short lowercase topical phrases (e.g. 'self-attention', "
            "  'retrieval augmented generation', 'diffusion'); 3–7 of them."
        ),
        "user": _user_en,
    },
    "zh": {
        "system": (
            "你是一位资深的 ML/CS 研究员,正在为读书会撰写深度论文速读笔记。"
            "给定论文文本,请输出一份结构化总结,包含三段较为详细的中文说明"
            "(contribution 贡献点 / method 方法 / result 结果)和一个简短的主题标签列表。\n\n"
            "严格要求:\n"
            "- 所有字段一律使用简体中文。即使论文原文是英文,总结也必须翻译成中文。\n"
            "- 每一段要写得具体、有血有肉。宁愿多给技术细节、具体数字、数据集、"
            "  baseline 名称,也不要写空洞的总结句(例如避免'取得了显著提升'这类"
            "  没有具体数字的表达)。\n"
            "- 技术术语首次出现时可以附带英文原文,例如 Transformer 可写成 "
            "  'Transformer 架构'、BLEU 分数等保留英文缩写。但不要整句英文。\n"
            "- 不要营销腔、不要堆砌形容词。像向一位也做研究的朋友讲这篇论文。\n"
            "- tags 为中文短词(如 '自注意力'、'检索增强'、'扩散模型'),不要写英文 "
            "  连字符单词(如 'self-attention')。"
        ),
        "user": _user_zh,
    },
}


def summarize(text: str, *, title: str | None = None) -> PaperSummary:
    """Run the summarization LLM call.

    Picks the prompt template based on ``Settings.summary_language``. Unknown
    languages silently fall back to English so a typo in ``.env`` never kills
    the pipeline.
    """
    trimmed = text[:MAX_INPUT_CHARS]
    lang = get_settings().summary_language.lower()
    prompt = _PROMPTS.get(lang, _PROMPTS["en"])

    return chat_json(
        system=prompt["system"],
        user=prompt["user"](trimmed, title),
        schema=PaperSummary,
        # Chinese is roughly 2-3× denser per-token than English, so the Chinese
        # prompt benefits from extra headroom; giving it to both is harmless.
        max_tokens=3500,
    )
