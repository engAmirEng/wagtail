import logging
from collections import namedtuple

from django.apps import apps
from django.conf import settings
from django.contrib import auth
from django.contrib.auth.models import (
    _user_get_permissions,
    _user_has_perm,
    _user_has_module_perms,
)
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.validators import MinLengthValidator
from django.db import models, transaction
from django.db.models import (
    Case,
    IntegerField,
    Q,
    When,
    UniqueConstraint,
    CheckConstraint,
)
from django.db.models.functions import Lower
from django.http.request import split_domain_port, HttpRequest
from django.utils.itercompat import is_iterable
from django.utils.translation import gettext_lazy as _


logger = logging.getLogger("wagtail.sites")

SiteUser = None

MATCH_HOSTNAME_PORT = 0
MATCH_HOSTNAME = 1


def get_site_for_hostname(hostname, port):
    """Return the wagtailcore.Site object for the given hostname and port."""
    Site = apps.get_model("wagtailcore.Site")

    sites = list(
        Site.objects.annotate(
            match=Case(
                # annotate the results by best choice descending
                # put exact hostname+port match first
                When(hostname=hostname, port=port, then=MATCH_HOSTNAME_PORT),
                # then put hostname+default (better than just hostname or just default)
                When(hostname=hostname, then=MATCH_HOSTNAME),
                # because of the filter below, if it's not default then its a hostname match
                output_field=IntegerField(),
            )
        )
        .filter(hostname=hostname)
        .order_by("match")
        .select_related("root_page")
    )

    if sites:
        # if there's a unique match or hostname (with port or default) match
        if len(sites) == 1 or sites[0].match == MATCH_HOSTNAME_PORT:
            return sites[0]
        logger.warning(
            f"requested site for {hostname}:{port} has more than one candidate"
        )
        return sites[0]

    raise Site.DoesNotExist()


class SiteManager(models.Manager):
    def get_queryset(self):
        return super(SiteManager, self).get_queryset().order_by(Lower("hostname"))

    def get_by_natural_key(self, hostname, port):
        return self.get(hostname=hostname, port=port)


SiteRootPath = namedtuple("SiteRootPath", "site_id root_path root_url language_code")

SITE_ROOT_PATHS_CACHE_KEY = "wagtail_site_root_paths"
# Increase the cache version whenever the structure SiteRootPath tuple changes
SITE_ROOT_PATHS_CACHE_VERSION = 2


