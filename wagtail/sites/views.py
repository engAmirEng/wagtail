from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from wagtail.admin import messages

from wagtail.models.sites import SiteUser
from wagtail.sites.utils import set_current_session_project

from wagtail.admin.ui.tables import Column, TitleColumn
from wagtail.admin.views import generic
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.models import Site
from wagtail.permissions import site_permission_policy
from wagtail.sites.forms import SiteForm


class IndexView(generic.IndexView):
    page_title = _("Sites")
    add_item_label = _("Add a site")
    context_object_name = "sites"
    default_ordering = "sitename"
    columns = [
        TitleColumn(
            "sitename",
            label=_("@sitename"),
            sort_key="sitename",
            url_name="wagtailsites:edit",
        ),
        Column("hostname", sort_key="hostname"),
        Column("port", sort_key="port"),
        # Column("site_name"),
        TitleColumn(
            lambda instance: "⏩⏩⏩",
            label="Workon",
            get_url=lambda instance: reverse("workon", kwargs={"site_id": instance.id}),
        ),
    ]

    def get_queryset(self):
        return (
            super(IndexView, self)
            .get_queryset()
            .filter(site_siteusers__user=self.request.user)
        )


class CreateView(generic.CreateView):
    page_title = _("Add site")
    success_message = _("Site '%(object)s' created.")
    template_name = "wagtailsites/create.html"

    def get_form_kwargs(self):
        kwargs = super(CreateView, self).get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_queryset(self):
        return (
            super(CreateView, self)
            .get_queryset()
            .filter(site_siteusers__user=self.request.user)
        )


class EditView(generic.EditView):
    success_message = _("Site '%(object)s' updated.")
    error_message = _("The site could not be saved due to errors.")
    delete_item_label = _("Delete site")
    context_object_name = "site"
    template_name = "wagtailsites/edit.html"

    def get_queryset(self):
        return (
            super(EditView, self)
            .get_queryset()
            .filter(site_siteusers__user=self.request.user)
        )


class DeleteView(generic.DeleteView):
    success_message = _("Site '%(object)s' deleted.")
    page_title = _("Delete site")
    confirmation_message = _("Are you sure you want to delete this site?")

    def get_queryset(self):
        return (
            super(DeleteView, self)
            .get_queryset()
            .filter(site_siteusers__user=self.request.user)
        )


class SiteViewSet(ModelViewSet):
    icon = "site"
    model = Site
    permission_policy = site_permission_policy

    index_view_class = IndexView
    add_view_class = CreateView
    edit_view_class = EditView
    delete_view_class = DeleteView

    def get_form_class(self, for_update=False):
        return SiteForm


def site_workon_view(request, site_id: int):
    try:
        site_user = request.user.user_siteusers.get(site_id=site_id)
    except SiteUser.DoesNotExist:
        messages.error(
            request, _("This Site does not exists or you are not a part of it.")
        )
    else:
        set_current_session_project(request, site_user)
        messages.success(
            request,
            _(
                "You are now working on {project_name}".format(
                    project_name=request.user.site_user.site
                )
            ),
        )
    resp = redirect(request.META["HTTP_REFERER"])
    return resp
