from __future__ import annotations

from collections import Counter
import hashlib
import math
import re

from app.core.config import settings
from app.services.openai_client import build_openai_client, post_openai_compatible_json


STAGE_KEYWORDS = {
    "design": {"设计", "预算", "合同", "报价", "物业", "报备", "开工"},
    "demolition": {"拆改", "拆除", "承重墙", "结构", "垃圾", "保护"},
    "water_electricity": {"水电", "插座", "开关", "打压", "强电", "弱电", "水管", "排水", "地漏"},
    "masonry": {"瓦工", "泥瓦", "防水", "闭水", "瓷砖", "空鼓", "坡度", "阴阳角", "归方", "找平"},
    "carpentry": {"木工", "吊顶", "龙骨", "柜体", "板材", "封边", "检修口"},
    "paint": {"油漆", "乳胶漆", "腻子", "墙面", "顶面", "裂缝", "色差", "阴阳角"},
    "installation": {"安装", "门窗", "洁具", "灯具", "开关", "插座", "地板", "踢脚线", "电器"},
    "completion": {"竣工", "验收", "整改", "尾款", "质保", "资料", "通风"},
    "budget": {"预算", "比价", "采购", "付款", "定金", "尾款", "增项", "凭证", "价格"},
}

ALIASES = {
    "海棠角": {"阳角", "瓷砖", "收口"},
    "止逆阀": {"油烟机", "厨房", "安装"},
    "闭水": {"防水", "渗漏", "卫生间"},
    "打压": {"水管", "水电", "渗漏"},
    "空鼓": {"瓷砖", "墙地砖", "瓦工"},
    "归方": {"阴阳角", "门洞", "墙面"},
    "找平": {"墙面", "地面", "基层"},
}


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", normalized)
    expanded = list(tokens)
    for keyword, related in ALIASES.items():
        if keyword in text:
            expanded.append(keyword)
            expanded.extend(related)
    for keywords in STAGE_KEYWORDS.values():
        for keyword in keywords:
            if keyword in text:
                expanded.append(keyword)
    return expanded


def term_signature(text: str) -> str:
    counts = Counter(tokenize(text))
    return " ".join(f"{term}:{count}" for term, count in sorted(counts.items()))


def parse_term_signature(value: str) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for item in value.split():
        if ":" not in item:
            continue
        term, count = item.rsplit(":", 1)
        try:
            parsed[term] = int(count)
        except ValueError:
            continue
    return parsed


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0
    return dot / (left_norm * right_norm)


def sparse_cosine_similarity(left: dict[str, int], right: dict[str, int]) -> float:
    if not left or not right:
        return 0
    overlap = set(left) & set(right)
    dot = sum(left[term] * right[term] for term in overlap)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0
    return dot / (left_norm * right_norm)


def _local_hash_embedding(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    if not tokens:
        return vector

    for token, count in Counter(tokens).items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * count

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def embed_text(text: str) -> list[float]:
    provider = settings.embedding_provider.lower()
    if provider in {"local", "local_hash", "hash"}:
        return _local_hash_embedding(text, settings.embedding_dimensions)
    if provider in {"openai", "openai_compatible", "api"}:
        client = build_openai_client(
            settings.embedding_api_base,
            settings.resolved_embedding_api_key,
            settings.embedding_timeout_seconds,
        )
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=text,
            encoding_format="float",
        )
        if not response.data:
            raise RuntimeError("嵌入接口返回格式不正确")
        return [float(value) for value in response.data[0].embedding]
    raise RuntimeError(f"不支持的 EMBEDDING_PROVIDER: {settings.embedding_provider}")


def rerank(query: str, documents: list[str]) -> list[float] | None:
    provider = settings.rerank_provider.lower()
    if provider in {"", "none", "off", "disabled"}:
        return None
    if provider not in {"openai_compatible", "api", "bge"}:
        raise RuntimeError(f"不支持的 RERANK_PROVIDER: {settings.rerank_provider}")
    if not settings.rerank_api_base:
        raise RuntimeError("RERANK_API_BASE 未配置")

    payload = post_openai_compatible_json(
        settings.rerank_api_base,
        settings.resolved_rerank_api_key,
        settings.rerank_timeout_seconds,
        "/rerank",
        {"model": settings.rerank_model, "query": query, "documents": documents},
    )
    results = payload.get("results")
    if isinstance(results, list):
        scores = [0.0] * len(documents)
        for item in results:
            index = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            if isinstance(index, int) and 0 <= index < len(scores) and score is not None:
                scores[index] = float(score)
        return scores
    scores = payload.get("scores")
    if isinstance(scores, list) and len(scores) == len(documents):
        return [float(score) for score in scores]
    raise RuntimeError("重排接口返回格式不正确")
