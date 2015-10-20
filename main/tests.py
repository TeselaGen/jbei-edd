# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import arrow
import os.path
import warnings

from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from edd.profile.models import UserProfile

from . import data_import
from . import sbml_export
from . import utilities
from .forms import (
    LineForm,
    )
from .models import (
    Assay, CarbonSource, GeneIdentifier, GroupPermission, Line, MeasurementType, MeasurementUnit,
    Metabolite, MetaboliteKeyword, MetadataGroup, MetadataType, Protocol, SBMLTemplate, Strain,
    Study, Update, UserPermission,
    )
from .solr import StudySearch


# Everything running in this file is a test, but Django only handles test instances of a
#   database; there is no concept of a Solr test instance as far as test framework is
#   concerned. Tests should be run with:
#       python manage.py test --settings test_settings main
#   Otherwise, tests will pollute the search index with several entries for testing data.


class UserTests(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        user1 = User.objects.create_user(
            username='James Smith',
            email="jsmith@localhost",
            password='password')
        User.objects.create_user(
            username='John Doe',
            email="jdoe@localhost",
            password='password')
        UserProfile.objects.create(
            user=user1,
            initials="JS",
            description="random postdoc")

    def test_monkey_patches(self):
        user1 = User.objects.get(username="James Smith")
        user2 = User.objects.get(username="John Doe")
        self.assertTrue(user1.initials == "JS")
        self.assertTrue(user2.initials is None)
        user_json = user1.to_json()
        for key, value in {'initials': u'JS', 'uid': u'James Smith', 'name': u'',
                           'email': u'jsmith@localhost'}.iteritems():
            self.assertTrue(user_json[key] == value)


class StudyTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        email = 'wcmorrell@lbl.gov'
        user1 = User.objects.create_user(username='test1', email=email, password='password')
        user2 = User.objects.create_user(username='test2', email=email, password='password')
        user3 = User.objects.create_user(username='test3', email=email, password='password')
        User.objects.create_user(username='test4', email=email, password='password')
        fuels = Group.objects.create(name='Fuels Synthesis')
        decon = Group.objects.create(name='Deconstruction')
        user1.groups.add(fuels)
        user2.groups.add(decon)
        user3.groups.add(fuels, decon)
        # test4 user will have no groups
        Study.objects.create(name='Test Study 1', description='')
        Study.objects.create(name='Test Study 2', description='')
        mdg1 = MetadataGroup.objects.create(group_name="Misc")
        MetadataType.objects.create(
            type_name="Some key",
            group=mdg1,
            for_context=MetadataType.STUDY)
        MetadataType.objects.create(
            type_name="Some key 2",
            group=mdg1,
            for_context=MetadataType.ALL)
        MetadataType.objects.create(
            type_name="Some key 3",
            group=mdg1,
            for_context=MetadataType.ASSAY)

    def tearDown(self):
        TestCase.tearDown(self)

    def test_read_with_no_permissions(self):
        """ Ensure that a study without permissions cannot be read. """
        # Load objects
        study = Study.objects.get(name='Test Study 1')
        user1 = User.objects.get(username='test1')
        # Asserts
        self.assertFalse(study.user_can_read(user1))

    def test_user_read_write_permission(self):
        """ Ensure that a study with user having read or write permissions can be read. """
        # Load objects
        study = Study.objects.get(name='Test Study 1')
        user1 = User.objects.get(username='test1')
        user2 = User.objects.get(username='test2')
        user3 = User.objects.get(username='test3')
        # Create permissions
        UserPermission.objects.create(study=study, permission_type='W', user=user1)
        UserPermission.objects.create(study=study, permission_type='R', user=user2)
        # Asserts
        self.assertTrue(study.user_can_read(user1))
        self.assertTrue(study.user_can_write(user1))
        self.assertTrue(study.user_can_read(user2))
        self.assertFalse(study.user_can_write(user2))
        self.assertFalse(study.user_can_read(user3))
        self.assertFalse(study.user_can_write(user3))

    def test_group_read_write_permission(self):
        """ Ensure that a study with group having read or write permissions can be read. """
        # Load objects
        study = Study.objects.get(name='Test Study 1')
        fuels = Group.objects.get(name='Fuels Synthesis')
        decon = Group.objects.get(name='Deconstruction')
        user1 = User.objects.get(username='test1')  # fuels
        user2 = User.objects.get(username='test2')  # decon
        user3 = User.objects.get(username='test3')  # fuels AND decon
        user4 = User.objects.get(username='test4')  # no group
        # Create permissions
        GroupPermission.objects.create(study=study, permission_type='W', group=fuels)
        GroupPermission.objects.create(study=study, permission_type='R', group=decon)
        # Asserts
        self.assertTrue(study.user_can_read(user1))
        self.assertTrue(study.user_can_write(user1))
        self.assertTrue(study.user_can_read(user2))
        self.assertFalse(study.user_can_write(user2))
        self.assertTrue(study.user_can_read(user3))
        self.assertTrue(study.user_can_write(user3))
        self.assertFalse(study.user_can_read(user4))
        self.assertFalse(study.user_can_write(user4))

    def test_study_metadata(self):
        study = Study.objects.get(name='Test Study 1')
        study.set_metadata_item("Some key", "1.234")
        study.set_metadata_item("Some key 2", "5.678")
        self.assertTrue(study.get_metadata_item("Some key") == "1.234")
        self.assertTrue(study.get_metadata_dict() == {'Some key 2': '5.678', 'Some key': '1.234'})
        try:
            study.set_metadata_item("Some key 3", "9.876")
        except ValueError:
            pass
        else:
            raise Exception("Should have caught a ValueError here...")


class SolrTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        email = 'wcmorrell@lbl.gov'
        self.admin = User.objects.create_superuser(username='admin', email=email, password='12345')
        self.user1 = User.objects.create_user(username='test1', email=email, password='password')
        self.solr_admin = StudySearch(ident=self.admin)
        self.solr_user = StudySearch(ident=self.user1)
        up1 = Update.objects.create(mod_by=self.user1)
        self.study1 = Study.objects.create(name='Test Study 1',
                                           description='Lorem ipsum dolor sit amet')
        self.study1.updates.add(up1)
        self.solr_admin.clear()

    def tearDown(self):
        self.solr_admin.clear()
        TestCase.tearDown(self)

    def test_initially_empty(self):
        result = self.solr_user.query(query='*:*')
        self.assertEqual(result['response']['numFound'], 0, "The test index is not initially empty")

    def test_add_and_retrieve(self):
        pre_add = self.solr_admin.query(query='description:dolor')
        self.solr_user.update([self.study1])
        post_add = self.solr_admin.query(query='description:dolor')
        self.assertEqual(pre_add['response']['numFound'], 0, "Study in index before it was added")
        self.assertEqual(post_add['response']['numFound'], 1, "Added study was not found in query")


class LineTests (TestCase):  # XXX also Strain, CarbonSource
    def setUp(self):
        TestCase.setUp(self)
        user1 = User.objects.create_user(
            username="admin", email="nechols@lbl.gov", password='12345')
        study1 = Study.objects.create(name='Test Study 1', description='')
        study2 = Study.objects.create(name='Test Study 2', description='')
        cs1 = CarbonSource.objects.create(
            name="Carbon source 1", labeling="100% unlabeled", volume=50.0, description="Desc 1")
        cs2 = CarbonSource.objects.create(
            name="Carbon source 2", labeling="20% 13C", volume=100.0)
        cs3 = CarbonSource.objects.create(
            name="Carbon source 3", labeling="40% 14C", volume=100.0)
        strain1 = Strain.objects.create(
            name="Strain 1", description="JBEI strain 1",
            registry_url="http://registry.jbei.org/strain/666",
            registry_id="00000000-0000-0000-0000-000000000000", )
        strain2 = Strain.objects.create(name="Strain 2")
        line1 = study1.line_set.create(
            name="Line 1", description="mutant 1", experimenter=user1, contact=user1)
        line1.carbon_source.add(cs1)
        line2 = study1.line_set.create(
            name="Line 2", description="mutant 2", experimenter=user1, contact=user1)
        line2.carbon_source.add(cs2)
        line3 = study2.line_set.create(
            name="Line 3", description="double mutant", experimenter=user1, contact=user1)
        line3.carbon_source.add(cs1)
        line3.carbon_source.add(cs3)
        line1.strains.add(strain1)
        line2.strains.add(strain1)
        line3.strains.add(strain1)
        line3.strains.add(strain2)
        mdg1 = MetadataGroup.objects.create(group_name="Line metadata")
        MetadataType.objects.create(
            type_name="Media", group=mdg1, for_context=MetadataType.LINE)
        mdg2 = MetadataGroup.objects.create(group_name="Assay metadata")
        MetadataType.objects.create(
            type_name="Sample volume", group=mdg2, for_context=MetadataType.ASSAY)

    def test_line_metadata(self):
        line1 = Line.objects.get(name="Line 1")
        media = MetadataType.objects.get(type_name="Media")
        sv = MetadataType.objects.get(type_name="Sample volume")
        line1.metadata_add(media, "M9")
        self.assertTrue(line1.metadata_get(media) == "M9")
        try:
            line1.metadata_add(sv, 1.5)
        except ValueError:
            pass
        else:
            raise Exception("Should have caught a ValueError here...")

    def test_line_json(self):
        line1 = Line.objects.get(name="Line 1")
        md = MetadataType.objects.get(type_name="Media")
        line1.metadata_add(md, 'M9')
        json_dict = line1.to_json()
        self.assertTrue(json_dict['meta'] == {"%s" % md.pk: "M9"})

    def test_line_form(self):
        line1 = Line.objects.select_related('study').get(name="Line 1")
        # default form to existing data
        data = LineForm.initial_from_model(line1, prefix='line')
        # flip the checkbox for control
        data['line-control'] = True
        form = LineForm(data, instance=line1, prefix='line', study=line1.study)
        # verify the form validates
        self.assertTrue(form.is_valid(), '%s' % form._errors)
        line2 = form.save()
        # verify the saved line is now a control
        self.assertTrue(line1.control != line2.control)

    def test_strain(self):
        strain1 = Strain.objects.get(name="Strain 1")
        strain2 = Strain.objects.get(name="Strain 2")
        self.assertTrue(strain1.n_lines == 3)
        self.assertTrue(strain1.n_studies == 2)
        self.assertTrue(strain2.n_lines == 1)
        self.assertTrue(strain2.n_studies == 1)
        json_dict = strain1.to_json()
        self.assertTrue(json_dict['registry_url'] == "http://registry.jbei.org/strain/666")
        self.assertTrue(json_dict['description'] == "JBEI strain 1")
        line1 = Line.objects.get(name="Line 1")
        line2 = Line.objects.get(name="Line 2")
        line3 = Line.objects.get(name="Line 3")
        self.assertTrue(line1.primary_strain_name == "Strain 1")
        self.assertTrue(line3.primary_strain_name == "Strain 1")
        self.assertTrue(line1.strain_ids == "Strain 1")
        self.assertTrue(line1.strain_ids == line2.strain_ids)
        self.assertTrue(line3.strain_ids == "Strain 1,Strain 2")

    def test_carbon_source(self):
        line1 = Line.objects.get(name="Line 1")
        line3 = Line.objects.get(name="Line 3")
        cs1 = CarbonSource.objects.get(name="Carbon source 1")
        cs2 = CarbonSource.objects.get(name="Carbon source 2")
        self.assertTrue(cs1.n_lines == 2)
        self.assertTrue(cs1.n_studies == 2)
        self.assertTrue(cs2.n_lines == 1)
        self.assertTrue(cs2.n_studies == 1)
        json_dict = cs1.to_json()
        self.assertTrue(json_dict['labeling'] == "100% unlabeled")
        self.assertTrue(line1.carbon_source_labeling == "100% unlabeled")
        self.assertTrue(line1.carbon_source_name == "Carbon source 1")
        self.assertTrue(line1.carbon_source_info == "Carbon source 1 (100% unlabeled)")
        self.assertTrue(
            line3.carbon_source_info ==
            "Carbon source 1 (100% unlabeled),Carbon source 3 (40% 14C)")


# XXX because there's so much overlap in functionality and the necessary setup
# is somewhat involved, this set of tests includes multiple models, focused
# on assay data and associated objects.
#
# TODO also test MeasurementVector
class AssayDataTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        user1 = User.objects.create_user(
            username="admin", email="nechols@lbl.gov", password='12345')
        study1 = Study.objects.create(name='Test Study 1', description='')
        line1 = study1.line_set.create(
            name="WT1", description="", experimenter=user1, contact=user1)
        protocol1 = Protocol.objects.create(name="gc-ms", owned_by=user1)
        protocol2 = Protocol.objects.create(name="OD600", owned_by=user1)
        Protocol.objects.create(name="New protocol", owned_by=user1, active=False)
        mt1 = Metabolite.objects.create(
            type_name="Mevalonate", short_name="Mev", type_group="m", charge=-1, carbon_count=6,
            molecular_formula="C6H11O4", molar_mass=148.16)
        mt2 = Metabolite.objects.create(
            type_name="D-Glucose", short_name="glc-D", type_group="m", charge=0, carbon_count=6,
            molecular_formula="C6H12O6", molar_mass=180.16)
        mt3 = Metabolite.objects.create(
            type_name="Acetate", short_name="ac", type_group="m", charge=-1, carbon_count=2,
            molecular_formula="C2H3O2", molar_mass=60.05)
        kw1 = MetaboliteKeyword.objects.create(name="GCMS", mod_by=user1)
        kw2 = MetaboliteKeyword.objects.create(name="HPLC", mod_by=user1)
        kw3 = MetaboliteKeyword.objects.create(name="Mevalonate Pathway", mod_by=user1)
        mt1.keywords.add(kw1)
        mt1.keywords.add(kw3)
        mt2.keywords.add(kw2)
        mt2 = GeneIdentifier.objects.create(
            type_name="Gene name 1", short_name="gen1", type_group="g")
        mt3 = MeasurementType.create_protein(
            type_name="Protein name 2", short_name="prot2")
        MeasurementType.create_protein(
            type_name="Protein name 1", short_name="prot1")
        assay1 = line1.assay_set.create(
            name="1", protocol=protocol1, description="GC-MS assay 1", experimenter=user1)
        line1.assay_set.create(
            name="1", protocol=protocol2, description="OD600 assay 1", experimenter=user1)
        up1 = Update.objects.create(mod_by=user1)
        mu1 = MeasurementUnit.objects.create(unit_name="hours")
        mu2 = MeasurementUnit.objects.create(unit_name="mM", type_group="m")
        MeasurementUnit.objects.create(unit_name="Cmol/L")
        MeasurementUnit.objects.create(unit_name="abcd", alternate_names="asdf")
        meas1 = assay1.measurement_set.create(
            experimenter=user1, measurement_type=mt1, compartment="1", update_ref=up1,
            x_units=mu1, y_units=mu2)
        assay1.measurement_set.create(
            experimenter=user1, measurement_type=mt2, compartment="1", update_ref=up1,
            x_units=mu1, y_units=mu2)
        assay1.measurement_set.create(
            experimenter=user1, measurement_type=mt3, compartment="1", update_ref=up1,
            x_units=mu1, y_units=mu2)
        x1 = [0, 4, 8, 12, 18, 24, ]
        y1 = [0.0, 0.1, 0.2, 0.4, 0.8, 1.6, ]
        for x, y in zip(x1, y1):
            meas1.measurementvalue_set.create(updated=up1, x=[x], y=[y])
        meas1.measurementvalue_set.create(updated=up1, x=[32], y=[])

    def test_protocol(self):
        p1 = Assay.objects.get(description="GC-MS assay 1").protocol
        p2 = Protocol.objects.get(name="OD600")
        p3 = Protocol.objects.filter(active=False)[0]
        self.assertTrue('%s' % p1 == "gc-ms")
        self.assertTrue(p1.categorization == "LCMS")
        self.assertTrue(p2.categorization == "OD")
        self.assertTrue(p3.categorization == "Unknown")
        p1_json = p1.to_json()
        self.assertTrue(p1_json.get('active', False))
        self.assertTrue(p1_json.get('name', None) == 'gc-ms')
        p3_json = p3.to_json()
        self.assertFalse(p3_json.get('active', True))
        self.assertTrue(p3_json.get('name', None) == 'New protocol')
        user1 = User.objects.get(username="admin")
        Protocol.objects.create(
            name="Another protocol",
            owned_by=user1,
            variant_of_id=p3.id)
        try:
            Protocol.objects.create(
                name="Another protocol",
                owned_by=user1,
                variant_of_id=p3.id)
        except ValueError as e:
            self.assertTrue('%s' % e == "There is already a protocol named 'Another protocol'.")
        else:
            raise Exception("Should have caught a ValueError...")
        try:
            Protocol.objects.create(
                name="",
                owned_by=user1)
        except ValueError as e:
            self.assertTrue('%s' % e == "Protocol name required.")
        else:
            raise Exception("Should have caught a ValueError...")

    def test_assay(self):
        assay = Assay.objects.get(description="GC-MS assay 1")
        self.assertTrue(len(assay.get_metabolite_measurements()) == 1)
        self.assertTrue(len(assay.get_gene_measurements()) == 1)
        self.assertTrue(len(assay.get_protein_measurements()))
        assay.to_json()
        self.assertTrue(assay.long_name == "WT1-gc-ms-1")
        new_assay_number = assay.line.new_assay_number("gc-ms")
        self.assertTrue(new_assay_number == 2)

    def test_measurement_type(self):
        proteins = MeasurementType.proteins()
        self.assertTrue(len(proteins) == 2)
        self.assertTrue(proteins[0].is_protein())
        assay = Assay.objects.get(description="GC-MS assay 1")
        meas1 = assay.measurement_set.filter(
            measurement_type__short_name="Mev")[0]
        mt1 = meas1.measurement_type
        self.assertTrue(mt1.is_metabolite() and not mt1.is_protein() and not mt1.is_gene())
        met = Metabolite.objects.get(short_name="Mev")
        met.set_keywords(["GCMS", "HPLC"])
        self.assertTrue(met.keywords_str == "GCMS, HPLC")
        self.assertTrue(met.to_json() == {
            'id': mt1.id, 'cc': 6, 'name': u'Mevalonate', 'chgn': -1, 'ans': '', 'mm': 148.16,
            'f': u'C6H11O4', 'chg': -1, 'sn': u'Mev', 'family': mt1.type_group,
            'kstr': 'GCMS,HPLC'})
        keywords = MetaboliteKeyword.all_with_metabolite_ids()
        self.assertTrue(len(keywords[1]['metabolites']) == 2)

    def test_measurement_unit(self):
        mu = MeasurementUnit.objects.get(unit_name="mM")
        self.assertTrue(mu.group_name == "Metabolite")
        all_units = [mu.unit_name for mu in MeasurementUnit.all_sorted()]
        self.assertTrue(all_units == [u'abcd', u'Cmol/L', u'hours', u'mM'])

    def test_measurement(self):
        assay = Assay.objects.get(description="GC-MS assay 1")
        metabolites = list(assay.get_metabolite_measurements())
        self.assertTrue(len(metabolites) == 1)
        meas1 = metabolites[0]
        meas2 = list(assay.get_gene_measurements())[0]
        self.assertTrue(meas1.y_axis_units_name == "mM")
        self.assertTrue(meas1.name == "Mevalonate")
        self.assertTrue(meas1.short_name == "Mev")
        self.assertTrue(meas1.full_name == "IC Mevalonate")
        self.assertTrue(meas1.is_concentration_measurement())
        self.assertTrue(not meas1.is_carbon_ratio())
        self.assertTrue(meas2.is_gene_measurement())
        mdata = list(meas1.measurementvalue_set.all())
        self.assertTrue(mdata[0].x[0] == 0)
        self.assertTrue(mdata[0].y[0] == 0)
        self.assertTrue(mdata[-1].x[0] == 32)
        self.assertFalse(mdata[-1].y)

    def test_measurement_extract(self):
        assay = Assay.objects.get(description="GC-MS assay 1")
        meas1 = list(assay.get_metabolite_measurements())[0]
        meas2 = list(assay.get_gene_measurements())[0]
        xval = meas1.extract_data_xvalues()
        self.assertTrue(xval == [0.0, 4.0, 8.0, 12.0, 18.0, 24.0, 32.0])
        xval2 = meas1.extract_data_xvalues(defined_only=True)
        self.assertTrue(xval2 == [0.0, 4.0, 8.0, 12.0, 18.0, 24.0])
        xval3 = meas2.extract_data_xvalues()
        self.assertTrue(len(xval3) == 0)

    def test_measurement_interpolate(self):
        assay = Assay.objects.get(description="GC-MS assay 1")
        meas1 = list(assay.get_metabolite_measurements())[0]
        meas2 = list(assay.get_gene_measurements())[0]
        y_interp = meas1.interpolate_at(21)
        # XXX I hate floating-point math
        self.assertTrue('%s' % y_interp == "1.2")
        y_interp2 = meas1.interpolate_at(25)
        self.assertTrue(y_interp2 is None)
        try:
            meas2.interpolate_at(20)
        except ValueError:
            pass
        else:
            raise Exception("Should have caught an exception here")


class ImportTests(TestCase):
    """ Test import of assay measurement data. """
    def setUp(self):
        TestCase.setUp(self)
        user1 = User.objects.create_user(
            username="admin", email="nechols@lbl.gov", password='12345')
        user2 = User.objects.create_user(
            username="postdoc", email="nechols@lbl.gov", password='12345')
        study1 = Study.objects.create(name='Test Study 1', description='')
        UserPermission.objects.create(
            study=study1, permission_type='R', user=user1)
        UserPermission.objects.create(
            study=study1, permission_type='W', user=user1)
        UserPermission.objects.create(
            study=study1, permission_type='R', user=user2)
        study1.line_set.create(
            name="L1", description="Line 1", experimenter=user1, contact=user1)
        study1.line_set.create(
            name="L2", description="Line 2", experimenter=user1, contact=user1)
        Protocol.objects.create(name="GC-MS", owned_by=user1)
        Protocol.objects.create(name="Transcriptomics", owned_by=user1)
        Metabolite.objects.create(
            type_name="Acetate", short_name="ac", type_group="m", charge=-1, carbon_count=2,
            molecular_formula="C2H3O2", molar_mass=60.05)
        Metabolite.objects.create(
            type_name="D-Glucose", short_name="glc-D", type_group="m", charge=0, carbon_count=6,
            molecular_formula="C6H12O6", molar_mass=180.16)
        MeasurementUnit.objects.create(unit_name="mM")
        MeasurementUnit.objects.create(unit_name="hours")
        MeasurementUnit.objects.create(unit_name="counts")
        MeasurementUnit.objects.create(unit_name="FPKM")

    def get_form(self):
        mu = MeasurementUnit.objects.get(unit_name="mM")
        # breaking up big text blob
        json = ("""[{"label":"Column 0","name":"Column 0","units":"units","parsingIndex":0,"""
                """"assay":null,"assayName":null,"measurementType":1,"metadata":{},"""
                """"singleData":null,"color":"rgb(10, 136, 109)","data":["""
                """[0,"0.1"],[1,"0.2"],[2,"0.4"],[4,"1.7"],[8,"5.9"]]},"""
                """{"label":"Column 1","name":"Column 1","units":"units","parsingIndex":1,"""
                """"assay":null,"assayName":null,"measurementType":2,"metadata":{},"""
                """"singleData":null,"color":"rgb(136, 14, 43)","data":["""
                """[0,"0.2"],[1,"0.4"],[2,"0.6"],[4,"0.8"],[8,"1.2"]]}]""")
        # XXX not proud of this, but we need actual IDs in here
        return {
            'action': "Submit Data",
            'datalayout': "std",
            'disamMComp1': 1,
            'disamMComp2': 1,
            'disamMType1': Metabolite.objects.get(short_name="ac").pk,
            'disamMType2': Metabolite.objects.get(short_name="glc-D").pk,
            'disamMUnits1': mu.pk,
            'disamMUnits2': mu.pk,
            'enableColumn0': 1,
            'enableColumn1': 2,
            'enableRow0': 1,
            'enableRow1': 2,
            'enableRow2': 3,
            'enableRow3': 4,
            'enableRow4': 5,
            'enableRow5': 6,
            'jsonoutput': json,
            'masterAssay': "new",
            'masterLine': Line.objects.get(name="L1").pk,
            'masterMComp': '',
            'masterMCompValue': 0,
            'masterMType': '',
            'masterMTypeValue': 0,
            'masterMUnits': '',
            'masterMUnitsValue': 0,
            'masterProtocol': Protocol.objects.get(name="GC-MS").pk,
            'masterTimestamp': '',
            'rawdataformat': "csv",
            'row0type': 2,
            'row1type': 3,
            'row2type': 3,
            'row3type': 3,
            'row4type': 3,
            'row5type': 3,
            'studyID': Study.objects.get(name="Test Study 1").pk,
            'writemode': "m",
        }

    def test_import_gc_ms_metabolites(self):
        table = data_import.TableImport(
            Study.objects.get(name="Test Study 1"),
            User.objects.get(username="admin"))
        added = table.import_data(self.get_form())
        self.assertEqual(added, 10)
        data_literal = ("""[[(0.0, 0.1), (1.0, 0.2), (2.0, 0.4), (4.0, 1.7), (8.0, 5.9)], """
                        """[(0.0, 0.2), (1.0, 0.4), (2.0, 0.6), (4.0, 0.8), (8.0, 1.2)]]""")
        assays = Line.objects.get(name="L1").assay_set.all()
        self.assertTrue(len(assays) == 1)
        meas = assays[0].measurement_set.all()
        self.assertTrue(len(meas) == 2)
        data = []
        for m in meas:
            data.append([(float(d.x[0]), float(d.y[0])) for d in m.measurementvalue_set.all()])
        self.assertTrue('%s' % data == data_literal)

    def test_error(self):
        try:  # failed user permissions check
            table = data_import.TableImport(
                Study.objects.get(name="Test Study 1"),
                User.objects.get(username="postdoc"))
            table.import_data(self.get_form())
        except PermissionDenied:
            pass
        else:
            raise Exception("Expected a PermissionDenied here")

    def test_import_rna_seq(self):
        line1 = Line.objects.get(name="L1")
        line2 = Line.objects.get(name="L2")
        table1 = [  # FPKM
            ["GENE",  "L1-1", "L1-2", "L2-1", "L2-2"],
            ["gene1", "5.34", "5.32", "7.45", "7.56"],
            ["gene2", "1.79", "1.94", "0.15", "0.33"],
        ]
        user = User.objects.get(username="admin")
        update = Update.objects.create(
            mod_time=arrow.utcnow(),
            mod_by=user)
        # two assays per line (replicas)
        result = data_import.import_rna_seq(
            study=Study.objects.get(name="Test Study 1"),
            user=user,
            update=update,
            table=table1,
            n_cols=4,
            data_type="fpkm",
            line_ids=[line1.pk, line1.pk, line2.pk, line2.pk],
            assay_ids=[0, 0, 0, 0],
            meas_times=[0]*4)
        self.assertTrue(result.n_meas == result.n_meas_data == 8)
        self.assertTrue(result.n_assay == 4 and result.n_meas_type == 2)
        result = data_import.interpret_raw_rna_seq_data(
            raw_data="\n".join(["\t".join(row) for row in table1]),
            study=Study.objects.get(name="Test Study 1"))
        self.assertTrue(result["guessed_data_type"] == "fpkm")
        self.assertTrue(result["samples"][0]["line_id"] == line1.pk)
        self.assertTrue(result["samples"][2]["line_id"] == line2.pk)
        # one assay, two timepoints per line
        result = data_import.import_rna_seq(
            study=Study.objects.get(name="Test Study 1"),
            user=user,
            update=update,
            table=table1,
            n_cols=4,
            data_type="fpkm",
            line_ids=[line1.pk, line1.pk, line2.pk, line2.pk],
            assay_ids=[0, 0, 0, 0],
            meas_times=[0, 1, 0, 1],
            group_timepoints=1)
        self.assertTrue(result.n_meas == 4 and result.n_meas_data == 8)
        self.assertTrue(result.n_meas_type == 0 and result.n_assay == 2)
        table2 = [  # count
            ["GENE",  "L1-1", "L1-2", "L2-1", "L2-2"],
            ["gene1", "64", "67", "89", "91"],
            ["gene2", "27", "30", "5", "4"],
        ]
        result = data_import.import_rna_seq(
            study=Study.objects.get(name="Test Study 1"),
            user=user,
            update=update,
            table=table2,
            n_cols=4,
            data_type="counts",
            line_ids=[line1.pk, line1.pk, line2.pk, line2.pk],
            assay_ids=[0, 0, 0, 0],
            meas_times=[5]*4)
        self.assertTrue(result.n_meas == result.n_meas_data == 8)
        self.assertTrue(result.n_meas_type == 0 and result.n_assay == 4)
        table3 = [  # combined
            ["GENE",  "L1-1", "L1-2", "L2-1", "L2-2"],
            ["gene1", "64,5.34", "67,5.32", "89,7.45", "91,7.56"],
            ["gene2", "27,1.79", "30,1.94", "5,0.15", "4,0.33"],
        ]
        # one assay, two timepoints, counts+fpkms
        result = data_import.import_rna_seq(
            study=Study.objects.get(name="Test Study 1"),
            user=user,
            update=update,
            table=table3,
            n_cols=4,
            data_type="combined",
            line_ids=[line1.pk, line1.pk, line2.pk, line2.pk],
            assay_ids=[0, 0, 0, 0],
            meas_times=[0, 1, 0, 1],
            group_timepoints=1)
        self.assertTrue(result.n_meas_type == 0 and result.n_assay == 2)
        self.assertTrue(result.n_meas == 8 and result.n_meas_data == 16)
        # two timepoints per condition, separate assays
        result = data_import.import_rna_seq(
            study=Study.objects.get(name="Test Study 1"),
            user=user,
            update=update,
            table=table3,
            n_cols=4,
            data_type="combined",
            line_ids=[line1.pk, line1.pk, line2.pk, line2.pk],
            assay_ids=[0, 0, 0, 0],
            meas_times=[0, 1, 0, 1])
        self.assertTrue(result.n_meas_type == 0 and result.n_assay == 4)
        self.assertTrue(result.n_meas == 16 and result.n_meas_data == 16)
        # error catching
        p = Protocol.objects.get(name="Transcriptomics")
        assay1 = line1.assay_set.create(
            name="assay1", description="", protocol=p, experimenter=user)
        assay2 = line2.assay_set.create(
            name="assay1", description="", protocol=p, experimenter=user)
        try:
            result = data_import.import_rna_seq(
                study=Study.objects.get(name="Test Study 1"),
                user=user,
                update=update,
                table=table3,
                n_cols=4,
                data_type="combined",
                line_ids=[line1.pk, line1.pk, line2.pk, line2.pk],
                assay_ids=[assay1.pk, assay1.pk, assay2.pk, assay2.pk],
                meas_times=[0, 0, 0, 0])
        except ValueError:
            pass
        else:
            raise Exception("ValueError expected")
        # use existing Assays instead of creating new ones
        result = data_import.import_rna_seq(
            study=Study.objects.get(name="Test Study 1"),
            user=user,
            update=update,
            table=table3,
            n_cols=4,
            data_type="combined",
            line_ids=[line1.pk, line1.pk, line2.pk, line2.pk],
            assay_ids=[assay1.pk, assay1.pk, assay2.pk, assay2.pk],
            meas_times=[0, 4, 0, 4])
        self.assertTrue(result.n_meas_type == 0 and result.n_assay == 0)
        self.assertTrue(result.n_meas == 8 and result.n_meas_data == 16)
        self.assertTrue(assay1.measurement_set.count() == 4)
        #
        result = data_import.interpret_raw_rna_seq_data(
            raw_data="\n".join(["\t".join(row) for row in table3]),
            study=Study.objects.get(name="Test Study 1"))
        self.assertTrue(result["guessed_data_type"] == "combined")

    def test_import_rna_seq_edgepro(self):
        line2 = Line.objects.get(name="L2")
        user = User.objects.get(username="admin")
        update = Update.objects.create(
            mod_time=arrow.utcnow(),
            mod_by=user)
        # EDGE-pro output
        raw = """\
gene_ID            start_coord       end_coord     average_cov          #reads            RPKM

b0001                      190             255           171.3              45             207
b0002                      337            2799           257.0            2502             309
b0003                     2801            3733           303.9            1121             366
b0004                     3734            5020           197.5            1005             238
b0005                     5234            5530           201.3             236             242
b0006                     5683            6459           183.9             565             221"""
        assay = line2.assay_set.create(
            name="RNA-seq",
            description="EDGE-pro result",
            protocol=Protocol.objects.get(name="Transcriptomics"),
            experimenter=user)
        result = data_import.import_rnaseq_edgepro(
            form={
                "assay": assay.pk,
                "timepoint": "0",
                "data_table": raw,
            },
            study=line2.study,
            update=update)
        self.assertTrue(result.n_meas_type == 6)
        self.assertTrue(result.n_meas == result.n_meas_data == 12)
        # overwriting old data
        result = data_import.import_rnaseq_edgepro(
            form={
                "assay": assay.pk,
                "timepoint": "0",
                "data_table": raw,
            },
            study=line2.study,
            update=update)
        self.assertTrue(result.n_meas_type == result.n_meas == 0)
        self.assertTrue(result.n_meas_data == 12)
        # adding a timepoint
        result = data_import.import_rnaseq_edgepro(
            form={
                "assay": assay.pk,
                "timepoint": "4",
                "data_table": raw,
            },
            study=line2.study,
            update=update)
        self.assertTrue(result.n_meas_type == result.n_meas == 0)
        self.assertTrue(result.n_meas_data == 12)
        # erasing all existing data
        result = data_import.import_rnaseq_edgepro(
            form={
                "assay": assay.pk,
                "timepoint": "0",
                "data_table": raw,
                "remove_all": "1",
            },
            study=line2.study,
            update=update)
        self.assertTrue(result.n_meas_type == result.n_meas == 0)
        self.assertTrue(result.n_meas_data == 12)
        # now get rid of all count measurements...
        assay.measurement_set.filter(y_units__unit_name="counts").delete()
        # ... and reload, which will update the unchanged RPKMs and add new
        # count measurements
        result = data_import.import_rnaseq_edgepro(
            form={
                "assay": assay.pk,
                "timepoint": "0",
                "data_table": raw,
            },
            study=line2.study,
            update=update)
        self.assertTrue(result.n_meas_type == 0)
        self.assertTrue(result.n_meas == 6 and result.n_meas_data == 12)
        self.assertTrue(result.format_message() == "Added 0 gene identifiers and 6 measurements, "
                        "and updated 6 measurements")


class SBMLUtilTests(TestCase):
    """ Unit tests for various utilities used in SBML export """
    def setUp(self):
        SBMLTemplate.objects.create(
          name="R_Ec_biomass_iJO1366_core_53p95M",
          biomass_calculation=33.19037,
          biomass_exchange_name="R_Ec_biomass_iJO1366_core_53p95M")
        Metabolite.objects.create(
            type_name="Optical Density", short_name="OD", type_group="m", charge=0, carbon_count=0,
            molecular_formula="", molar_mass=0)

    def test_metabolite_name(self):
        guesses = sbml_export.generate_species_name_guesses_from_metabolite_name(
            "acetyl-CoA")
        self.assertTrue(
            guesses == ['acetyl-CoA', 'acetyl_DASH_CoA', 'M_acetyl-CoA_c',
                        'M_acetyl_DASH_CoA_c', 'M_acetyl_DASH_CoA_c_'])

    def test_sbml_notes(self):
        try:
            import libsbml
        except ImportError as e:
            warnings.warn('%s' % e)
        else:
            libsbml.SBML_DOCUMENT  # check to make sure it loaded
            notes = sbml_export.create_sbml_notes_object({
              "CONCENTRATION_CURRENT": [0.5, ],
              "CONCENTRATION_HIGHEST": [1.0, ],
              "CONCENTRATION_LOWEST": [0.01, ],
            })
            notes_dict = sbml_export.parse_sbml_notes_to_dict(notes)
            self.assertTrue(dict(notes_dict) == {
              'CONCENTRATION_CURRENT': ['0.5'],
              'CONCENTRATION_LOWEST': ['0.01'],
              'CONCENTRATION_HIGHEST': ['1.0'], })

    def test_sbml_setup(self):
        try:
            import libsbml
        except ImportError as e:
            warnings.warn('%s' % e)
        else:
            libsbml.SBML_DOCUMENT  # check to make sure it loaded
            dir_name = os.path.dirname(__file__)
            sbml_file = os.path.join(dir_name, "fixtures", "misc_data", "simple.sbml")
            s = sbml_export.sbml_info(i_template=0, sbml_file=sbml_file)
            self.assertTrue(s.n_sbml_species == 4)
            self.assertTrue(s.n_sbml_reactions == 5)
            # TODO lots more


class ExportTests(TestCase):
    """ Test export of assay measurement data, either as simple tables or SBML. """
    fixtures = ['export_data_1', ]

    def test_data_export(self):
        # TODO tests using main.forms.ExportSelectionForm, main.forms.ExportOptionForm, and
        #   main.views.ExportView
        pass

    def test_user_permission(self):
        # TODO tests using main.forms.ExportSelectionForm, main.forms.ExportOptionForm, and
        #   main.views.ExportView
        pass

    # XXX this test does NOT depend on libsbml being available
    def test_data_export_setup(self):
        study = Study.objects.get(name="Test Study 1")
        data = sbml_export.line_assay_data(
            study=study,
            lines=[Line.objects.get(name="Line 1"), ],
            form={})
        data.run()
        od_data = data.export_od_measurements()
        self.assertTrue(od_data[0]['data_points'][-1]['title'] == "0.59 at 24h")
        self.assertTrue(data.n_hplc_measurements == 2)
        hplc_data = data.export_hplc_measurements()
        self.assertTrue(len(hplc_data) > 0)
        hplc_data_assays = hplc_data[0]['assays']
        self.assertTrue(len(hplc_data_assays) > 0)
        hplc_data_measurements = hplc_data_assays[0]['measurements']
        self.assertTrue(len(hplc_data_measurements) > 0)
        self.assertTrue(hplc_data_measurements[0]['name'] == "EC Acetate")
        self.assertTrue(hplc_data_measurements[0]['n_points'] == 6)
        dp = hplc_data_measurements[0]['data_points'][2]
        self.assertTrue(dp['title'] == "0.22 at 8h")
        self.assertTrue(data.n_lcms_measurements == 3)
        lcms_data = data.export_lcms_measurements()
        dp = lcms_data[0]['assays'][0]['measurements'][0]['data_points'][2]
        self.assertTrue(dp['title'] == "0.2 at 8h")
        self.assertTrue(data.n_ramos_measurements == 2)
        all_meas = data.processed_measurements()
        self.assertTrue(len(all_meas) == 8)
        meas = all_meas[0]
        self.assertTrue(meas.n_errors == 0)
        self.assertTrue(meas.n_warnings == 1)
        self.assertTrue(meas.warnings[0] == 'Start OD of 0 means nothing physically present  (and '
                        'a potential division-by-zero error).  Skipping...')
        # for md in meas.data :
        #   print md
        # for fd in meas.flux_data :
        #   print fd
        # TODO test interpolation of measurements
        self.assertTrue(data.available_timepoints == [4.0, 8.0, 12.0, 18.0, ])

    def test_sbml_export(self):
        try:
            import libsbml
        except ImportError as e:
            warnings.warn('%s' % e)
        else:
            study = Study.objects.get(name="Test Study 1")
            data = sbml_export.line_sbml_export(
                study=study,
                lines=[Line.objects.get(name="Line 1"), ],
                form={"chosenmap": 0})
            dir_name = os.path.dirname(__file__)
            sbml_file = os.path.join(dir_name, "fixtures", "misc_data", "simple.sbml")
            data.run(test_mode=True, sbml_file=sbml_file)
            sbml_out = data.as_sbml(8.0)
            sbml_in = libsbml.readSBMLFromString(sbml_out)
            model = sbml_in.getModel()
            self.assertTrue(model is not None)
            # TODO test contents of file output

    def test_data_export_errors(self):
        # now start removing data (testing for deliberate failure)
        study = Study.objects.get(name="Test Study 1")
        od = Assay.objects.get(name="OD measurement")
        odm = od.measurement_set.all()[0]
        odm.measurementvalue_set.filter(x__0__gt=0).delete()
        try:
            data = sbml_export.line_sbml_export(
                study=study,
                lines=[Line.objects.get(name="Line 1"), ],
                form={})
            data.run(test_mode=True)
        except ValueError as e:
            self.assertTrue("Selected Optical Data contains less than two defined data points!" in (
                '%s' % e))
        else:
            raise Exception("Should have caught an exception here!")
        # now delete the assay altogether
        od.delete()
        try:
            data = sbml_export.line_sbml_export(
                study=study,
                lines=[Line.objects.get(name="Line 1"), ],
                form={})
            data.run(test_mode=True)
        except ValueError as e:
            self.assertTrue("Line selection does not contain any OD600 Assays"
                            in ('%s' % e))
        else:
            raise Exception("Should have caught an exception here!")


class UtilityTests(TestCase):
    fixtures = ['export_data_1', ]

    def test_get_edddata(self):
        utilities.get_edddata_users()
        # TODO validate output of get_edddata_users()
        # print(users)
        meas = utilities.get_edddata_measurement()
        self.assertTrue(
          sorted([m['name'] for k, m in meas['MetaboliteTypes'].iteritems()]) ==
          [u'Acetate', u'CO2', u'CO2 production', u'D-Glucose', u'O2',
           u'O2 consumption', u'Optical Density'])
        utilities.get_edddata_carbon_sources()
        # TODO validate output of get_edddata_carbon_sources()
        strains = utilities.get_edddata_strains()
        self.assertTrue(len(strains['EnabledStrainIDs']) == 1)
        misc = utilities.get_edddata_misc()
        misc_keys = sorted(["UnitTypes", "MediaTypes", "Users", "MetaDataTypes",
                            "MeasurementTypeCompartments"])
        self.assertTrue(sorted(misc.keys()) == misc_keys)
        study = Study.objects.get(name="Test Study 1")
        utilities.get_edddata_study(study)
        # TODO validate output of get_edddata_study()

    def test_interpolate(self):
        assay = Assay.objects.get(name="Assay 1")
        mt1 = Metabolite.objects.get(type_name="Acetate")
        meas = assay.measurement_set.get(measurement_type=mt1)
        data = meas.data()
        self.assertTrue(abs(utilities.interpolate_at(data, 10)-0.3) < 0.00001)

    def test_form_data(self):
        lines = Line.objects.all()
        form1 = {"selectedLineIDs": ",".join(['%s' % l.id for l in lines]), }
        form2 = {"selectedLineIDs": ['%s' % l.id for l in lines], }
        form3 = {}
        for l in lines:
            form3["line%dinclude" % l.id] = 1
        ids1 = utilities.extract_id_list(form1, "selectedLineIDs")
        ids2 = utilities.extract_id_list(form2, "selectedLineIDs")
        ids3 = utilities.extract_id_list_as_form_keys(form3, "line")
        self.assertTrue(ids1 == ids2 == sorted(ids3))
        study = Study.objects.get(name="Test Study 1")
        utilities.get_selected_lines(form1, study)

    def test_line_export_base(self):
        study = Study.objects.get(name="Test Study 1")
        data = utilities.line_export_base(
            study=study,
            lines=study.line_set.all())
        data._fetch_cache_data()
        assay = Assay.objects.get(name="Assay 1")
        m = data._get_measurements(assay.id)
        self.assertTrue(len(m) == 2)
        m0d = data._get_measurement_data(m[0].id)
        m1d = data._get_measurement_data(m[1].id)
        self.assertEqual(len(m0d), 6)
        self.assertEqual(len(m1d), 6)
        mt = set()
        mt.add(data._get_measurement_type(m[0].id).type_name)
        mt.add(data._get_measurement_type(m[1].id).type_name)
        self.assertEqual(mt, set(['D-Glucose', 'Acetate']))
        mu = data._get_y_axis_units_name(m[1].id)
        self.assertTrue(mu == "mM")
        met = data._get_metabolite_measurements(assay.id)
        self.assertTrue(len(met) == 2)
