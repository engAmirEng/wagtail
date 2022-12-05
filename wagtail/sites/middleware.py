import re

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from wagtail.models.sites import get_site_user_model

SiteUser = get_site_user_model()


class SiteUserMiddleware(MiddlewareMixin):
    """
    Middleware that sets `_wagtail_site` attribute to request object
    and `site_user` attribute to request.user object.
    It should be located after user is set to request(after `AuthenticationMiddleware`)
    """

    def process_request(self, request):
        if not request.user.is_authenticated:
            # The hole point is to be able to handle user permissions,
            # so if not `is_authenticated` the view should trigger it
            return
        paths = getattr(settings, "PATHS_NEED_SITE", None)
        if not paths:
            # The urls that not included but need this behavior
            # should use `set_current_project_site` decorator
            return
        if any([re.match(pattern, request.path) for pattern in paths]):
            SiteUser.find_for_request(request)
