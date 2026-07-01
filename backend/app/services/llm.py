from app.core.config import settings
from app.services.openai_client import build_openai_client


ChatHistoryMessage = dict[str, str]


SYSTEM_PROMPT = """你是装修管家的 AI 助手，只回答装修、采购、验收、预算、工期相关问题。
必须优先依据用户知识库引用内容回答；不要编造未在引用中出现的规范条文、价格或承诺。
如果引用不足，明确说明资料不足，并给出需要补充的资料。
回答要简洁、可执行，适合移动端阅读。
如果用户追问“这个”“上面”“继续”等上下文相关问题，结合最近对话理解指代。"""


def _format_history(history: list[ChatHistoryMessage]) -> str:
    if not history:
        return "无"
    role_label = {"user": "用户", "assistant": "助手"}
    lines = []
    for message in history[-8:]:
        role = role_label.get(message.get("role", ""), "消息")
        content = message.get("content", "").strip()
        if content:
            lines.append(f"{role}：{content[:800]}")
    return "\n".join(lines) if lines else "无"


def generate_answer(question: str, contexts: list[str], history: list[ChatHistoryMessage] | None = None) -> str | None:
    provider = settings.llm_provider.lower()
    if provider in {"", "none", "off", "disabled"}:
        return None
    if provider not in {"openai", "openai_compatible", "api"}:
        raise RuntimeError(f"不支持的 LLM_PROVIDER: {settings.llm_provider}")
    if not settings.llm_model:
        raise RuntimeError("LLM_MODEL 未配置")

    response = _create_chat_completion(question, contexts, history or [], stream=False)
    if not response.choices:
        raise RuntimeError("LLM 接口返回格式不正确")
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM 接口未返回回答内容")
    return content.strip()


def rewrite_search_query(question: str, history: list[ChatHistoryMessage] | None = None) -> str | None:
    provider = settings.llm_provider.lower()
    if provider in {"", "none", "off", "disabled"}:
        return None
    if provider not in {"openai", "openai_compatible", "api"}:
        raise RuntimeError(f"不支持的 LLM_PROVIDER: {settings.llm_provider}")
    if not settings.llm_model:
        raise RuntimeError("LLM_MODEL 未配置")

    history_text = _format_history(history or [])
    prompt = f"""最近对话：
{history_text}

用户当前问题：{question}

请把用户当前问题改写成一个独立的装修知识库检索问题。只输出改写后的问题，不要解释。"""
    client = build_openai_client(settings.llm_api_base, settings.resolved_llm_api_key, settings.llm_timeout_seconds)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": "你只负责改写检索问题，输出必须简洁、完整、可用于知识库检索。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=120,
    )
    if not response.choices:
        return None
    content = response.choices[0].message.content
    return content.strip() if content else None


def stream_answer(question: str, contexts: list[str], history: list[ChatHistoryMessage] | None = None):
    provider = settings.llm_provider.lower()
    if provider in {"", "none", "off", "disabled"}:
        return
    if provider not in {"openai", "openai_compatible", "api"}:
        raise RuntimeError(f"不支持的 LLM_PROVIDER: {settings.llm_provider}")
    if not settings.llm_model:
        raise RuntimeError("LLM_MODEL 未配置")

    stream = _create_chat_completion(question, contexts, history or [], stream=True)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def build_user_prompt(question: str, contexts: list[str], history: list[ChatHistoryMessage] | None = None) -> str:
    context_text = "\n\n".join(contexts)
    history_text = _format_history(history or [])
    return f"""最近对话：
{history_text}

用户当前问题：{question}

知识库引用：
{context_text}

请结合最近对话理解用户当前问题，但事实依据必须来自知识库引用。回答结尾用“参考资料”列出引用序号。"""


def _create_chat_completion(
    question: str,
    contexts: list[str],
    history: list[ChatHistoryMessage],
    *,
    stream: bool,
):
    client = build_openai_client(settings.llm_api_base, settings.resolved_llm_api_key, settings.llm_timeout_seconds)
    return client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(question, contexts, history)},
        ],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        stream=stream,
    )
