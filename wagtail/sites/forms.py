from django import forms
from django.utils.translation import gettext_lazy as _

from wagtail.admin.widgets import AdminPageChooser
from wagtail.models import Site


class SiteForm(forms.ModelForm):

    required_css_class = "required"

    class Meta:
        model = Site
        fields = ("sitename", "site_name", "hostname", "port")

    def __init__(self, *args, user=None, instance=None, **kwargs):
        if not instance and not user:
            raise Exception("user is required for creating site")
        self.user = user
        super(SiteForm, self).__init__(*args, instance=instance, **kwargs)

    def save(self, commit=True):
        if not commit:
            return super(SiteForm, self).save(commit=commit)
        return self.instance.save(create_site_user_for=self.user)
