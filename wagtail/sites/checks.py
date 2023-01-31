from django.contrib import auth
from django.core import checks

from .backends import BaseSiteAuthBackend
from .utils import SitePermissionsMonkeyPatchMixin

UserModel = auth.get_user_model()


@checks.register()
def auth_backend_check(app_configs, **kwargs):
    errors = []

    site_auth_backend_used = False
    another_auth_backend_used = False

    for i in auth.get_backends():
        if issubclass(type(i), BaseSiteAuthBackend):
            site_auth_backend_used = True
        else:
            another_auth_backend_used = True

    if not (site_auth_backend_used and another_auth_backend_used):
        if another_auth_backend_used:
            hint = (
                "Add wagtail.sites.backends.SiteAuthBackend or "
                "a subclass of BaseSiteAuthBackend to AUTHENTICATION_BACKENDS."
            )
        else:
            hint = (
                "Add django.contrib.auth.backends.ModelBackend or "
                "another backend to AUTHENTICATION_BACKENDS."
            )
        errors.append(
            checks.Error(
                "A subclass of BaseSiteAuthBackend and another authbackend should \
                be used as AUTHENTICATION_BACKENDS.",
                hint=hint,
            )
        )
    return errors


@checks.register()
def user_model_patche_check(app_configs, **kwargs):
    errors = []

    patched = getattr(UserModel, "patched", None)
    monkey_patched = issubclass(UserModel, SitePermissionsMonkeyPatchMixin)

    if not (monkey_patched or patched):
        hint = (
            "Either add SitePermissionsMonkeyPatchMixin to "
            "the user class's first base or if you patched it your self "
            "set it's `patched` attribute to True"
        )
        errors.append(
            checks.Error(
                "the User class is not pathced for using sited app",
                hint=hint,
            )
        )
    return errors
