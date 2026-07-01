from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "装修管家"
    api_prefix: str = "/api"
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60 * 24 * 7, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    database_url: str = Field(
        default="postgresql+psycopg://renovation:renovation@db:5432/renovation",
        alias="DATABASE_URL",
    )
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    s3_bucket: str = Field(default="renovation-assets", alias="S3_BUCKET")
    s3_public_base_url: str | None = Field(default=None, alias="S3_PUBLIC_BASE_URL")
    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    max_upload_mb: int = Field(default=10, alias="MAX_UPLOAD_MB")

    modelscope_api_key: str | None = Field(default=None, alias="MODELSCOPE_API_KEY")

    embedding_provider: str = Field(default="openai_compatible", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="Qwen/Qwen3-Embedding-8B", alias="EMBEDDING_MODEL")
    embedding_api_base: str | None = Field(default=None, alias="EMBEDDING_API_BASE")
    embedding_api_key: str | None = Field(default=None, alias="EMBEDDING_API_KEY")
    embedding_dimensions: int = Field(default=4096, alias="EMBEDDING_DIMENSIONS")
    embedding_index_dimensions: int = Field(default=1536, alias="EMBEDDING_INDEX_DIMENSIONS")
    embedding_timeout_seconds: float = Field(default=20, alias="EMBEDDING_TIMEOUT_SECONDS")

    rerank_provider: str = Field(default="openai_compatible", alias="RERANK_PROVIDER")
    rerank_model: str | None = Field(default="bge-reranker-v2.5-gemma2-lightweight", alias="RERANK_MODEL")
    rerank_api_base: str | None = Field(default=None, alias="RERANK_API_BASE")
    rerank_api_key: str | None = Field(default=None, alias="RERANK_API_KEY")
    rerank_timeout_seconds: float = Field(default=20, alias="RERANK_TIMEOUT_SECONDS")
    rag_candidate_limit: int = Field(default=24, alias="RAG_CANDIDATE_LIMIT")
    rag_context_max_chars: int = Field(default=9000, alias="RAG_CONTEXT_MAX_CHARS")
    rag_context_per_source_max_chars: int = Field(default=2400, alias="RAG_CONTEXT_PER_SOURCE_MAX_CHARS")
    rag_neighbor_window: int = Field(default=1, alias="RAG_NEIGHBOR_WINDOW")
    knowledge_chunk_target_chars: int = Field(default=1800, alias="KNOWLEDGE_CHUNK_TARGET_CHARS")
    knowledge_chunk_max_chars: int = Field(default=3200, alias="KNOWLEDGE_CHUNK_MAX_CHARS")
    knowledge_embedding_max_chars: int = Field(default=12000, alias="KNOWLEDGE_EMBEDDING_MAX_CHARS")

    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    rq_queue_name: str = Field(default="knowledge-index", alias="RQ_QUEUE_NAME")

    llm_provider: str = Field(default="none", alias="LLM_PROVIDER")
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")
    llm_api_base: str | None = Field(default=None, alias="LLM_API_BASE")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_timeout_seconds: float = Field(default=45, alias="LLM_TIMEOUT_SECONDS")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=900, alias="LLM_MAX_TOKENS")

    mineru_api_base: str = Field(default="https://mineru.net", alias="MINERU_API_BASE")
    mineru_api_token: str | None = Field(default=None, alias="MINERU_API_TOKEN")
    mineru_model_version: str = Field(default="pipeline", alias="MINERU_MODEL_VERSION")
    mineru_timeout_seconds: float = Field(default=60, alias="MINERU_TIMEOUT_SECONDS")
    mineru_download_timeout_seconds: float = Field(default=300, alias="MINERU_DOWNLOAD_TIMEOUT_SECONDS")
    mineru_poll_interval_seconds: float = Field(default=5, alias="MINERU_POLL_INTERVAL_SECONDS")
    mineru_poll_timeout_seconds: float = Field(default=900, alias="MINERU_POLL_TIMEOUT_SECONDS")
    mineru_retry_attempts: int = Field(default=3, alias="MINERU_RETRY_ATTEMPTS")
    mineru_retry_backoff_seconds: float = Field(default=2, alias="MINERU_RETRY_BACKOFF_SECONDS")
    mineru_download_retry_attempts: int = Field(default=8, alias="MINERU_DOWNLOAD_RETRY_ATTEMPTS")
    mineru_download_retry_backoff_seconds: float = Field(default=3, alias="MINERU_DOWNLOAD_RETRY_BACKOFF_SECONDS")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_embedding_api_key(self) -> str | None:
        return self.embedding_api_key or self.modelscope_api_key

    @property
    def resolved_rerank_api_key(self) -> str | None:
        return self.rerank_api_key or self.modelscope_api_key

    @property
    def resolved_llm_api_key(self) -> str | None:
        return self.llm_api_key or self.modelscope_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
