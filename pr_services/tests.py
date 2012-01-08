"""
Merge test classes from multiple test suites into this namespace so that
they can be easily started by a typical Django test run.


This module also ensures when test classes are merged into a single
namepsace, there are no duplicates names.
"""

import inspect

from pr_services.testlib import TestCase

TEST_MODULES = (
        'pr_services.pr_tests',
        'pr_services.exam_system.tests',
        # more coming soon...
)

def _import_test_module(path):
    module = __import__(path, globals(), locals(), [], -1)
    suites = path.split('.')[1:]
    for suite in suites:
        module = getattr(module, suite)
    return module

def _test_class_filter(name__value):
    name, value = name__value
    return name.startswith('Test') and isinstance(value, type)

def _setup_tests():
    for module_path in TEST_MODULES:
        module = _import_test_module(module_path)
        members = inspect.getmembers(module)
        classobjs = dict(filter(_test_class_filter, members))
        assert not any(name in locals() for name in classobjs)
        globals().update(classobjs)
        locals().update(classobjs)

_setup_tests()
