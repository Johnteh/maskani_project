from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from rest_framework import serializers
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from common.phone import normalize_phone

from .models import Membership, Organisation, Permission, Profile, Role
from .viewsets import OrgModelViewSet

User = get_user_model()


class NormalizePhoneTests(SimpleTestCase):
    def test_formats(self):
        for raw, expected in [
            ('0712345678', '+254712345678'),
            ('+254712345678', '+254712345678'),
            ('254712345678', '+254712345678'),
            ('0712 345-678', '+254712345678'),
            ('00254712345678', '+254712345678'),
            ('+447911123456', '+447911123456'),
            ('', None),
            (None, None),
            ('  ', None),
        ]:
            self.assertEqual(normalize_phone(raw), expected, raw)


class UserModelTests(TestCase):
    def test_create_user_normalises_phone(self):
        user = User.objects.create_user('0712345678', password='pass12345')
        self.assertEqual(user.phone, '+254712345678')
        self.assertEqual(str(user), '+254712345678')
        self.assertIsNone(user.email)
        self.assertFalse(user.phone_verified)

    def test_phone_is_required(self):
        for missing in (None, '', '  '):
            with self.assertRaises(ValueError):
                User.objects.create_user(missing, password='pass12345')

    def test_email_is_optional_and_many_users_can_have_none(self):
        User.objects.create_user('0712345678', password='pass12345')
        User.objects.create_user('0722345678', password='pass12345', email='')
        User.objects.create_user('0732345678', password='pass12345', email='a@example.com')

    def test_duplicate_phone_rejected(self):
        User.objects.create_user('0712345678', password='pass12345')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('+254712345678', password='pass12345')

    def test_duplicate_email_rejected(self):
        User.objects.create_user('0712345678', password='pass12345', email='a@example.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('0722345678', password='pass12345', email='a@example.com')

    def test_full_clean_keeps_missing_email_null(self):
        user = User.objects.create_user('0712345678', password='pass12345')
        user.full_clean()
        user.save()
        user.refresh_from_db()
        self.assertIsNone(user.email)

    def test_superuser(self):
        admin = User.objects.create_superuser('0712345678', password='pass12345')
        self.assertTrue(admin.is_staff and admin.is_superuser)


class ProfileTests(TestCase):
    def test_profile_created_with_every_user(self):
        user = User.objects.create_user('0712345678', password='pass12345')
        admin = User.objects.create_superuser('0722345678', password='pass12345')
        self.assertEqual(Profile.objects.count(), 2)
        self.assertEqual(user.profile.user, user)
        self.assertEqual(admin.profile.user, admin)
        self.assertTrue(user.profile.sms_opt_in)
        self.assertEqual(user.profile.id_number, '')

    def test_profile_not_duplicated_on_user_save(self):
        user = User.objects.create_user('0712345678', password='pass12345')
        user.first_name = 'Amina'
        user.save()
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_profile_deleted_with_user(self):
        user = User.objects.create_user('0712345678', password='pass12345')
        user.delete()
        self.assertEqual(Profile.objects.count(), 0)


class AuthApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def register(self, **extra):
        data = {'phone': '0712345678', 'password': 'pass12345', **extra}
        return self.client.post('/api/auth/register/', data, format='json')

    def login(self, phone, password='pass12345'):
        return self.client.post('/api/auth/token/', {'phone': phone, 'password': password}, format='json')

    def test_register_with_phone_only(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        user = response.json()['user']
        self.assertEqual(user['phone'], '+254712345678')
        self.assertIsNone(user['email'])
        self.assertFalse(user['phone_verified'])
        self.assertTrue(Profile.objects.filter(user__phone='+254712345678').exists())

    def test_register_with_optional_email(self):
        response = self.register(email='a@example.com', first_name='Amina')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['email'], 'a@example.com')

    def test_register_needs_a_valid_phone(self):
        no_phone = self.client.post('/api/auth/register/', {'password': 'pass12345'}, format='json')
        self.assertEqual(no_phone.status_code, 400)
        self.assertIn('phone', no_phone.json())
        self.assertEqual(self.register(phone='12').status_code, 400)
        self.assertEqual(self.register(phone='abc').status_code, 400)

    def test_register_rejects_duplicates(self):
        self.assertEqual(self.register(email='a@example.com').status_code, 200)
        same_phone = self.register(phone='+254712345678')
        self.assertEqual(same_phone.status_code, 400)
        self.assertIn('phone', same_phone.json())
        same_email = self.register(phone='0722345678', email='a@example.com')
        self.assertEqual(same_email.status_code, 400)
        self.assertIn('email', same_email.json())

    def test_register_rejects_short_password(self):
        self.assertEqual(self.register(password='short').status_code, 400)

    def test_login_with_any_phone_format(self):
        self.register()
        for form in ('0712345678', '+254712345678', '254712345678', '0712 345 678'):
            response = self.login(form)
            self.assertEqual(response.status_code, 200, form)
            self.assertIn('access', response.json())

    def test_login_wrong_password(self):
        self.register()
        self.assertEqual(self.login('0712345678', 'wrong-password').status_code, 401)

    def test_login_unknown_phone(self):
        self.assertEqual(self.login('0799999999').status_code, 401)

    def test_login_needs_a_phone(self):
        self.assertEqual(self.login('   ').status_code, 400)
        response = self.client.post('/api/auth/token/', {'password': 'pass12345'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_email_is_not_a_login(self):
        self.register(email='a@example.com')
        self.assertEqual(self.login('a@example.com').status_code, 401)

    def test_inactive_user_cannot_log_in(self):
        self.register()
        User.objects.filter(phone='+254712345678').update(is_active=False)
        self.assertEqual(self.login('0712345678').status_code, 401)

    def test_me_and_refresh(self):
        self.register()
        tokens = self.login('0712345678').json()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
        me = self.client.get('/api/auth/me/')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()['phone'], '+254712345678')
        self.client.credentials()
        refreshed = self.client.post('/api/auth/token/refresh/', {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(refreshed.status_code, 200)


class AdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('0712345678', password='pass12345')

    def test_superuser_has_permissions(self):
        self.assertTrue(self.admin.has_perm('identity.view_user'))
        self.assertTrue(self.admin.has_module_perms('identity'))
        self.assertFalse(User.objects.create_user('0722345678', password='pass12345').has_perm('identity.view_user'))

    def test_names(self):
        self.admin.first_name, self.admin.last_name = 'Amina', 'Odhiambo'
        self.assertEqual(self.admin.get_full_name(), 'Amina Odhiambo')
        self.assertEqual(self.admin.get_short_name(), 'Amina')


class MembershipPermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('0712345678', password='pass12345')
        self.org = Organisation.objects.create(name='Kilimani Court')
        self.read = Permission.objects.create(code='property.read', name='Read properties')
        self.edit = Permission.objects.create(code='property.edit', name='Edit properties')
        self.delete = Permission.objects.create(code='property.delete', name='Delete properties')
        self.membership = Membership.objects.create(user=self.user, organisation=self.org)

    def role(self, name, *permissions):
        role = Role.objects.create(name=name)
        role.permissions.set(permissions)
        self.membership.roles.add(role)
        return role

    def fresh(self):
        return Membership.objects.get(pk=self.membership.pk)

    def test_no_roles_grants_nothing(self):
        self.assertEqual(self.membership.permission_codes, frozenset())
        self.assertFalse(self.membership.has_permission('property.read'))

    def test_role_grants_its_permissions_only(self):
        self.role('caretaker', self.read)
        membership = self.fresh()
        self.assertTrue(membership.has_permission('property.read'))
        self.assertFalse(membership.has_permission('property.edit'))

    def test_several_roles_are_combined(self):
        self.role('viewer', self.read)
        self.role('editor', self.read, self.edit)
        self.assertEqual(self.fresh().permission_codes, {'property.read', 'property.edit'})

    def test_unknown_code_is_denied(self):
        self.role('caretaker', self.read)
        self.assertFalse(self.fresh().has_permission('nonsense'))

    def test_inactive_membership_grants_nothing(self):
        self.role('caretaker', self.read)
        Membership.objects.filter(pk=self.membership.pk).update(is_active=False)
        self.assertFalse(self.fresh().has_permission('property.read'))

    def test_permissions_do_not_leak_between_memberships(self):
        self.role('caretaker', self.read)
        other_org = Organisation.objects.create(name='Karen House')
        other = Membership.objects.create(user=self.user, organisation=other_org)
        self.assertFalse(other.has_permission('property.read'))

    def test_one_query_per_membership(self):
        self.role('editor', self.read, self.edit)
        membership = self.fresh()
        with self.assertNumQueries(1):
            membership.has_permission('property.read')
            membership.has_permission('property.edit')
            membership.has_permission('property.delete')


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ('ref_id', 'user', 'is_active')


class MembershipViewSet(OrgModelViewSet):
    """Memberships are organisation-scoped, so they stand in for a real model such as Property."""

    queryset = Membership.objects.all()
    serializer_class = MembershipSerializer
    required_permissions = {
        'list': 'member.read',
        'retrieve': 'member.read',
        'create': 'member.add',
    }


LIST = MembershipViewSet.as_view({'get': 'list', 'post': 'create'})
DETAIL = MembershipViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'})


class OrgViewSetTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.read = Permission.objects.create(code='member.read', name='Read members')
        self.add = Permission.objects.create(code='member.add', name='Add members')
        self.edit = Permission.objects.create(code='member.edit', name='Edit members')
        self.kilimani = Organisation.objects.create(name='Kilimani Court')
        self.karen = Organisation.objects.create(name='Karen House')
        self.user = User.objects.create_user('0712345678', password='pass12345')
        self.other = User.objects.create_user('0722345678', password='pass12345')

    def join(self, user, organisation, *permissions, **extra):
        membership = Membership.objects.create(user=user, organisation=organisation, **extra)
        role = Role.objects.create(name=f'{user.phone}@{organisation.name}')
        role.permissions.set(permissions)
        membership.roles.add(role)
        return membership

    def call(self, view, method, user, org=None, header=None, data=None, **kwargs):
        headers = {}
        if org is not None:
            headers['HTTP_X_ORGANISATION'] = str(org.ref_id)
        if header is not None:
            headers['HTTP_X_ORGANISATION'] = header
        request = getattr(self.factory, method)('/', data, format='json', **headers)
        if user is not None:
            force_authenticate(request, user=user)
        return view(request, **kwargs)

    def test_member_with_permission_sees_only_their_organisation(self):
        mine = self.join(self.user, self.kilimani, self.read)
        self.join(self.other, self.karen)
        response = self.call(LIST, 'get', self.user, self.kilimani)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['ref_id'] for row in response.data], [str(mine.ref_id)])

    def test_unauthenticated_is_401(self):
        self.assertEqual(self.call(LIST, 'get', None, self.kilimani).status_code, 401)

    def test_missing_or_malformed_header_is_400(self):
        self.join(self.user, self.kilimani, self.read)
        self.assertEqual(self.call(LIST, 'get', self.user).status_code, 400)
        self.assertEqual(self.call(LIST, 'get', self.user, header='not-a-uuid').status_code, 400)

    def test_not_a_member_is_403(self):
        self.join(self.user, self.kilimani, self.read)
        self.assertEqual(self.call(LIST, 'get', self.user, self.karen).status_code, 403)

    def test_unknown_organisation_is_403_like_not_a_member(self):
        self.join(self.user, self.kilimani, self.read)
        unknown = '00000000-0000-4000-8000-000000000000'
        self.assertEqual(self.call(LIST, 'get', self.user, header=unknown).status_code, 403)

    def test_inactive_membership_is_403(self):
        self.join(self.user, self.kilimani, self.read, is_active=False)
        self.assertEqual(self.call(LIST, 'get', self.user, self.kilimani).status_code, 403)

    def test_member_without_the_permission_is_403(self):
        self.join(self.user, self.kilimani, self.add)
        self.assertEqual(self.call(LIST, 'get', self.user, self.kilimani).status_code, 403)

    def test_permissions_come_from_the_header_organisation(self):
        self.join(self.user, self.kilimani, self.read)
        self.join(self.user, self.karen)
        self.assertEqual(self.call(LIST, 'get', self.user, self.kilimani).status_code, 200)
        self.assertEqual(self.call(LIST, 'get', self.user, self.karen).status_code, 403)

    def test_action_not_listed_is_denied(self):
        mine = self.join(self.user, self.kilimani, self.read, self.add, self.edit)
        response = self.call(DETAIL, 'patch', self.user, self.kilimani, data={'is_active': False}, pk=mine.pk)
        self.assertEqual(response.status_code, 403)

    def test_other_organisations_object_is_404(self):
        self.join(self.user, self.kilimani, self.read)
        theirs = self.join(self.other, self.karen)
        self.assertEqual(self.call(DETAIL, 'get', self.user, self.kilimani, pk=theirs.pk).status_code, 404)

    def test_create_is_placed_in_the_header_organisation(self):
        self.join(self.user, self.kilimani, self.add)
        response = self.call(LIST, 'post', self.user, self.kilimani, data={'user': self.other.pk})
        self.assertEqual(response.status_code, 201)
        created = Membership.objects.get(user=self.other)
        self.assertEqual(created.organisation, self.kilimani)

    def test_create_needs_the_add_permission(self):
        self.join(self.user, self.kilimani, self.read)
        response = self.call(LIST, 'post', self.user, self.kilimani, data={'user': self.other.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Membership.objects.filter(user=self.other).exists())
