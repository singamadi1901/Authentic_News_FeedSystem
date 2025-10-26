# news_feed/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

# This form will handle the creation of new users.
class SignUpForm(UserCreationForm):
    # We add an email field, which is required for registration.
    email = forms.EmailField(max_length=254, required=True, help_text='Required. Please enter a valid email address.')

    class Meta:
        model = User
        # Define the fields to be displayed in the signup form.
        fields = ('username', 'email', 'password', 'password2')
