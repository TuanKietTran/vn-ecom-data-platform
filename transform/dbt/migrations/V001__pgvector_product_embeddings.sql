-- Versioned PostgreSQL/pgvector schema contract for the configurable embedding store.
-- Deliberately use unconstrained `vector`: embedding_dimensions is configured by
-- the application, and PostgreSQL's vector(n) typmod would bake one value here.
-- PgVectorStore enforces the configured dimension on writes and queries.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS product_embeddings (
    document_id text PRIMARY KEY,
    text text NOT NULL,
    content_hash text NOT NULL,
    metadata jsonb NOT NULL,
    embedding vector NOT NULL
);

CREATE INDEX IF NOT EXISTS product_embeddings_embedding_hnsw
    ON product_embeddings USING hnsw (embedding vector_cosine_ops);
