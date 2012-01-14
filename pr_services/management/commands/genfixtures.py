import sys

from StringIO import StringIO
from contextlib import contextmanager
from os import path

from django.core.management import call_command
from django.core.management.base import NoArgsCommand

from settings import PROJECT_ROOT


_stdout = sys.stdout

# XXX: some magic to get around django
# dumpdata stupidly writing *only* to standard out.
@contextmanager
def catch_stdout(stream=None):
    if stream is None:
        stream = StringIO()
    sys.stdout = stream
    yield
    sys.stdout = _stdout


class Command(NoArgsCommand):
    requires_model_validation = False

    FIXTURE_DIR = 'pr_services/testlib/fixtures'

    def handle_noargs(self, **options):
        self.fixture_dir = path.join(PROJECT_ROOT, self.FIXTURE_DIR)
        print("Writing fixtures to %s" % self.FIXTURE_DIR)
        for create_fixture in (self._initial_setup_default,
                               self._initial_setup_precor):
            with catch_stdout(None):
                call_command('resetdb')

            create_fixture()

    def _dumpdata(self, models, filename):
        print("Writing %s" % filename)
        buf = StringIO()
        with catch_stdout(buf):
            call_command('dumpdata', *models, use_natural_keys=True, indent=4)

        filepath = path.join(self.fixture_dir, filename)
        with open(filepath, 'w') as f:
            f.write(buf.getvalue())

    def _initial_setup_default(self):
        with catch_stdout(None):
            call_command('setup')

        models = [
           'pr_messaging',
           'pr_services.ACCheckMethod',
           'pr_services.ACL',
           'pr_services.ACMethodCall',
           'pr_services.Address',
           'pr_services.AuthToken',
           'pr_services.Blame',
           'pr_services.Domain',
           'pr_services.DomainAffiliation',
           'pr_services.Group',
           'pr_services.Role',
           'pr_services.SessionUserRole',
           'pr_services.User',
           ]
        self._dumpdata(models, 'initial_setup_default.json')


    def _initial_setup_precor(self):
        with catch_stdout(None):
            call_command('setup', 'base', 'legacy', 'precor')

        models = [
           'pr_messaging',
           'pr_services.ACCheckMethod',
           'pr_services.ACL',
           'pr_services.ACMethodCall',
           'pr_services.Address',
           'pr_services.AuthToken',
           'pr_services.Blame',
           'pr_services.Domain',
           'pr_services.DomainAffiliation',
           'pr_services.Group',
           'pr_services.Role',
           'pr_services.SessionUserRole',
           'pr_services.User',
           ]
        self._dumpdata(models, 'initial_setup_precor.json')
