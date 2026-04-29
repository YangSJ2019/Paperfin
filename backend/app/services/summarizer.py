"""LLM-backed paper summarization.

Given the text of a paper (abstract + optional intro/conclusion excerpts), ask
the LLM to produce a compact, structured summary that feeds the detail page.

The summary is three short paragraphs (contribution / method / result) plus a
small tag list, **written in Simplified Chinese** for UI consistency. Keeping
it structured lets the frontend render consistent cards.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.llm import chat_json

# Upper bound for prompt text. Most papers have enough signal in abstract + first
# ~12k chars to summarize well, without blowing past context windows on smaller models.
MAX_INPUT_CHARS = 12000


class PaperSummary(BaseModel):
    """Structured summary attached to each Paper. All fields in Simplified Chinese."""

    contribution: str = Field(
        ...,
        description=(
            "核心贡献点,用中文写 3-6 句。说清楚:论文解决了什么具体问题、"
            "提出了什么具体的新东西(模型/算法/理论/数据集)、和先前最强工作相比"
            "新颖之处在哪里。要具体到机制层面,避免'首次提出'、'重大突破'这类空话。"
        ),
    )
    method: str = Field(
        ...,
        description=(
            "技术方法,用中文写 4-8 句。包括:模型架构/算法流程的关键组件、"
            "训练或推理的数据与优化目标、关键超参或设计选择、使用的数据集规模。"
            "最好能让读者仅凭这段就大致复现思路。"
        ),
    )
    result: str = Field(
        ...,
        description=(
            "关键结果与意义,用中文写 3-6 句。列出代表性数据(benchmark / 指标 / "
            "相对提升),指出最能说明论文价值的消融或对比结论;再用 1 句说清楚"
            "'这结果为什么重要'、对后续研究意味着什么。不要堆形容词。"
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        description="3-7 个中文主题标签,每个 2-6 字短词,不要用英文。",
    )


SYSTEM_PROMPT = (
    "你是一位资深的 ML/CS 研究员,正在为读书会撰写深度论文速读笔记。"
    "给定论文文本,请输出一份结构化总结,包含三段较为详细的中文说明("
    "contribution 贡献点 / method 方法 / result 结果)和一个简短的主题标签列表。\n\n"
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
)


def summarize(text: str, *, title: str | None = None) -> PaperSummary:
    """Run the summarization LLM call."""
    trimmed = text[:MAX_INPUT_CHARS]
    header = f"论文标题: {title}\n\n" if title else ""
    user = (
        f"{header}"
        "请仔细阅读以下论文文本,返回 JSON 对象,字段: contribution, method, "
        "result, tags。所有字段必须用简体中文书写,篇幅参考 schema 描述。\n\n"
        "--- PAPER TEXT START ---\n"
        f"{trimmed}\n"
        "--- PAPER TEXT END ---"
    )
    # max_tokens bumped to accommodate longer Chinese output (Chinese is denser
    # per-token than English, but 3-6 sentences × 3 paragraphs still benefits
    # from the extra headroom).
    return chat_json(system=SYSTEM_PROMPT, user=user, schema=PaperSummary, max_tokens=3500)
