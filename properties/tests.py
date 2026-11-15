from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient

from identity.models import Membership, Organisation, Permission, Role

from .models import Property

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
