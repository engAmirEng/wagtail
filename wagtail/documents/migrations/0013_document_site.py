# Generated by Django 4.2.1 on 2023-05-08 06:21

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("wagtailcore", "0084_merge_20230305_1030"),
        ("wagtaildocs", "0012_uploadeddocument"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="site",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="site_%(class)s",
                to="wagtailcore.site",
            ),
            preserve_default=False,
        ),
    ]