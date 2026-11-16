from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient

from catalogue.models import ChargeType
from identity.models import Membership, Organisation, Permission, Role

from .models import Frequency, Property, PropertyCharge, Unit

User = get_user_model()


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


class PropertyApiTests(TestCase):
    LIST_URL = '/api/properties/'

    def setUp(self):
        self.client = APIClient()
        self.codes = {
            code: Permission.objects.create(code=code, name=code)
            for code in ('property.read', 'property.create', 'property.update', 'property.delete')
        }
        self.kilimani = Organisation.objects.create(name='Kilimani Ltd')
        self.karen = Organisation.objects.create(name='Karen Ltd')
        self.user = User.objects.create_user('0712345678', password='pass12345')
        self.outsider = User.objects.create_user('0722345678', password='pass12345')
        self.mine = Property.objects.create(organisation=self.kilimani, name='Kilimani Court', address='Argwings Kodhek Rd')
        self.theirs = Property.objects.create(organisation=self.karen, name='Karen House', address='Karen Rd')

    def join(self, user, organisation, *codes):
        membership = Membership.objects.create(user=user, organisation=organisation)
        role = Role.objects.create(name=f'{user.phone}@{organisation.name}')
        role.permissions.set([self.codes[code] for code in codes])
        membership.roles.add(role)
        return membership

    def request(self, method, url, user=None, organisation=None, data=None):
        if user is not None:
            self.client.force_authenticate(user=user)
        headers = {'HTTP_X_ORGANISATION': str(organisation.ref_id)} if organisation is not None else {}
        return getattr(self.client, method)(url, data, format='json', **headers)

    def detail(self, prop):
        return f'{self.LIST_URL}{prop.pk}/'

    # reading

    def test_list_shows_only_my_organisations_properties(self):
        self.join(self.user, self.kilimani, 'property.read')
        response = self.request('get', self.LIST_URL, self.user, self.kilimani)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data], [self.mine.pk])

    def test_list_is_ordered_by_name(self):
        self.join(self.user, self.kilimani, 'property.read')
        Property.objects.create(organisation=self.kilimani, name='Altitude Apartments', address='x')
        response = self.request('get', self.LIST_URL, self.user, self.kilimani)
        self.assertEqual([row['name'] for row in response.data], ['Altitude Apartments', 'Kilimani Court'])

    def test_response_shape_hides_organisation_but_keeps_the_rest(self):
        self.join(self.user, self.kilimani, 'property.read')
        row = self.request('get', self.detail(self.mine), self.user, self.kilimani).data
        self.assertEqual(
            set(row), {'id', 'ref_id', 'name', 'address', 'is_active', 'created_at', 'updated_at'}
        )

    def test_retrieve_my_property(self):
        self.join(self.user, self.kilimani, 'property.read')
        response = self.request('get', self.detail(self.mine), self.user, self.kilimani)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Kilimani Court')

    def test_another_organisations_property_is_404_not_403(self):
        self.join(self.user, self.kilimani, 'property.read', 'property.update', 'property.delete')
        for method in ('get', 'patch', 'delete'):
            response = self.request(method, self.detail(self.theirs), self.user, self.kilimani, data={'name': 'x'})
            self.assertEqual(response.status_code, 404, method)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.name, 'Karen House')

    # who may call

    def test_unauthenticated_is_401(self):
        self.assertEqual(self.request('get', self.LIST_URL, None, self.kilimani).status_code, 401)

    def test_missing_header_is_400(self):
        self.join(self.user, self.kilimani, 'property.read')
        self.assertEqual(self.request('get', self.LIST_URL, self.user).status_code, 400)

    def test_not_a_member_is_403(self):
        self.join(self.user, self.kilimani, 'property.read')
        self.assertEqual(self.request('get', self.LIST_URL, self.user, self.karen).status_code, 403)

    def test_each_action_needs_its_own_permission(self):
        self.join(self.user, self.kilimani, 'property.read')
        body = {'name': 'New', 'address': 'Somewhere'}
        self.assertEqual(self.request('post', self.LIST_URL, self.user, self.kilimani, body).status_code, 403)
        self.assertEqual(self.request('patch', self.detail(self.mine), self.user, self.kilimani, body).status_code, 403)
        self.assertEqual(self.request('delete', self.detail(self.mine), self.user, self.kilimani).status_code, 403)
        self.assertEqual(Property.objects.filter(organisation=self.kilimani).count(), 1)

    # writing

    def test_create_places_the_property_in_the_header_organisation(self):
        self.join(self.user, self.kilimani, 'property.create')
        response = self.request(
            'post', self.LIST_URL, self.user, self.kilimani, {'name': 'New Block', 'address': 'Ngong Rd'}
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('organisation', response.data)
        self.assertEqual(Property.objects.get(name='New Block').organisation, self.kilimani)

    def test_create_ignores_an_organisation_sent_by_the_client(self):
        self.join(self.user, self.kilimani, 'property.create')
        body = {'name': 'Sneaky', 'address': 'x', 'organisation': self.karen.pk}
        response = self.request('post', self.LIST_URL, self.user, self.kilimani, body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Property.objects.get(name='Sneaky').organisation, self.kilimani)

    def test_create_validates_required_fields(self):
        self.join(self.user, self.kilimani, 'property.create')
        response = self.request('post', self.LIST_URL, self.user, self.kilimani, {'name': 'No address'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('address', response.data)

    def test_patch_updates_my_property(self):
        self.join(self.user, self.kilimani, 'property.update')
        response = self.request('patch', self.detail(self.mine), self.user, self.kilimani, {'is_active': False})
        self.assertEqual(response.status_code, 200)
        self.mine.refresh_from_db()
        self.assertFalse(self.mine.is_active)

    def test_patch_cannot_move_a_property_to_another_organisation(self):
        self.join(self.user, self.kilimani, 'property.update')
        self.request('patch', self.detail(self.mine), self.user, self.kilimani, {'organisation': self.karen.pk})
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.organisation, self.kilimani)

    def test_put_updates_my_property(self):
        self.join(self.user, self.kilimani, 'property.update')
        body = {'name': 'Renamed', 'address': 'New address', 'is_active': True}
        response = self.request('put', self.detail(self.mine), self.user, self.kilimani, body)
        self.assertEqual(response.status_code, 200)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, 'Renamed')

    def test_delete_removes_my_property(self):
        self.join(self.user, self.kilimani, 'property.delete')
        response = self.request('delete', self.detail(self.mine), self.user, self.kilimani)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Property.objects.filter(pk=self.mine.pk).exists())

    # one user, two organisations

    def test_the_header_decides_which_organisations_properties_are_returned(self):
        self.join(self.user, self.kilimani, 'property.read')
        self.join(self.user, self.karen, 'property.read')
        mine = self.request('get', self.LIST_URL, self.user, self.kilimani).data
        theirs = self.request('get', self.LIST_URL, self.user, self.karen).data
        self.assertEqual([row['name'] for row in mine], ['Kilimani Court'])
        self.assertEqual([row['name'] for row in theirs], ['Karen House'])


class PropertyChargeModelTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(name='Kilimani Ltd')
        self.property = Property.objects.create(
            organisation=self.organisation, name='Kilimani Court', address='Argwings Kodhek Rd'
        )
        self.service = ChargeType.objects.create(code='SERVICE_CHARGE', name='Service charge')
        self.garbage = ChargeType.objects.create(code='GARBAGE', name='Garbage collection')

    def make(self, **kwargs):
        defaults = {
            'organisation': self.organisation,
            'property': self.property,
            'charge_type': self.service,
            'amount': Decimal('1500.00'),
        }
        return PropertyCharge.objects.create(**{**defaults, **kwargs})

    def test_str_uses_the_charge_type_name_when_there_is_no_label(self):
        self.assertEqual(str(self.make()), 'Service charge (Kilimani Court)')

    def test_str_uses_the_label_when_there_is_one(self):
        self.assertEqual(str(self.make(name='Block A service')), 'Block A service (Kilimani Court)')

    def test_label_is_optional(self):
        charge = self.make()
        charge.full_clean()
        self.assertEqual(charge.name, '')

    def test_active_by_default(self):
        self.assertTrue(self.make().is_active)

    def test_amount_keeps_cents_exactly(self):
        charge = self.make(amount=Decimal('1500.50'))
        charge.refresh_from_db()
        self.assertEqual(charge.amount, Decimal('1500.50'))

    def test_negative_amount_is_rejected_by_validation(self):
        charge = PropertyCharge(
            organisation=self.organisation, property=self.property, charge_type=self.service, amount=Decimal('-1')
        )
        with self.assertRaises(ValidationError) as caught:
            charge.full_clean()
        self.assertIn('amount', caught.exception.message_dict)

    def test_organisation_is_required(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PropertyCharge.objects.create(property=self.property, charge_type=self.service, amount=Decimal('300'))

    def test_charge_type_is_required(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PropertyCharge.objects.create(
                organisation=self.organisation, property=self.property, amount=Decimal('300')
            )

    def test_a_charge_type_in_use_cannot_be_deleted(self):
        self.make()
        with self.assertRaises(ProtectedError):
            self.service.delete()

    def test_property_reaches_its_charges(self):
        charge = self.make()
        self.assertEqual(list(self.property.charges.all()), [charge])

    def test_deleting_a_property_deletes_its_charges(self):
        self.make()
        self.property.delete()
        self.assertEqual(PropertyCharge.objects.count(), 0)

    def test_charges_are_ordered_by_charge_type_name(self):
        self.make(charge_type=self.service)
        self.make(charge_type=self.garbage)
        self.assertEqual(
            [c.charge_type.code for c in self.property.charges.all()], ['GARBAGE', 'SERVICE_CHARGE']
        )

    def test_two_active_charges_of_one_type_cannot_share_a_property(self):
        self.make()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(name='Block B service', amount=Decimal('2000'))

    def test_different_types_can_share_a_property(self):
        self.make(charge_type=self.service)
        self.make(charge_type=self.garbage)
        self.assertEqual(self.property.charges.count(), 2)

    def test_a_retired_charge_type_can_be_added_again(self):
        old = self.make()
        old.is_active = False
        old.save()
        new = self.make(amount=Decimal('2000'))
        self.assertTrue(new.is_active)

    def test_the_same_type_is_fine_on_another_property(self):
        other = Property.objects.create(organisation=self.organisation, name='Westlands Heights', address='x')
        self.make()
        self.make(property=other)
        self.assertEqual(PropertyCharge.objects.filter(charge_type=self.service).count(), 2)

    def test_frequency_is_monthly_by_default(self):
        self.assertEqual(self.make().frequency, Frequency.MONTHLY)

    def test_every_frequency_is_accepted(self):
        for value in ('MONTHLY', 'QUARTERLY', 'HALF_YEARLY', 'ANNUALLY', 'ONE_OFF'):
            charge = self.make(frequency=value, charge_type=ChargeType.objects.create(code=value, name=value))
            charge.full_clean()

    def test_an_unknown_frequency_is_rejected_by_validation(self):
        charge = PropertyCharge(
            organisation=self.organisation,
            property=self.property,
            charge_type=self.service,
            amount=Decimal('100'),
            frequency='FORTNIGHTLY',
        )
        with self.assertRaises(ValidationError) as caught:
            charge.full_clean()
        self.assertIn('frequency', caught.exception.message_dict)

    def test_frequency_does_not_make_a_second_active_charge_of_one_type_allowed(self):
        self.make(frequency=Frequency.MONTHLY)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(frequency=Frequency.ANNUALLY)


class UnitModelTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(name='Kilimani Ltd')
        self.property = Property.objects.create(
            organisation=self.organisation, name='Kilimani Court', address='Argwings Kodhek Rd'
        )

    def make(self, **kwargs):
        defaults = {
            'organisation': self.organisation,
            'property': self.property,
            'unit_number': 'A4',
            'rent': Decimal('25000.00'),
        }
        return Unit.objects.create(**{**defaults, **kwargs})

    def test_str_is_the_unit_number(self):
        self.assertEqual(str(self.make(unit_name='Ground floor shop')), 'A4')

    def test_unit_name_is_optional(self):
        unit = self.make()
        unit.full_clean()
        self.assertEqual(unit.unit_name, '')

    def test_active_by_default(self):
        self.assertTrue(self.make().is_active)

    def test_rent_keeps_cents_exactly(self):
        unit = self.make(rent=Decimal('25000.50'))
        unit.refresh_from_db()
        self.assertEqual(unit.rent, Decimal('25000.50'))

    def test_negative_rent_is_rejected_by_validation(self):
        unit = Unit(organisation=self.organisation, property=self.property, unit_number='B1', rent=Decimal('-1'))
        with self.assertRaises(ValidationError) as caught:
            unit.full_clean()
        self.assertIn('rent', caught.exception.message_dict)

    def test_organisation_is_required(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Unit.objects.create(property=self.property, unit_number='A4', rent=Decimal('1000'))

    def test_property_reaches_its_units(self):
        unit = self.make()
        self.assertEqual(list(self.property.units.all()), [unit])

    def test_a_property_with_units_cannot_be_deleted(self):
        self.make()
        with self.assertRaises(ProtectedError):
            self.property.delete()

    def test_unit_number_must_be_unique_within_a_property(self):
        self.make()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(unit_name='Duplicate')

    def test_the_same_unit_number_is_fine_in_another_property(self):
        other = Property.objects.create(organisation=self.organisation, name='Westlands Heights', address='x')
        self.make()
        self.make(property=other)
        self.assertEqual(Unit.objects.filter(unit_number='A4').count(), 2)

    def test_units_are_ordered_by_unit_number(self):
        self.make(unit_number='B2')
        self.make(unit_number='A1')
        self.assertEqual([u.unit_number for u in self.property.units.all()], ['A1', 'B2'])
