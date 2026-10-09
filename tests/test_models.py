from app.db.models import EMBEDDING_DIM, Base

# ROADMAP.md section 5
EXPECTED_COLUMNS = {
    "shoes": {
        "id",
        "brand",
        "model",
        "version",
        "category",
        "drop_mm",
        "stack_heel_mm",
        "stack_forefoot_mm",
        "weight_g",
        "widths_available",
        "toe_box",
        "upper_volume",
        "heel_lock",
        "price_usd",
    },
    "fit_notes": {"id", "shoe_id", "source", "text", "embedding"},
    "size_charts": {"id", "brand", "us_size", "length_mm_min", "length_mm_max", "sizing_note"},
    "offers": {
        "id",
        "shoe_id",
        "retailer",
        "us_size",
        "width",
        "price_usd",
        "in_stock",
        "affiliate_url",
        "updated_at",
    },
    "users": {"id", "foot_profile", "questionnaire", "created_at"},
    "scans": {"id", "user_id", "raw_file_path", "parsed_profile", "parser_version", "created_at"},
    "tasks": {"id", "user_id", "status", "result", "error", "created_at"},
    "feedback": {
        "id",
        "user_id",
        "shoe_id",
        "us_size",
        "width",
        "rating",
        "notes",
        "created_at",
    },
}


def test_tables_match_roadmap():
    actual = {name: set(table.columns.keys()) for name, table in Base.metadata.tables.items()}
    assert actual == EXPECTED_COLUMNS


def test_fit_note_embedding_is_hnsw_cosine():
    table = Base.metadata.tables["fit_notes"]
    assert table.c.embedding.type.dim == EMBEDDING_DIM == 384
    (index,) = [i for i in table.indexes if i.name == "ix_fit_notes_embedding_hnsw"]
    assert index.dialect_options["postgresql"]["using"] == "hnsw"
    assert index.dialect_options["postgresql"]["ops"] == {"embedding": "vector_cosine_ops"}
