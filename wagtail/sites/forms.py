from django import forms
from django.utils.translation import gettext_lazy as _

from wagtail.admin.widgets import AdminPageChooser
from wagtail.models import Site


class SiteForm(forms.ModelForm):

    required_css_class = "required"

    class Meta:
        model = Site
        fields = ("sitename", "site_name", "hostname", "port")
