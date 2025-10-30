from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from .serializers import RegisterSerializer, UserSerializer
from rest_framework import permissions, status, viewsets
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def create(self, request, *args, **kwargs):
         return Response(
            {'detail': '请使用 /users/register/ 接口注册用户'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    @extend_schema(                   
        request=RegisterSerializer,   # 指定请求体
        responses={200: UserSerializer},
        summary="注册用户",
        description="使用用户名、邮箱和密码注册新用户"
    )
    @action(methods=['post'], detail=False, url_path='register')
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': '注册成功', 'status': status.HTTP_200_OK})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=False, url_path='login')
    def login(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if not user:
            return Response({'message': '用户名或密码错误', 'status': status.HTTP_401_UNAUTHORIZED})
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
            'status': status.HTTP_200_OK
        })
    
    @action(methods=['get'], detail=True, url_path='me')
    def me(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)