from django.http import HttpRequest

from ..models.sites import AbstractSiteUser


def set_current_session_project(
    request: HttpRequest, site_user: AbstractSiteUser, set_default: bool = True
):
    if set_default:
        request.session["site_id"] = site_user.site_id
    request.user.site_user = site_user
    request._wagtail_site = site_user.site


class SitePermissionsMonkeyPatchMixin:
    """
    Mix this with your User Model

    This is a proxy helper to have the ability to call the permission methods directly on the site_user
    instead of user itself to keep the compatibility with all apps.

    if site_user property is set for the user obj the assumption would be
    all permission checking is going to be for that site_user and not user itself.
    """

    # Permission keys that are setting by the backend to obj to cache them ,
    # and we want them to be cached as well for site_user
    PERM_CACHE_NAMES = ("_perm_cache", "_user_perm_cache", "_group_perm_cache")

    def cache(self, func, *args, **kwargs):
        """This function prevent us from loosing advantage of caching the permissions in the user object"""
        for i in self.PERM_CACHE_NAMES:
            if hasattr(self, "_site_" + i):
                setattr(self.site_user, i, getattr(self, "_site_" + i))
        res = func(*args, **kwargs)
        for i in self.PERM_CACHE_NAMES:
            if hasattr(self.site_user, i):
                setattr(self, "_site_" + i, getattr(self.site_user, i))
        return res

    def get_user_permissions(self, obj=None):
        if hasattr(self, "site_user"):
            return self.cache(self.site_user.get_site_user_permissions, obj)
        return super().get_user_permissions(obj)

    def get_group_permissions(self, obj=None):
        if hasattr(self, "site_user"):
            return self.cache(self.site_user.get_group_permissions, obj)
        return super().get_group_permissions(obj)

    def get_all_permissions(self, obj=None):
        if hasattr(self, "site_user"):
            return self.cache(self.site_user.get_site_all_permissions, obj)
        return super().get_all_permissions(obj)

    def has_perm(self, perm, obj=None):
        if hasattr(self, "site_user"):
            return self.cache(self.site_user.site_has_perm, perm, obj)
        return super().has_perm(perm, obj)

    def has_perms(self, perm_list, obj=None):
        if hasattr(self, "site_user"):
            return self.cache(self.site_user.site_has_perms, perm_list, obj)
        return super().has_perms(perm_list, obj)

    def has_module_perms(self, app_label):
        if hasattr(self, "site_user"):
            return self.cache(self.site_user.site_has_module_perms, app_label)
        return super().has_module_perms(app_label)
