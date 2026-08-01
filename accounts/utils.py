from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

def send_verification_email(user):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    verify_link = f"{frontend_url}/verify-email?uid={uid}&token={token}"
    
    subject = "Verify your Loonkoo Farm Account"
    message = f"Hello {user.first_name or 'Farmer'},\n\n" \
              f"Thank you for registering on Loonkoo! Please verify your email address by clicking the link below:\n\n" \
              f"{verify_link}\n\n" \
              f"If you did not create this account, please ignore this email."
              
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )

def send_staff_invitation_email(user, inviter=None):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    setup_link = f"{frontend_url}/set-password?uid={uid}&token={token}"
    
    inviter_name = f"{inviter.first_name} {inviter.last_name}".strip() if inviter else "A farm owner"
    
    subject = "You have been invited to join a Farm on Loonkoo"
    message = f"Hello {user.first_name or user.email},\n\n" \
              f"{inviter_name} has invited you to join their farm as a {user.get_role_display()}.\n\n" \
              f"Please click the link below to set your password and access the farm dashboard:\n\n" \
              f"{setup_link}\n\n" \
              f"Welcome to Loonkoo!"
              
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
