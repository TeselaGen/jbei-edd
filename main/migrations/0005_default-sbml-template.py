# -*- coding: utf-8 -*-
# Generated by Django 1.9.13 on 2017-05-25 19:13
from __future__ import unicode_literals

import os

from django.apps import apps as django_apps
from django.core.files import File
from django.db import migrations

from main.models import SBMLTemplate as RealSBMLTemplate
from main.signals.handlers import template_sync_species


def add_template(apps, schema_editor):
    """
    Adds the default SBML template for EDD tutorial.
    """
    # define models
    SBMLTemplate = apps.get_model('main', 'SBMLTemplate')
    Attachment = apps.get_model('main', 'Attachment')
    Update = apps.get_model('main', 'Update')
    # get the bootstrap update object
    beginning = Update.objects.get(pk=1)
    # load template file
    conf = django_apps.get_app_config('main')
    fixture_dir = os.path.join(conf.path, 'fixtures')
    template_file = os.path.join(fixture_dir, 'StdEciJO1366.xml')
    with open(template_file, 'rb') as fp:
        django_file = File(fp)
        # Create objects
        template = SBMLTemplate(
            name="StdEciJO1366",
            description="JO1366 with standardized names",
            uuid='d9cca866-962f-49cd-9809-292263465bfa',
            created=beginning,
            updated=beginning,
        )
        template.save()
        sbml_file = Attachment(
            object_ref=template,
            file=django_file,
            filename='StdEciJO1366.xml',
            mime_type='text/xml',
            file_size=os.path.getsize(template_file),
            created=beginning,
        )
        sbml_file.save()
        template.sbml_file = sbml_file
        template.save()
    # template_sync_species requires the real SBMLTemplate object
    template = RealSBMLTemplate.objects.get(pk=template.pk)
    template_sync_species(template)


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0004_set-assay-names'),
    ]

    operations = [
        migrations.RunPython(code=add_template, reverse_code=migrations.RunPython.noop),
    ]
