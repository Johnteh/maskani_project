from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from common.phone import normalize_phone

from .models import Profile

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