class Site(models.Model):
    hostname = models.CharField(
        verbose_name=_("hostname"), max_length=255, db_index=True
    )
    port = models.IntegerField(
        verbose_name=_("port"),
        default=80,
        help_text=_(
            "Set this to something other than 80 if you need a specific port number to appear in URLs"
            " (e.g. development on port 8000). Does not affect request handling (so port forwarding still works)."
        ),
    )
    sitename = models.SlugField(
        verbose_name=_("sitename"),
        max_length=31,
        unique=True,
        validators=[MinLengthValidator(5)],
        help_text=_("The username for the site."),
    )
    site_name = models.CharField(
        verbose_name=_("site name"),
        max_length=255,
        blank=True,
        help_text=_("Human-readable name for the site."),
    )
    root_page = models.ForeignKey(
        "Page",
        verbose_name=_("root page"),
        related_name="sites_rooted_here",
        on_delete=models.CASCADE,
    )

    @property
    def is_default_site(self):
        """
        Monkey fix until I find the problem
        """
        return False

    objects = SiteManager()

    class Meta:
        unique_together = ("hostname", "port")
        verbose_name = _("site")
        verbose_name_plural = _("sites")
        constraints = [CheckConstraint(check=Q(depth=1), name="root_page_be_root")]

    def natural_key(self):
        return (self.hostname, self.port)

    def __str__(self):
        if self.site_name:
            return self.site_name
        else:
            return self.hostname + ("" if self.port == 80 else (":%d" % self.port))

    def clean(self):
        self.hostname = self.hostname.lower()

    def save(self, *args, create_site_user_for=None, **kwargs):
        if not self.pk:
            from wagtail.models import Page

            with transaction.atomic():
                self.root_page = Page.add_root(title="Root")
                super(Site, self).save(*args, *kwargs)
                if create_site_user_for and self.pk:
                    SiteUser = get_site_user_model()
                    SiteUser.objects.create_site_creator(create_site_user_for, self)
            return self
        super(Site, self).save(*args, **kwargs)
        return self

    @staticmethod
    def find_for_request(request):
        """
        Find the site object responsible for responding to this HTTP
        request object. Try:

        * unique hostname first
        * then hostname and port
        * if there is no matching hostname at all, or no matching
          hostname:port combination, fall back to the unique default site,
          or raise an exception

        NB this means that high-numbered ports on an extant hostname may
        still be routed to a different hostname which is set as the default

        The site will be cached via request._wagtail_site
        """

        if request is None:
            return None

        if not hasattr(request, "_wagtail_site"):
            site = Site._find_for_request(request)
            setattr(request, "_wagtail_site", site)
        return request._wagtail_site

    @staticmethod
    def _find_for_request(request):
        hostname = split_domain_port(request.get_host())[0]
        port = request.get_port()
        try:
            site = get_site_for_hostname(hostname, port)
        except Site.DoesNotExist:
            raise
        return site

    @property
    def root_url(self):
        if self.port == 80:
            return "http://%s" % self.hostname
        elif self.port == 443:
            return "https://%s" % self.hostname
        else:
            return "http://%s:%d" % (self.hostname, self.port)

    def get_site_root_paths(self):
        """
        Return a list of `SiteRootPath` instances, most specific path
        first - used to translate url_paths into actual URLs with hostnames

        Each root path is an instance of the `SiteRootPath` named tuple,
        and have the following attributes:

        - `site_id` - The ID of the Site record
        - `root_path` - The internal URL path of the site's home page (for example '/home/')
        - `root_url` - The scheme/domain name of the site (for example 'https://www.example.com/')
        - `language_code` - The language code of the site (for example 'en')
        """
        if getattr(settings, "WAGTAIL_I18N_ENABLED", False):
            return [
                SiteRootPath(
                    self.id,
                    root_page.url_path,
                    self.root_url,
                    root_page.locale.language_code,
                )
                for root_page in self.root_page.get_translations(
                    inclusive=True
                ).select_related("locale")
            ]
        else:
            return [
                SiteRootPath(
                    self.id,
                    self.root_page.url_path,
                    self.root_url,
                    self.root_page.locale.language_code,
                )
            ]

    @staticmethod
    def clear_site_root_paths_cache():
        cache.delete(SITE_ROOT_PATHS_CACHE_KEY, version=SITE_ROOT_PATHS_CACHE_VERSION)


class SiteGroupManager(models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name, site_id):
        return self.get(name=name, site_id=site_id)

    def for_site(self, site: Site):
        return self.filter(site=site)


class SiteGroup(models.Model):
    """
    SiteGroup is a generic way of categorizing site_users to apply permissions, or
    some other label, to those users.
    """

    IN_SITE_METHOD = "for_site"
    PROVIDE_SITE_METHOD = "set_site"

    name = models.CharField(_("name"), max_length=150)
    permissions = models.ManyToManyField(
        "auth.Permission",
        related_name="permission_sitegroups",
        verbose_name=_("permissions"),
        blank=True,
    )
    site = models.ForeignKey(
        Site, related_name="site_sitegroups", on_delete=models.CASCADE
    )

    objects = SiteGroupManager()

    class Meta:
        verbose_name = _("group")
        verbose_name_plural = _("groups")

        constraints = [
            UniqueConstraint(fields=["name", "site"], name="unique_name_site")
        ]

    def set_site(self, site):
        self.site = site

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name, self.site_id


# A few helper functions for using correct auth backend for SiteUser.
def _site_user_get_permissions(site_user, obj, from_name):
    permissions = set()
    name = "get_site_%s_permissions" % from_name
    for backend in auth.get_backends():
        if hasattr(backend, name):
            permissions.update(getattr(backend, name)(site_user, obj))
    return permissions


def _site_user_has_perm(site_user, perm, obj):
    """
    A backend can raise `PermissionDenied` to short-circuit permission checking.
    """
    for backend in auth.get_backends():
        if not hasattr(backend, "has_site_perm"):
            continue
        try:
            if backend.has_site_perm(site_user, perm, obj):
                return True
        except PermissionDenied:
            return False
    return False


def _site_user_has_module_perms(site_user, app_label):
    """
    A backend can raise `PermissionDenied` to short-circuit permission checking.
    """
    for backend in auth.get_backends():
        if not hasattr(backend, "has_module_site_perms"):
            continue
        try:
            if backend.has_module_site_perms(site_user, app_label):
                return True
        except PermissionDenied:
            return False
    return False


