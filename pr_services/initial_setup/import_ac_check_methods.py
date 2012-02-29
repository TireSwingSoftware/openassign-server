
from pr_services.authorizer.checks import import_authorizer_checks
from decorators import authz

@authz
def setup(machine):
    import_authorizer_checks()
