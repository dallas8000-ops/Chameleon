from django.core.management.base import BaseCommand, CommandError

from api.deployment_checks import ROLES, collect_deployment_problems


class Command(BaseCommand):
    help = "Verify the production runtime configuration for a deployed Chameleon service."

    def add_arguments(self, parser):
        parser.add_argument(
            "--role",
            choices=[*ROLES, "all"],
            default="all",
            help="Service role to check: web, worker, beat or all (default: all).",
        )
        parser.add_argument(
            "--skip-media-write-probe",
            action="store_true",
            help="Skip the MEDIA_ROOT write test; use where the volume is not mounted "
            "(Railway pre-deploy).",
        )

    def handle(self, *args, **options):
        role = options["role"]
        problems = collect_deployment_problems(
            role, probe_media_write=not options["skip_media_write_probe"]
        )
        if problems:
            for problem in problems:
                self.stderr.write(f"- {problem}")
            raise CommandError(
                f"{len(problems)} deployment configuration problem(s) found for role '{role}'."
            )
        self.stdout.write(f"Deployment configuration looks correct for role '{role}'.")
