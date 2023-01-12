from django.contrib.auth import get_user_model

from wagtail.admin.views.bulk_action import BulkAction
from wagtail.users.views.users import get_users_filter_query


User = get_user_model()


class UserBulkAction(BulkAction):
    models = [get_user_model()]

    def get_all_objects_in_listing_query(self, parent_id):
        listing_objects = self.model.objects.all().values_list("pk", flat=True)
        if "q" in self.request.GET:
            q = self.request.GET.get("q")
            model_fields = [f.name for f in self.model._meta.get_fields()]
            conditions = get_users_filter_query(q, model_fields)

            listing_objects = listing_objects.filter(conditions)

        return listing_objects

    def get_actionable_objects(self):
        objects, objects_without_access = super().get_actionable_objects()
        user = self.request.user
        users = list(
            User.objects.filter(
                id__in=[u.id for u in objects],
                user_siteusers__site_id=user.site_user.site_id,
            )
        )
        if len(objects) != len(users):
            objects_without_access["items_with_no_access"].extend(
                [i for i in objects if i not in users]
            )
        return users, objects_without_access
