# -*- coding: utf-8 -*-
# Generated by Django 1.9.11 on 2017-03-10 01:13
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('branding', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='branding',
            name='style_sheet',
            field=models.FileField(blank=True, null=True, upload_to=b''),
        ),
    ]
