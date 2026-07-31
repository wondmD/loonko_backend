import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dft_backend.settings')
django.setup()

from cattle.models import Cattle
from accounts.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from io import BytesIO

farm = User.objects.first().farm

img = Image.new('RGB', (100, 100), color='red')
f = BytesIO()
img.save(f, format='JPEG')
f.seek(0)
upload = SimpleUploadedFile("test.jpg", f.read(), content_type="image/jpeg")

c = Cattle(farm=farm, tag_id="TEST002", sex="FEMALE")
c.photo_front = upload
c.save()

print(c.photo_front.name)
