from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import ChargeType


class ChargeTypeTests(TestCase):
    def make(self, **kwargs):
        defaults = {'code': 'GARBAGE', 'name': 'Garbage collection'}
        return ChargeType.objects.create(**{**defaults, **kwargs})

    def test_str_is_the_code(self):
        self.assertEqual(str(self.make()), 'GARBAGE')

    def test_active_by_default(self):
        self.assertTrue(self.make().is_active)

    def test_has_ref_id_and_timestamps_from_base_model(self):
        charge_type = self.make()
        self.assertIsNotNone(charge_type.ref_id)
        self.assertIsNotNone(charge_type.created_at)

    def test_code_is_stored_upper_case_and_trimmed(self):
        self.assertEqual(self.make(code='  service_charge ').code, 'SERVICE_CHARGE')

    def test_code_must_be_unique(self):
        self.make()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(name='Another')

    def test_codes_that_differ_only_by_case_are_the_same_code(self):
        self.make(code='GARBAGE')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(code='garbage')

    def test_ordered_by_name(self):
        self.make(code='SECURITY', name='Security')
        self.make(code='GARBAGE', name='Garbage collection')
        self.assertEqual([c.code for c in ChargeType.objects.all()], ['GARBAGE', 'SECURITY'])
