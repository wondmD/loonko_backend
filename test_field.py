import django
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.fields.files import FieldFile, FileField

class DummyModel:
    pass

f = FileField()
upload = SimpleUploadedFile("test.jpg", b"dummy")
field_file = FieldFile(DummyModel(), f, upload.name)
field_file.file = upload
field_file._committed = False

print(hasattr(field_file, '_committed'))
print(hasattr(upload, '_committed'))
