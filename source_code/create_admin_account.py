from accounts.models import Role, User

# Bắt buộc phải có Role ADMIN trong DB trước (đã chạy lệnh get_or_create ở bước trước)
admin_role = Role.objects.get(role_name='ADMIN')

admin = User.objects.create(
    email='admin@aptech.edu.vn', 
    role=admin_role, 
    status='ACTIVE'
)
admin.set_password('123456') # Lõi băm PBKDF2 tự động kích hoạt
admin.save()
exit()