from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.farm_utils import create_farm_for_owner

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source='farm.name', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'phone',
            'first_name',
            'last_name',
            'role',
            'farm',
            'farm_name',
            'is_active_staff_member',
            'date_joined',
        )
        read_only_fields = (
            'id',
            'role',
            'farm',
            'farm_name',
            'date_joined',
            'is_active_staff_member',
        )


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    farm_name = serializers.CharField(required=False, allow_blank=True, default='My Dairy Farm')

    def validate(self, attrs):
        if User.objects.filter(email__iexact=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'This email is already registered.'})
        validate_password(attrs['password'])
        return attrs

    def create(self, validated_data):
        farm_name = validated_data.pop('farm_name', None) or 'My Dairy Farm'
        email = validated_data['email'].lower()
        username = validated_data.get('username') or email.split('@')[0]
        base = username
        i = 1
        while User.objects.filter(username=username).exists():
            username = f'{base}{i}'
            i += 1

        farm = create_farm_for_owner(name=farm_name)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone=validated_data.get('phone') or None,
            role=User.Role.OWNER,
            farm=farm,
        )
        return user


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = User.EMAIL_FIELD

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['email'] = user.email
        token['farm_id'] = user.farm_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data


class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'phone',
            'first_name',
            'last_name',
            'role',
            'farm',
            'is_active_staff_member',
            'password',
            'date_joined',
        )
        read_only_fields = ('id', 'farm', 'date_joined')

    def validate_role(self, value):
        if value not in (User.Role.WORKER, User.Role.VETERINARIAN):
            raise serializers.ValidationError('Staff role must be WORKER or VETERINARIAN.')
        return value

    def create(self, validated_data):
        request = self.context['request']
        farm = request.user.farm
        if farm is None:
            raise serializers.ValidationError('Owner has no farm.')

        password = validated_data.pop('password', None) or User.objects.make_random_password()
        email = validated_data['email'].lower()
        username = validated_data.get('username') or email.split('@')[0]
        base = username
        i = 1
        while User.objects.filter(username=username).exists():
            username = f'{base}{i}'
            i += 1
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone=validated_data.get('phone') or None,
            role=validated_data['role'],
            farm=farm,
            is_active_staff_member=True,
        )
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        validated_data.pop('farm', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
