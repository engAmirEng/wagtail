from django.http import HttpRequest

from models.sites import AbstractSiteUser


def set_current_session_project(
    request: HttpRequest, site_user: AbstractSiteUser, set_default: bool = True
):
    if set_default:
        request.session["site_id"] = site_user.site_id
    request.user.site_user = site_user
    request._wagtail_site = site_user.site
