from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from identity.models import Organisation

from .models import Property


class PropertyModelTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(name='Kilimani Ltd')

    def make(self, **kwargs):
        defaults = {'organisation': self.organisation, 'name': 'Kilimani Court', 'address': 'Argwings Kodhek Rd'}
        return Property.objects.create(**{**defaults, **kwargs})

    def test_str_is_the_name(self):
        self.assertEqual(str(self.make()), 'Kilimani Court')

    def test_active_by_default(self):
        self.assertTrue(self.make().is_active)

    def test_has_ref_id_and_timestamps_from_base_model(self):
        prop = self.make()
        self.assertIsNotNone(prop.ref_id)
        self.assertIsNotNone(prop.created_at)
        self.assertIsNotNone(prop.updated_at)

    def test_organisation_is_required(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Property.objects.create(name='Orphan', address='Nowhere')

    def test_organisation_is_not_editable(self):
        self.assertFalse(Property._meta.get_field('organisation').editable)

    def test_organisation_with_properties_cannot_be_deleted(self):
        self.make()
        with self.assertRaises(ProtectedError):
            self.organisation.delete()

    def test_organisation_reaches_its_properties(self):
        prop = self.make()
        self.assertEqual(list(self.organisation.properties_property_set.all()), [prop])

    def test_ordered_by_name(self):
        self.make(name='Westlands Heights')
        self.make(name='Kilimani Court')
        self.assertEqual([p.name for p in Property.objects.all()], ['Kilimani Court', 'Westlands Heights'])
