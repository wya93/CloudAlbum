from rest_framework import serializers, viewsets, status
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.decorators import action
from rest_framework.response import Response

class RegisterSerializer(serializers.ModelSerializer):
    password=serializers.CharField(write_only=True)

    class Meta:
        model=User
        fields=['username', 'email', 'password']
    
    def create(self, validated_data):
        user = User.objects.create_user(username=validated_data.get('username'), email=validated_data.get('password'), password=validated_data.get('password'))
        return user

class AuthViewSet(viewsets.ModelViewSet):
    queryset=User.objects.all()
    serializer_classes=RegisterSerializer

    @action(methods=['post'], detail=False, url_path='register')
    def register(self, request):
        serializer=self.get_serializer(request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': '注册成功'}, status=static.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=False, url_path='login')
    def login(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username, password)
        if user:
            return Response({'message': '登录成功'}, status=status.HTTP_200_OK)
        return Response({'message': '用户名或密码错误'}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True, url_path='login')
    def login(self, request, user_id):
        user = self.get_object()
        serializer = self.get_serializer(user)
        return Response(serializer.data)


from rest_framework.routers import DefaultRouter
from django.urls import path

router = DefaultRouter()

router.register('users', AuthViewSet)

urlpatterns = router.urls