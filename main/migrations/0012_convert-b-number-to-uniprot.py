# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-02-25 18:41
from __future__ import unicode_literals

import logging
import re

from django.db import IntegrityError, migrations, transaction
from django.db.models import Count

from .constants.b_to_uniprot import B_TO_UNIPROT, NAMES, UNIPROT


logger = logging.getLogger(__name__)
accession_pattern = re.compile(
    r'(?:[a-z]{2}\|)?'  # optional identifier for SwissProt or TrEMBL
    r'([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})'  # the ID
    r'(?:\|(\w+))?'  # optional name
)


class ProteinUpdate(object):

    def add_datasource(self):
        from main.models import Update
        Datasource = self._apps.get_model('main', 'Datasource')
        MigrateUpdate = self._apps.get_model('main', 'Update')
        app_update = Update.load_update(path=__name__)
        update = MigrateUpdate.objects.get(pk=app_update.pk)
        self._ds = Datasource.objects.create(
            name='UniProt',
            url='http://www.uniprot.org/uniprot/',
            created=update,
        )
        return self._ds

    def merge_proteins(self, old, canonical):
        Measurement = self._apps.get_model('main', 'Measurement')
        queryset = Measurement.objects.filter(measurement_type=old)
        try:
            with transaction.atomic():
                queryset.update(measurement_type=canonical)
        except IntegrityError:
            # at least one  item in queryset already has a link to canonical protein
            logger.warning('Model %s already has link with "%s", cannot merge "%s"',
                           Measurement, canonical, old)
        old.delete()

    def process_uniprot(self, apps, schema_editor):
        self._apps = apps
        ProteinIdentifier = apps.get_model('main', 'ProteinIdentifier')
        self.add_datasource()
        qs = ProteinIdentifier.objects.annotate(
            num_studies=Count('measurement__assay__line__study', distinct=True, ),
        )
        updated = self.update_all_proteins(qs)
        missing = [value for key, value in UNIPROT.iteritems() if key not in updated]
        for uniprot in missing:
            self.update_protein(ProteinIdentifier(), uniprot)

    def update_all_proteins(self, queryset):
        updated = set()
        for p in queryset:
            uniprot = B_TO_UNIPROT.get(p.type_name, None)
            match = accession_pattern.match(p.type_name)
            if uniprot:
                updated.add(self.update_protein(p, uniprot))
            elif match:
                p.short_name = match.group(1)
                if p.short_name in UNIPROT:
                    updated.add(self.update_protein(p, UNIPROT[p.short_name]))
                elif match.group(2):
                    p.type_name = match.group(2)
                    p.save()
                else:
                    p.save()
            elif p.type_name in NAMES:
                updated.add(self.update_protein(p, NAMES[p.type_name]))
            elif p.num_studies == 0:
                p.delete()
        return updated

    def update_protein(self, protein, uniprot):
        ProteinIdentifier = self._apps.get_model('main', 'ProteinIdentifier')
        check = ProteinIdentifier.objects.filter(short_name=uniprot['id'])
        if protein.pk:
            check = check.filter(pk__lt=protein.pk)
        if check.count():
            canonical = check[0]
            self.merge_proteins(protein, canonical)
        else:
            protein.type_name = uniprot['name']
            protein.short_name = uniprot['id']
            protein.length = uniprot['length']
            protein.mass = uniprot['mass']
            protein.type_source = self._ds
            protein.save()
        return uniprot['id']


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0011_measurement_meta_store'),
        ('main', '0012_add-protein-fields')
    ]

    operations = [
        migrations.RunPython(ProteinUpdate().process_uniprot),
    ]
