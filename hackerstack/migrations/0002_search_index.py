from django.db import migrations


def create_index(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        statements = [
            "CREATE VIRTUAL TABLE hackerstack_fts USING fts5(search_text, content='hackerstack_resource', content_rowid='id')",
            "CREATE TRIGGER hs_search_insert AFTER INSERT ON hackerstack_resource BEGIN INSERT INTO hackerstack_fts(rowid,search_text) VALUES(new.id,new.search_text); END",
            "CREATE TRIGGER hs_search_delete AFTER DELETE ON hackerstack_resource BEGIN INSERT INTO hackerstack_fts(hackerstack_fts,rowid,search_text) VALUES('delete',old.id,old.search_text); END",
            "CREATE TRIGGER hs_search_update AFTER UPDATE OF search_text ON hackerstack_resource BEGIN INSERT INTO hackerstack_fts(hackerstack_fts,rowid,search_text) VALUES('delete',old.id,old.search_text); INSERT INTO hackerstack_fts(rowid,search_text) VALUES(new.id,new.search_text); END",
            "INSERT INTO hackerstack_fts(hackerstack_fts) VALUES('rebuild')",
        ]
    elif schema_editor.connection.vendor == "postgresql":
        statements = [
            "CREATE INDEX hs_search_gin ON hackerstack_resource USING gin (to_tsvector('simple'::regconfig, COALESCE(search_text, '')))"
        ]
    else:
        raise RuntimeError("HackerStack requires SQLite with FTS5 or PostgreSQL")
    for sql in statements:
        schema_editor.execute(sql)


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        for name in ("hs_search_insert", "hs_search_delete", "hs_search_update"):
            schema_editor.execute("DROP TRIGGER IF EXISTS " + name)
        schema_editor.execute("DROP TABLE IF EXISTS hackerstack_fts")
    elif schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS hs_search_gin")


class Migration(migrations.Migration):
    dependencies = [("hackerstack", "0001_initial")]
    operations = [migrations.RunPython(create_index, drop_index)]
