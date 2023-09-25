from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver
from phonenumber_field.modelfields import PhoneNumberField
import uuid
from django.urls import reverse


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_employer = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class JobPosting(models.Model):
    INDUSTRY_CHOICES = (
        ('1', 'Unspecified'),
        ('2', 'Consulting'),
        ('3', 'Accounting'),
        ('4', 'Finance'),
        ('5', 'Advertising'),
        ('6', 'Human Resources'),
        ('7', 'Sales'),
        ('8', 'News & Media'),
        ('9', 'Insurance'),
        ('10', 'Entertainment'),
        ('11', 'Marketing'),
        ('12', 'Science & Research'),
        ('13', 'Tech'),
        ('14', 'Healthcare'),
        ('15', 'Manufacturing'),
    )
    COUNTRY_CHOICES = (
        ('RU', 'Russia'),
        ('KZ', 'Kazakhstan'),
        ('BY', 'Belarus'),
        ('UZ', 'Uzbekistan'),
        ('AZ', 'Azerbaijan'),
        ('GE', 'Georgia'),
        ('KG', 'Kyrgyzstan'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    industry = models.ForeignKey('Industry', on_delete=models.CASCADE)
    country = models.CharField(max_length=3, choices=COUNTRY_CHOICES, default='KZ')
    city = models.CharField(max_length=100)
    job_description = models.TextField(max_length=10000)
    additional_information = models.TextField(max_length=10000, null=True, blank=True)
    experience_required = models.CharField(max_length=10000)
    does_not_need_experience = models.BooleanField(default=False)
    is_remote = models.BooleanField(default=False)
    is_part_time = models.BooleanField(default=False)
    employer = models.ForeignKey('User', on_delete=models.CASCADE, related_name='employers')
    job_open_date = models.DateTimeField(auto_now_add=True)
    min_salary = models.DecimalField(max_digits=10, decimal_places=2)
    max_salary = models.DecimalField(max_digits=10, decimal_places=2)
    visible = models.BooleanField(default=True)
    liked = models.ManyToManyField('User', blank=True, related_name='liked_post')

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('job_posting', kwargs={'job_posting_uuid': self.id})


class Industry(models.Model):
    title = models.CharField(max_length=200)

    class Meta:
        verbose_name_plural = "Industries"

    def __str__(self):
        return self.title


class JobSeekerProfile(models.Model):
    GENDER_CHOICES = (
        ('P', 'Prefer not to say'),
        ('M', 'Male'),
        ('F', 'Female'),
        ('U', 'Unspecified'),
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='U')
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.URLField(null=True, blank=True, verbose_name='Profile image')
    phone_number = PhoneNumberField(null=True, blank=True)
    telegram_ID = models.CharField(max_length=50, null=True, blank=True)
    preferred_country = models.CharField(max_length=100, null=True, blank=True)
    preferred_location = models.CharField(max_length=100, null=True, blank=True)
    preferred_industry = models.CharField(max_length=3, choices=JobPosting.INDUSTRY_CHOICES, default='1')

    def __str__(self):
        return f'{self.user}_profile'


class EmployerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telegram_ID = models.CharField(max_length=50, null=True, blank=True)
    company_name = models.CharField(max_length=150, null=True, blank=True)
    company_logo = models.URLField(null=True, blank=True, verbose_name='Company logo')
    phone_number = PhoneNumberField(null=True, blank=True)

    def __str__(self):
        return f'{self.user}_profile'



# @receiver(post_save, sender=User)
# def create_user_profile(sender, instance, created, **kwargs):
#     """
#     Creates user profile if it does not exist
#     :param sender: User
#     :param instance:
#     :param created:
#     :param kwargs:
#     :return:
#     """
#     if created:
#         if instance.is_employer:
#             EmployerProfile.objects.get_or_create(user=instance)
#         else:
#             JobSeekerProfile.objects.get_or_create(user=instance)

# @receiver(post_save, sender=User)
# def save_user_profile(sender, instance, **kwargs):
#     instance.profile.save()