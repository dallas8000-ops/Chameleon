import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studio", "0005_audio_assets_and_ai_disclosure"),
    ]

    operations = [
        migrations.AddField(
            model_name="character",
            name="voice_sample_asset",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="studio.asset",
            ),
        ),
    ]
