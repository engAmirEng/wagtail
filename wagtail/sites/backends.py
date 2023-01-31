from django.contrib.auth.models import Permission
from django.db.models import OuterRef, Q, Exists
from wagtail.models.sites import get_site_user_model

SiteUserModel = get_site_user_model()


class BaseSiteAuthBackend:
    """Permision management for SiteUser,
    should be used with another fullyfunctioning backend"""

    def authenticate(self):
        return "This backend does not implement authentication"

    def get_site_user_permissions(self, site_user_obj, obj=None):
        return set()

    def get_site_group_permissions(self, site_user_obj, obj=None):
        return set()

    def get_site_all_permissions(self, site_user_obj, obj=None):
        return {
            *self.get_site_user_permissions(site_user_obj, obj=obj),
            *self.get_site_group_permissions(site_user_obj, obj=obj),
        }

    def has_site_perm(self, site_user_obj, perm, obj=None):
        return perm in self.get_site_all_permissions(site_user_obj, obj=obj)


class SiteAuthBackend(BaseSiteAuthBackend):
    def _get_site_user_permissions(self, site_user_obj):
        return site_user_obj.site_user_permissions.all()

    def _get_site_group_permissions(self, site_user_obj):
        user_groups_field = get_site_user_model()._meta.get_field("groups")
        user_groups_query = (
            "permission_sitegroups__%s" % user_groups_field.related_query_name()
        )
        return Permission.objects.filter(**{user_groups_query: site_user_obj})

    def _get_site_permissions(self, site_user_obj, obj, from_name):
        """
        Return the permissions of `site_user_obj` from `from_name`. `from_name` can
        be either "group" or "user" to return permissions from
        `_get_site_group_permissions` or `_get_site_user_permissions` respectively.
        """
        if not site_user_obj.is_active or obj is not None:
            return set()

        perm_cache_name = "_%s_perm_cache" % from_name
        if not hasattr(site_user_obj, perm_cache_name):
            if site_user_obj.is_superuser:
                perms = Permission.objects.filter(permission_siteusers=site_user_obj)
            else:
                perms = getattr(self, "_get_site_%s_permissions" % from_name)(
                    site_user_obj
                )
            perms = perms.values_list("content_type__app_label", "codename").order_by()
            setattr(
                site_user_obj,
                perm_cache_name,
                {"%s.%s" % (ct, name) for ct, name in perms},
            )
        return getattr(site_user_obj, perm_cache_name)

    def get_site_user_permissions(self, user_obj, obj=None):
        """
        Return a set of permission strings the site_user `site_user_obj` has from their
        `site_user_permissions`.
        """
        return self._get_site_permissions(user_obj, obj, "user")

    def get_site_group_permissions(self, user_obj, obj=None):
        """
        Return a set of permission strings the site_user `site_user_obj` has from the
        groups they belong.
        """
        return self._get_site_permissions(user_obj, obj, "group")

    def get_site_all_permissions(self, site_user_obj, obj=None):
        if not site_user_obj.is_active or obj is not None:
            return set()
        if not hasattr(site_user_obj, "_perm_cache"):
            site_user_obj._perm_cache = super().get_site_all_permissions(site_user_obj)
        return site_user_obj._perm_cache

    def has_site_perm(self, site_user_obj, perm, obj=None):
        return site_user_obj.is_active and super().has_site_perm(
            site_user_obj, perm, obj=obj
        )

    def has_module_site_perms(self, site_user_obj, app_label):
        """
        Return True if site_user_obj has any permissions in the given app_label.
        """
        return site_user_obj.is_active and any(
            perm[: perm.index(".")] == app_label
            for perm in self.get_site_all_permissions(site_user_obj)
        )

    def site_with_perm(self, perm, is_active=True, include_superusers=True, obj=None):
        """
        Return site_users that have permission "perm". By default, filter out
        inactive users and include superusers.
        """
        if isinstance(perm, str):
            try:
                app_label, codename = perm.split(".")
            except ValueError:
                raise ValueError(
                    "Permission name should be in the form "
                    "app_label.permission_codename."
                )
        elif not isinstance(perm, Permission):
            raise TypeError(
                "The `perm` argument must be a string or a permission instance."
            )

        if obj is not None:
            return SiteUserModel._default_manager.none()

        permission_q = Q(permission_sitegroups__sitegroup_siteusers=OuterRef("pk")) | Q(
            permission_siteusers=OuterRef("pk")
        )
        if isinstance(perm, Permission):
            permission_q &= Q(pk=perm.pk)
        else:
            permission_q &= Q(codename=codename, content_type__app_label=app_label)

        user_q = Exists(Permission.objects.filter(permission_q))
        if include_superusers:
            user_q |= Q(is_superuser=True)
        if is_active is not None:
            user_q &= Q(is_active=is_active)

        return SiteUserModel._default_manager.filter(user_q)
