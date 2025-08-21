from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class ParentUserManager(BaseUserManager):
    """Custom user model manager where email is the unique identifier."""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(email, password, **extra_fields)


class ParentUser(AbstractUser):
    """Custom user model for parents."""
    username = None
    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    objects = ParentUserManager()
    
    def __str__(self):
        return self.email


class Child(models.Model):
    """Model representing a child associated with a parent."""
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='children'
    )
    name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    school = models.CharField(max_length=200, blank=True)
    grade = models.CharField(max_length=50, blank=True)
    
    class Meta:
        verbose_name_plural = 'children'
    
    def __str__(self):
        return self.name


class LunchboxAssignment(models.Model):
    """Model to track which lunchbox is assigned to which child."""
    child = models.OneToOneField(
        Child,
        on_delete=models.CASCADE,
        related_name='lunchbox_assignment'
    )
    lunchbox_id = models.CharField(max_length=100, unique=True)
    assigned_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.child.name}'s Lunchbox ({self.lunchbox_id})"


class ParentNotification(models.Model):
    """Model to store notifications for parents."""
    NOTIFICATION_TYPES = [
        ('food_eaten', 'Food Eaten'),
        ('food_spoiled', 'Food Spoiled'),
        ('temperature_alert', 'Temperature Alert'),
        ('low_battery', 'Low Battery'),
    ]
    
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.title}"
