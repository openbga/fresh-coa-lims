from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        from config.integrations import report_holds, report_methods
        from reporting.evidence import register_collector

        register_collector("holds", report_holds)
        register_collector("methods", report_methods)
