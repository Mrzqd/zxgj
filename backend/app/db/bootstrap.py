from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings


def should_create_ivfflat_index(dimensions: int) -> bool:
    return dimensions <= 2000


def _validated_dimensions(value: int, name: str) -> int:
    dimensions = int(value)
    if dimensions <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return dimensions


def prepare_database(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    embedding_dimensions = _validated_dimensions(settings.embedding_dimensions, "EMBEDDING_DIMENSIONS")
    embedding_index_dimensions = _validated_dimensions(
        settings.embedding_index_dimensions,
        "EMBEDDING_INDEX_DIMENSIONS",
    )

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        documents_table_exists = connection.execute(text("SELECT to_regclass('public.knowledge_documents')")).scalar()
        if documents_table_exists is not None:
            connection.execute(
                text(
                    "ALTER TABLE IF EXISTS knowledge_documents "
                    "ADD COLUMN IF NOT EXISTS index_status varchar(20) NOT NULL DEFAULT 'pending'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE IF EXISTS knowledge_documents "
                    "ADD COLUMN IF NOT EXISTS index_signature varchar(128)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE IF EXISTS knowledge_documents "
                    "ADD COLUMN IF NOT EXISTS indexed_at timestamp with time zone"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE IF EXISTS knowledge_documents "
                    "ADD COLUMN IF NOT EXISTS index_error text"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_index_status "
                    "ON knowledge_documents (index_status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_index_signature "
                    "ON knowledge_documents (index_signature)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_title_trgm "
                    "ON knowledge_documents USING gin (title gin_trgm_ops)"
                )
            )
            duplicate_documents_sql = (
                "SELECT kd.id "
                "FROM knowledge_documents kd "
                "JOIN knowledge_documents kept "
                "ON kd.id > kept.id "
                "AND kd.source_type = kept.source_type "
                "AND kd.filename = kept.filename "
                "AND kd.project_id IS NOT DISTINCT FROM kept.project_id"
            )
            connection.execute(
                text(
                    "DELETE FROM knowledge_chunks "
                    f"WHERE document_id IN ({duplicate_documents_sql})"
                )
            )
            connection.execute(
                text(
                    "DELETE FROM knowledge_documents "
                    f"WHERE id IN ({duplicate_documents_sql})"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_documents_scope_filename "
                    "ON knowledge_documents (COALESCE(project_id, -1), source_type, filename)"
                )
            )

        table_exists = connection.execute(text("SELECT to_regclass('public.knowledge_chunks')")).scalar()
        if table_exists is None:
            return

        connection.execute(
            text(
                "ALTER TABLE IF EXISTS knowledge_chunks "
                "ADD COLUMN IF NOT EXISTS embedding_provider varchar(80) NOT NULL DEFAULT 'local'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE IF EXISTS knowledge_chunks "
                "ADD COLUMN IF NOT EXISTS embedding_model varchar(120) NOT NULL DEFAULT 'local-hash'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE IF EXISTS knowledge_chunks "
                f"ADD COLUMN IF NOT EXISTS embedding_dimensions integer NOT NULL DEFAULT {embedding_dimensions}"
            )
        )
        vector_type = f"vector({embedding_dimensions})"
        current_vector_type = connection.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "WHERE a.attrelid = 'public.knowledge_chunks'::regclass "
                "AND a.attname = 'embedding_vector' "
                "AND NOT a.attisdropped"
            )
        ).scalar()
        if current_vector_type is None:
            connection.execute(
                text(
                    "ALTER TABLE IF EXISTS knowledge_chunks "
                    f"ADD COLUMN IF NOT EXISTS embedding_vector {vector_type}"
                )
            )
        elif current_vector_type != vector_type:
            connection.execute(text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_vector"))
            connection.execute(
                text(
                    "ALTER TABLE knowledge_chunks "
                    f"ALTER COLUMN embedding_vector TYPE {vector_type} USING NULL"
                )
            )
            connection.execute(text("UPDATE knowledge_chunks SET embedding_dimensions = :dimensions"), {"dimensions": 0})

        connection.execute(text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_vector"))
        if should_create_ivfflat_index(embedding_dimensions):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_vector "
                    "ON knowledge_chunks USING ivfflat (embedding_vector vector_cosine_ops) "
                    "WITH (lists = 32)"
                )
            )

        connection.execute(
            text(
                "ALTER TABLE IF EXISTS knowledge_chunks "
                f"ADD COLUMN IF NOT EXISTS embedding_index_dimensions integer NOT NULL DEFAULT {embedding_index_dimensions}"
            )
        )
        index_vector_type = f"vector({embedding_index_dimensions})"
        current_index_vector_type = connection.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "WHERE a.attrelid = 'public.knowledge_chunks'::regclass "
                "AND a.attname = 'embedding_index_vector' "
                "AND NOT a.attisdropped"
            )
        ).scalar()
        if current_index_vector_type is None:
            connection.execute(
                text(
                    "ALTER TABLE IF EXISTS knowledge_chunks "
                    f"ADD COLUMN IF NOT EXISTS embedding_index_vector {index_vector_type}"
                )
            )
        elif current_index_vector_type != index_vector_type:
            connection.execute(text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_index_vector"))
            connection.execute(
                text(
                    "ALTER TABLE knowledge_chunks "
                    f"ALTER COLUMN embedding_index_vector TYPE {index_vector_type} USING NULL"
                )
            )
            connection.execute(
                text("UPDATE knowledge_chunks SET embedding_index_dimensions = :dimensions"),
                {"dimensions": 0},
            )

        connection.execute(text("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_index_vector"))
        if should_create_ivfflat_index(embedding_index_dimensions):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_index_vector "
                    "ON knowledge_chunks USING ivfflat (embedding_index_vector vector_cosine_ops) "
                    "WITH (lists = 32)"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_terms_trgm "
                "ON knowledge_chunks USING gin (terms gin_trgm_ops)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_heading_trgm "
                "ON knowledge_chunks USING gin (heading gin_trgm_ops)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_content_trgm "
                "ON knowledge_chunks USING gin (content gin_trgm_ops)"
            )
        )
