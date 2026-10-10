from django.db import migrations

LEGACY_TABLES = [
    "jobs_usageledgerentry",
    "jobs_providerevent",
    "jobs_generatedfilecandidate",
    "jobs_generationquote",
    "jobs_generationjob",
]


def drop_legacy_tables(apps, schema_editor):
    connection = schema_editor.connection
    existing = set(connection.introspection.table_names())
    cascade = " CASCADE" if connection.vendor == "postgresql" else ""
    for table in LEGACY_TABLES:
        if table in existing:
            schema_editor.execute(f"DROP TABLE {schema_editor.quote_name(table)}{cascade}")
    if "django_migrations" in existing:
        schema_editor.execute("DELETE FROM django_migrations WHERE app = 'jobs'")


class Migration(migrations.Migration):
    dependencies = [
        ("studio", "0002_export"),
    ]

    operations = [
        migrations.RunPython(drop_legacy_tables, migrations.RunPython.noop),
    ]
