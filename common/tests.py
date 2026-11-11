from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from .serializers import BaseModelSerializer, InternalFieldsMixin
from .viewsets import BaseModelViewSet

User = get_user_model()


class InternalFieldsMixinTests(SimpleTestCase):
    class Plain(serializers.Serializer):
        name = serializers.CharField()
        secret = serializers.CharField()

    class Hiding(InternalFieldsMixin, Plain):
        internal_fields = ('secret',)

    def test_nothing_hidden_by_default(self):
        class Default(InternalFieldsMixin, self.Plain):
            pass

        self.assertEqual(list(Default().fields), ['name', 'secret'])

    def test_named_fields_are_removed(self):
        self.assertEqual(list(self.Hiding().fields), ['name'])

    def test_hidden_field_is_not_shown(self):
        data = self.Hiding({'name': 'A4', 'secret': 'x'}).data
        self.assertEqual(data, {'name': 'A4'})

    def test_hidden_field_from_client_is_ignored(self):
        serializer = self.Hiding(data={'name': 'A4', 'secret': 'x'})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data, {'name': 'A4'})

    def test_unknown_name_in_internal_fields_is_harmless(self):
        class Typo(InternalFieldsMixin, self.Plain):
            internal_fields = ('nope',)

        self.assertEqual(list(Typo().fields), ['name', 'secret'])


class ReadWriteSerializerMixinTests(SimpleTestCase):
    class ReadSerializer(serializers.Serializer):
        pass

    class WriteSerializer(serializers.Serializer):
        pass

    class DefaultSerializer(serializers.Serializer):
        pass

    def serializer_class_for(self, method, **attrs):
        view = BaseModelViewSet()
        view.serializer_class = self.DefaultSerializer
        for name, value in attrs.items():
            setattr(view, name, value)
        view.request = getattr(APIRequestFactory(), method)('/')
        return view.get_serializer_class()

    def test_reads_use_the_read_serializer(self):
        for method in ('get', 'head', 'options'):
            self.assertIs(
                self.serializer_class_for(
                    method,
                    read_serializer_class=self.ReadSerializer,
                    write_serializer_class=self.WriteSerializer,
                ),
                self.ReadSerializer,
                method,
            )

    def test_writes_use_the_write_serializer(self):
        for method in ('post', 'put', 'patch', 'delete'):
            self.assertIs(
                self.serializer_class_for(
                    method,
                    read_serializer_class=self.ReadSerializer,
                    write_serializer_class=self.WriteSerializer,
                ),
                self.WriteSerializer,
                method,
            )

    def test_falls_back_to_serializer_class_when_neither_is_set(self):
        self.assertIs(self.serializer_class_for('get'), self.DefaultSerializer)
        self.assertIs(self.serializer_class_for('post'), self.DefaultSerializer)

    def test_only_the_set_serializer_is_swapped(self):
        self.assertIs(self.serializer_class_for('get', read_serializer_class=self.ReadSerializer), self.ReadSerializer)
        self.assertIs(self.serializer_class_for('post', read_serializer_class=self.ReadSerializer), self.DefaultSerializer)


class BaseModelSerializerTests(SimpleTestCase):
    def test_hides_nothing_by_default(self):
        class Plain(BaseModelSerializer):
            class Meta:
                model = User
                fields = ('phone', 'email')

        self.assertEqual(list(Plain().fields), ['phone', 'email'])

    def test_a_subclass_can_hide_fields(self):
        class Hiding(BaseModelSerializer):
            internal_fields = ('email',)

            class Meta:
                model = User
                fields = ('phone', 'email')

        self.assertEqual(list(Hiding().fields), ['phone'])
