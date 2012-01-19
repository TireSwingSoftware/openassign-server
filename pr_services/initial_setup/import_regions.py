from django.core.management import call_command

def setup(machine):
    call_command('loaddata', 'default_regions.json', verbosity=0, commit=False)
