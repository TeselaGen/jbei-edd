# -*- coding: utf-8 -*-
# Generated by Django 1.9.13 on 2017-05-25 19:13

import os

from django.apps import apps as django_apps
from django.core.files import storage
from django.db import migrations

from main.signals.sbml import template_sync_species


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
        path = storage.default_storage.save('StdEciJO1366.xml', fp)
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
        file=storage.default_storage.path(path),
        filename='StdEciJO1366.xml',
        mime_type='text/xml',
        file_size=os.path.getsize(template_file),
        created=beginning,
    )
    sbml_file.save()
    template.sbml_file = sbml_file
    # can these be calculated from the model?
    template.biomass_calculation = 8.78066
    template.biomass_exchange_name = 'R_Ec_biomass_iJO1366_core_53p95M'
    template.save()
    template_sync_species(template.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0004_set-assay-names'),
    ]

    operations = [
        migrations.RunPython(code=add_template, reverse_code=migrations.RunPython.noop),
    ]
