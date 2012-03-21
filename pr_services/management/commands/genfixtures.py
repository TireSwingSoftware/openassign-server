import sys

from StringIO import StringIO
from contextlib import contextmanager
from os import path

from django.core.management import call_command
from django.core.management.base import BaseCommand

from settings import PROJECT_ROOT

from pr_services.initial_setup import (InitialSetupMachine,
        create_default_domains,
        create_organization_admin_role)

import facade
facade.import_models(locals())


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


def fixture(func):
    setattr(func, '_fixture', True)
    return func

class Command(BaseCommand):
    args = '<fixture names...>'
    requires_model_validation = False

    FIXTURE_DIR = 'pr_services/testlib/fixtures'

    def handle(self, *args, **options):
        self.fixture_dir = path.join(PROJECT_ROOT, self.FIXTURE_DIR)
        print("Writing fixtures to %s" % self.FIXTURE_DIR)
        fixture_names = set(args)
        for name in dir(self):
            if name.startswith('_'):
                continue
            if fixture_names and name not in fixture_names:
                continue
            func = getattr(self, name)
            if not hasattr(func, '_fixture'):
                continue
            with catch_stdout(None):
                call_command('resetdb')
            func()

    def _dumpdata(self, models, filename):
        print("Writing %s" % filename)
        buf = StringIO()
        with catch_stdout(buf):
            call_command('dumpdata', *models, use_natural_keys=True, indent=4)

        filepath = path.join(self.fixture_dir, filename)
        with open(filepath, 'w') as f:
            f.write(buf.getvalue())

    @fixture
    def initial_setup_default(self):
        with catch_stdout(None):
            call_command('setup', 'base', 'legacy')

        models = [
           'pr_messaging',
           'pr_services.ACCheckMethod',
           'pr_services.ACL',
           'pr_services.ACMethodCall',
           'pr_services.Address',
           'pr_services.Blame',
           'pr_services.Domain',
           'pr_services.DomainAffiliation',
           'pr_services.Group',
           'pr_services.Role',
           'pr_services.SessionUserRole',
           'pr_services.User',
           ]
        self._dumpdata(models, 'initial_setup_default.json')


    @fixture
    def initial_setup_precor(self):
        with catch_stdout(None):
            call_command('setup', 'base', 'legacy', 'precor')

        models = [
           'pr_messaging',
           'pr_services.ACCheckMethod',
           'pr_services.ACL',
           'pr_services.ACMethodCall',
           'pr_services.Address',
           'pr_services.Blame',
           'pr_services.Domain',
           'pr_services.DomainAffiliation',
           'pr_services.Group',
           'pr_services.Role',
           'pr_services.SessionUserRole',
           'pr_services.User',
           ]
        self._dumpdata(models, 'initial_setup_precor.json')

    def _pr_services(self, model):
        return 'pr_services.' + model

#    @fixture
#    def barebones(self):
#        from pr_services.authorizer.checks import import_authorizer_checks
#        machine = InitialSetupMachine()
#        import_authorizer_checks()
#        create_default_domains.setup(machine)
#        models = map(self._pr_services, [
#           'ACCheckMethod',
#           'ACL',
#           'ACMethodCall',
#           'Domain',
#           'DomainAffiliation',
#        ])
#        self._dumpdata(models, 'barebones.json')

    @fixture
    def barebones_orgrole(self):
        from pr_services.authorizer.checks import import_authorizer_checks
        machine = InitialSetupMachine()
        import_authorizer_checks()
        create_default_domains.setup(machine)
        create_organization_admin_role.setup(machine)
        with catch_stdout(None):
            call_command('loaddata', 'unprivileged_user', 'precor_org_roles')
        user = User.objects.get(id=2)
        org = Organization.objects.create(name='Foo')
        role = OrgRole.objects.get(name='Administrator')
        UserOrgRole.objects.create(owner=user, organization=org, role=role)
        models = map(self._pr_services, [
           'ACCheckMethod',
           'ACL',
           'ACMethodCall',
           'Blame',
           'Domain',
           'DomainAffiliation',
           'OrgRole',
           'Organization',
           'Role',
           'User',
           'UserOrgRole',
        ])
        self._dumpdata(models, 'barebones_orgrole.json')
