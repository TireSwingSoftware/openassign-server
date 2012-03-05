
"""
This is a quick and dirty script to more easily search through ACLs for roles.
It may be helpful if you want to know what operations each role can perform on
an object.
"""

import textwrap

from collections import defaultdict
from optparse import make_option
from operator import itemgetter
from pprint import pprint

from django.core.management import call_command
from django.core.management.base import BaseCommand

import facade

facade.import_models(locals())

option_items = itemgetter('create', 'read', 'update', 'delete')

default_read_fields = frozenset(('id',
                                 'content_type',
                                 'create_timestamp',
                                 'save_timestamp'))

class Command(BaseCommand):

    args = "<model or manager types...>"

    option_list = BaseCommand.option_list + (
        make_option('-c', '--create', action='store_true', default=False,
            help='Include create privileges'),
        make_option('-r', '--read', action='store_true', default=False,
            help='Include read privileges'),
        make_option('-u', '--update', action='store_true', default=False,
            help='Include update privileges'),
        make_option('-d', '--delete', action='store_true', default=False,
            help='Include delete privileges'),
        make_option('-R', '--show-roles-only', action='store_true',
            default=False, help='Only show role names'),
        make_option('-t', '--find-check-methods', action='store_true', default=False,
            help='Find authorizer checks using the types specified on'
            ' the command line'),
        make_option('-D', '--dont-show-docs', action='store_true', default=False,
            help='When listing authorizer checks dont show documentation'),
    )

    authorizer = facade.subsystems.Authorizer()

    def handle(self, *args, **options):
        actee_types = set(map(str.strip, args))
        if options['find_check_methods']:
            self.findchecks(actee_types, **options)
        else:
           self.showprivs(actee_types, **options)

    def findchecks(self, actee_types, **options):
        checks = []
        actee_types = set(map(lambda x: getattr(facade.models, x), actee_types))
        names = ACCheckMethod.objects.values_list('name', flat=True).order_by('name')
        for shortname in map(str, names):
            suite, _, name = shortname.rpartition('.')
            module = __import__('pr_services.authorizer.checks.%s' % suite,
                    fromlist=[name])
            check = getattr(module, name)
            check_types = getattr(check, '_check_types', None)
            if not (check_types and bool(actee_types & set(check_types))):
                continue
            if options['dont_show_docs']:
                print(shortname)
            else:
                doc = textwrap.wrap(textwrap.dedent(check.__doc__))
                print('%s' % (70 * '-'))
                print('%s:\n\n%s\n\n' % (shortname, '\n'.join(doc)))
            print('')

    def showprivs(self, actee_types, **options):
        c, r, u, d = option_items(options)
        if not c | r | u | d:
            c = r = u = d = True
        roles = {}
        acls = self.collect_acls(actee_types, c, r, u, d)
        for acl in acls:
            role_name = str(acl.object.role.name)
            role = roles.setdefault(role_name, {})
            for actee_type in actee_types:
                privs = acl.privs.get(actee_type, None)
                role.setdefault(actee_type, {})
                if hasattr(facade.models, actee_type):
                    if c:
                        role[actee_type].setdefault('c', False)
                        role[actee_type]['c'] |= privs['c']

                    if r:
                        role[actee_type].setdefault('r', set())
                        role[actee_type]['r'] |= privs['r'] - default_read_fields

                    if u:
                        role[actee_type].setdefault('u', set())
                        role[actee_type]['u'] |= privs['u'] - default_read_fields

                    if d:
                        role[actee_type].setdefault('d', False)
                        role[actee_type]['d'] |= privs['d']

        if options['show_roles_only']:
            pprint(roles.keys())
        else:
            pprint(roles)

    def collect_acls(self, actee_types, c, r, u, d):
        acls = list()
        collect = self.authorizer.acls.collect
        for actee_type in actee_types:
            if hasattr(facade.models, actee_type):
                actee = getattr(facade.models, actee_type)
                if c:
                    acls.extend(collect('c', actee))
                if r:
                    acls.extend(collect('r', actee))
                if u:
                    acls.extend(collect('u', actee))
                if d:
                    acls.extend(collect('d', actee))
        return acls

