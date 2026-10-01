"""Persistent, permission-filtered embedding search in SQLite or Postgres."""
import hashlib
import json
import math

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (Column, Float, Index, JSON, MetaData, String, Table,
                        delete, event, func, select, text)

DIMENSIONS = 768
metadata = MetaData()
chunks = Table(
    "rag_chunks", metadata,
    Column("id", String(300), primary_key=True),
    Column("team", String(80), nullable=False),
    Column("channel", String(80), nullable=False),
    Column("project", String(100), nullable=False),
    Column("model", String(100), nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("embedding", VECTOR(DIMENSIONS).with_variant(JSON, "sqlite"), nullable=False),
)
Index("rag_chunks_scope", chunks.c.team, chunks.c.channel, chunks.c.project, chunks.c.model)


def fingerprint(doc, model):
    return hashlib.sha256((model + "\n" + doc["text"]).encode()).hexdigest()


def normalize(vector):
    if len(vector) != DIMENSIONS or any(not math.isfinite(float(x)) for x in vector):
        raise ValueError(f"Expected {DIMENSIONS} finite embedding dimensions")
    norm = math.sqrt(sum(float(x) ** 2 for x in vector))
    if norm == 0:
        raise ValueError("Embedding must not be a zero vector")
    return [float(x) / norm for x in vector]


def load_sqlite_vectors(connection, _record):
    import sqlite_vec
    connection.enable_load_extension(True)
    try:
        sqlite_vec.load(connection)
    finally:
        connection.enable_load_extension(False)


class VectorIndex:
    def __init__(self, engine):
        self.engine = engine
        self.backend = engine.dialect.name
        if self.backend == "sqlite":
            # Checkout also covers connections already created by the record store.
            if not getattr(engine, "_digest_vec_loaded", False):
                def on_checkout(connection, record, _proxy):
                    load_sqlite_vectors(connection, record)
                # Keep the listener marker on this engine, not global process state.
                event.listen(engine, "checkout", on_checkout)
                engine._digest_vec_loaded = True
        elif self.backend == "postgresql":
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        else:
            raise ValueError("Vector search supports SQLite or PostgreSQL")
        metadata.create_all(engine)
        if self.backend == "postgresql":
            with engine.begin() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS rag_chunks_hnsw ON rag_chunks USING hnsw (embedding vector_cosine_ops)"))

    def sync(self, team, channels, projects, docs, model, embed, reuse=None):
        """Embed changed accessible chunks; reconcile stale rows within that scope."""
        if not channels or not projects:
            return {"embedded": 0, "reused": 0, "unchanged": 0, "removed": 0}
        scope = (chunks.c.team == team, chunks.c.channel.in_(channels), chunks.c.project.in_(projects))
        with self.engine.connect() as conn:
            existing = {r.id: r.fingerprint for r in conn.execute(select(chunks.c.id, chunks.c.fingerprint).where(*scope))}
        stats = {"embedded": 0, "reused": 0, "unchanged": 0, "removed": 0}
        docs = [d for d in docs if d["channel"] in channels and d["project"] in projects]
        for doc in docs:
            stamp = fingerprint(doc, model)
            if existing.get(doc["id"]) == stamp:
                stats["unchanged"] += 1
                continue
            vector = reuse(doc) if reuse else None
            if vector is not None and len(vector) == DIMENSIONS:
                stats["reused"] += 1
            else:
                vector = embed(doc["text"])
                stats["embedded"] += 1
            values = dict(id=doc["id"], team=team, channel=doc["channel"], project=doc["project"],
                          model=model, fingerprint=stamp, embedding=normalize(vector))
            # Atomic upsert; each completed chunk survives a later provider failure.
            if self.backend == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                from sqlalchemy.dialects.postgresql import insert
            stmt = insert(chunks).values(**values)
            with self.engine.begin() as conn:
                conn.execute(stmt.on_conflict_do_update(index_elements=[chunks.c.id], set_=values))
        valid = {d["id"] for d in docs}
        stale = set(existing) - valid
        if stale:
            with self.engine.begin() as conn:
                conn.execute(delete(chunks).where(*scope, chunks.c.id.in_(stale)))
            stats["removed"] = len(stale)
        return stats

    def search(self, team, channels, projects, model, vector, valid_ids, limit=12):
        if not channels or not projects or not valid_ids:
            return []
        vector = normalize(vector)
        if self.backend == "postgresql":
            distance = chunks.c.embedding.cosine_distance(vector)
        else:
            distance = func.vec_distance_cosine(chunks.c.embedding, json.dumps(vector), type_=Float)
        # ACL filters and current-source IDs apply before LIMIT in the database.
        stmt = select(chunks.c.id, distance.label("distance")).where(
            chunks.c.team == team, chunks.c.channel.in_(channels),
            chunks.c.project.in_(projects), chunks.c.model == model,
            chunks.c.id.in_(valid_ids)).order_by(distance).limit(limit)
        with self.engine.connect() as conn:
            return [(r.id, 1.0 - float(r.distance)) for r in conn.execute(stmt)]

    def count(self):
        with self.engine.connect() as conn:
            return conn.scalar(select(func.count()).select_from(chunks))