class SiteUserManager(models.Manager):
    def create_site_creator(self, creator, site: Site):
        return self.create(site=site, user=creator, is_active=True, is_superuser=True)


class AbstractSiteUser(models.Model):
    site = models.ForeignKey(
        Site, related_name="site_siteusers", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="user_siteusers",
        on_delete=models.CASCADE,
    )

    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    is_superuser = models.BooleanField(
        _("superuser status"),
        default=False,
        help_text=_(
            "Designates that this user has all permissions without "
            "explicitly assigning them."
        ),
    )

    groups = models.ManyToManyField(
        SiteGroup,
        verbose_name=_("groups"),
        blank=True,
        help_text=_(
            "The groups this user belongs to. A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="sitegroup_siteusers",
    )
    site_user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name=_("user permissions"),
        blank=True,
        help_text=_("Specific permissions for this user."),
        related_name="permission_siteusers",
    )

    objects = SiteUserManager()

    class Meta:
        swappable = "SITE_USER_MODEL"
        abstract = True
        constraints = [
            UniqueConstraint(fields=["site", "user"], name="unique_site_user")
        ]

    @staticmethod
    def find_for_request(request: HttpRequest):
        """
        Find the site user object responsible for responding to this HTTP
        request object. Try:

        * reading site_id from session first
        * then get user default choice
        then validate the access to that

        The site user will be cached via request.user.site_user
        """
        from ..sites.utils import set_current_session_project

        global SiteUser
        SiteUser = SiteUser or get_site_user_model()

        site_id = request.session.get("site_id")
        if not site_id:
            # To keep the user working on whatever site they want
            site_id = request.session[
                "site_id"
            ] = request.user.user_siteusers.last().site_id
        site_user = (
            SiteUser.objects.filter(site_id=site_id, user_id=request.user.id)
            .select_related("site")
            .get()
        )
        if (
            not getattr(request.user, "site_user", None)
            or request.user.site_user.site_id != site_id
        ):
            set_current_session_project(request, site_user)
        return request.user.site_user

    def get_site_user_permissions(self, obj=None):
        """
        Return a list of permission strings that this user has directly.
        Query all available auth backends. If an object is passed in,
        return only permissions matching this object.
        """
        return _site_user_get_permissions(self, obj, "user")

    def get_site_group_permissions(self, obj=None):
        """
        Return a list of permission strings that this user has through their
        groups. Query all available auth backends. If an object is passed in,
        return only permissions matching this object.
        """
        return _site_user_get_permissions(self, obj, "group")

    def get_site_all_permissions(self, obj=None):
        return _site_user_get_permissions(self, obj, "all")

    def site_has_perm(self, perm, obj=None):
        """
        Return True if the user has the specified permission. Query all
        available auth backends, but return immediately if any backend returns
        True. Thus, a user who has permission from a single auth backend is
        assumed to have permission in general. If an object is provided, check
        permissions for that object.
        """
        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True

        # Otherwise we need to check the backends.
        return _site_user_has_perm(self, perm, obj)

    def site_has_perms(self, perm_list, obj=None):
        """
        Return True if the user has each of the specified permissions. If
        object is passed, check if the user has all required perms for it.
        """
        if not is_iterable(perm_list) or isinstance(perm_list, str):
            raise ValueError("perm_list must be an iterable of permissions.")
        return all(self.site_has_perm(perm, obj) for perm in perm_list)

    def site_has_module_perms(self, app_label):
        """
        Return True if the user has any permissions in the given app label.
        Use similar logic as has_perm(), above.
        """
        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True

        return _site_user_has_module_perms(self, app_label)


def get_site_user_model() -> AbstractSiteUser:
    """
    Get the site user model from the ``SITE_USER_MODEL`` setting.
    """
    from django.apps import apps

    try:
        return apps.get_model(settings.SITE_USER_MODEL, require_ready=False)
    except ValueError:
        raise ImproperlyConfigured(
            "settings must be of the form 'app_label.model_name'"
        )
    except LookupError:
        raise ImproperlyConfigured(
            "settings refers to model '%s' that has not been installed"
            % settings.SITE_USER_MODEL
        )
    except AttributeError:
        raise ImproperlyConfigured(
            "Please configure settings.SITE_USER_MODEL \
            that should subclass the AbstractSiteUser"
        )
