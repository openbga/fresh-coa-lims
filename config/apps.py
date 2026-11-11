from django.contrib.admin.apps import AdminConfig


class AuditedAdminConfig(AdminConfig):
    default_site = "config.admin.AuditedAdminSite"
